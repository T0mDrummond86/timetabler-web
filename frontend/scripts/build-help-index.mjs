/** Turn src/help/articles/*.md into a searchable index with embeddings baked in.
 *
 * The output is committed, so a normal build does not run this -- see the note
 * at the foot of the file for how to regenerate after editing an article.
 *
 * Doing the article side of the embedding here rather than in the browser means
 * a user's machine only
 * ever has to encode the short string they typed, which is the difference
 * between search feeling instant and search feeling like a page load.
 *
 * The model files are read from public/models, the same copies the browser
 * uses, so the two sides cannot drift onto different weights and start
 * disagreeing about what is similar to what.
 */
import { readdir, readFile, writeFile, mkdir, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
// HELP_ROOT lets the script run from a throwaway install elsewhere. The dev
// container is Alpine, and transformers.js pulls in native modules (onnxruntime
// and sharp) that are built against glibc, so generating the index is done in a
// Debian container with its own node_modules. See docs at the foot of this file.
const ROOT = process.env.HELP_ROOT
  ? path.resolve(process.env.HELP_ROOT)
  : path.resolve(HERE, "..");
const ARTICLES = path.join(ROOT, "src/help/articles");
const MODELS = path.join(ROOT, "public/models");
const PUBLIC = path.join(ROOT, "public");
const OUT = path.join(ROOT, "src/help/help-index.generated.json");
const MODEL_ID = "Xenova/all-MiniLM-L6-v2";

/** Minimal frontmatter reader — the files are ours, so no YAML parser needed. */
function parseArticle(raw, file) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(raw);
  if (!match) throw new Error(`${file}: missing frontmatter block`);
  const [, head, body] = match;
  const meta = {};
  for (const line of head.split(/\r?\n/)) {
    const at = line.indexOf(":");
    if (at === -1) continue;
    const key = line.slice(0, at).trim();
    let value = line.slice(at + 1).trim();
    // Titles containing a colon are quoted in the frontmatter.
    if (value.startsWith('"') && value.endsWith('"')) value = value.slice(1, -1);
    meta[key] = value;
  }
  for (const required of ["id", "title", "category", "keywords"]) {
    if (!meta[required]) throw new Error(`${file}: frontmatter is missing "${required}"`);
  }
  return {
    id: meta.id,
    title: meta.title,
    category: meta.category,
    keywords: meta.keywords
      .split(",")
      .map((k) => k.trim())
      .filter(Boolean),
    body: body.trim(),
  };
}

/** Plain text for the encoder: no markdown syntax, no link or image targets. */
function toPlainText(body) {
  return body
    // Screenshots first: their alt text describes a picture, not the topic, and
    // the file path is pure noise in an embedding.
    .replace(/!\[[^\]]*\]\([^)\s]+\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1") // links keep their words
    .replace(/[*_`#>]/g, "")
    .replace(/\r?\n[-*]\s+/g, ". ")
    .replace(/\s+/g, " ")
    .trim();
}

/** What actually gets encoded.
 *
 * Title and keywords are repeated ahead of the prose deliberately. The model
 * truncates at 256 tokens, and a long article's tail matters far less to
 * "which article is this" than the phrasings a user might type.
 */
function embeddingText(article) {
  const plain = toPlainText(article.body);
  return [
    article.title,
    article.keywords.join(", "),
    article.category,
    plain.slice(0, 1200),
  ].join(". ");
}

async function main() {
  if (!existsSync(MODELS)) {
    throw new Error(
      `Model files not found at ${MODELS}. They are committed to the repo; ` +
        `if this is a fresh checkout, check they were not excluded.`,
    );
  }

  const files = (await readdir(ARTICLES)).filter((f) => f.endsWith(".md")).sort();
  if (!files.length) throw new Error(`No articles found in ${ARTICLES}`);

  const articles = [];
  const seen = new Set();
  for (const file of files) {
    const article = parseArticle(await readFile(path.join(ARTICLES, file), "utf8"), file);
    if (seen.has(article.id)) throw new Error(`Duplicate article id "${article.id}" in ${file}`);
    seen.add(article.id);
    articles.push(article);
  }

  // Every internal [text](#id) must point at an article that exists, or the
  // help would quietly offer dead links.
  const broken = [];
  for (const article of articles) {
    for (const [, target] of article.body.matchAll(/\]\(#([a-z0-9-]+)\)/g)) {
      if (!seen.has(target)) broken.push(`${article.id} -> #${target}`);
    }
  }
  if (broken.length) throw new Error(`Broken help links:\n  ${broken.join("\n  ")}`);

  // Same reasoning for screenshots: a missing file would be a silent broken
  // image in the panel, which is worse than a build that stops and says so.
  const missingShots = [];
  for (const article of articles) {
    for (const [, src] of article.body.matchAll(/!\[[^\]]*\]\(([^)\s]+)\)/g)) {
      if (!src.startsWith("/")) {
        missingShots.push(`${article.id} -> ${src} (must be an absolute path under public/)`);
        continue;
      }
      if (!existsSync(path.join(PUBLIC, src.replace(/^\//, "")))) {
        missingShots.push(`${article.id} -> ${src}`);
      }
    }
  }
  if (missingShots.length) {
    throw new Error(`Missing help screenshots:\n  ${missingShots.join("\n  ")}`);
  }

  const { env, pipeline } = await import("@huggingface/transformers");
  env.allowRemoteModels = false;
  env.localModelPath = MODELS;

  const extractor = await pipeline("feature-extraction", MODEL_ID, { dtype: "q8" });

  const vectors = [];
  for (const article of articles) {
    const out = await extractor(embeddingText(article), { pooling: "mean", normalize: true });
    // Rounded to 5 places: the JSON halves in size and cosine similarity moves
    // by less than a thousandth, which no ranking here is close enough to feel.
    vectors.push(Array.from(out.data, (v) => Math.round(v * 1e5) / 1e5));
  }

  const payload = {
    model: MODEL_ID,
    dims: vectors[0].length,
    articles: articles.map((a, i) => ({
      id: a.id,
      title: a.title,
      category: a.category,
      keywords: a.keywords,
      body: a.body,
      embedding: vectors[i],
    })),
  };

  await mkdir(path.dirname(OUT), { recursive: true });
  await writeFile(OUT, JSON.stringify(payload), "utf8");
  const { size } = await stat(OUT);
  console.log(
    `help index: ${articles.length} articles, ${payload.dims} dims, ` +
      `${(size / 1024).toFixed(0)} kB -> ${path.relative(ROOT, OUT)}`,
  );
}

await main();

/* Regenerate after editing any article:
 *
 *   cd frontend && docker run --rm -v "$PWD":/app -w /work node:22-bookworm-slim \
 *     bash -lc 'npm init -y >/dev/null && npm i --no-audit --no-fund \
 *       @huggingface/transformers@3.8.1 >/dev/null 2>&1 \
 *       && cp /app/scripts/build-help-index.mjs . \
 *       && HELP_ROOT=/app node build-help-index.mjs'
 *
 * The output is committed, so a normal build needs none of this.
 */
