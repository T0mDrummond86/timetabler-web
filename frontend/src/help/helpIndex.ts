/** The help corpus, and the cheap search that always works.
 *
 * Two searches live in this feature. The semantic one is better but needs a
 * ~34 MB model to finish downloading first; this one is a plain word match over
 * titles and keywords, available the instant the panel opens. The panel starts
 * on this and upgrades itself when the model is ready, so search is never
 * simply unavailable — including on a machine where the model fails to load at
 * all.
 */
import raw from "./help-index.generated.json";

export type HelpArticle = {
  id: string;
  title: string;
  category: string;
  keywords: string[];
  body: string;
  embedding: number[];
};

export type HelpHit = {
  article: HelpArticle;
  score: number;
  /** Which search produced it, so the panel can say so. */
  via: "semantic" | "keyword";
};

const index = raw as { model: string; dims: number; articles: HelpArticle[] };

export const HELP_ARTICLES: HelpArticle[] = index.articles;
export const HELP_MODEL_ID = index.model;
export const HELP_DIMS = index.dims;

export function articleById(id: string): HelpArticle | undefined {
  return HELP_ARTICLES.find((a) => a.id === id);
}

/**
 * Browsing order: roughly the order someone meets these things, rather than
 * the alphabetical order the filenames happen to give. Anything not listed
 * falls to the end, so adding a category cannot make it disappear.
 */
const CATEGORY_ORDER = [
  "Getting started",
  "The timetable grid",
  "Classes, groups and qualifications",
  "Lecturers",
  "Warnings and clashes",
  "Lecturer cover",
  "Change log and admin export",
  "Importing data",
  "Exporting and printing",
  "Block delivery and variants",
  "Global workspace",
  "Account and security",
  "Troubleshooting",
];

export function helpCategories(): { name: string; articles: HelpArticle[] }[] {
  const out: { name: string; articles: HelpArticle[] }[] = [];
  for (const article of HELP_ARTICLES) {
    let group = out.find((g) => g.name === article.category);
    if (!group) {
      group = { name: article.category, articles: [] };
      out.push(group);
    }
    group.articles.push(article);
  }
  const rank = (name: string) => {
    const at = CATEGORY_ORDER.indexOf(name);
    return at === -1 ? CATEGORY_ORDER.length : at;
  };
  return out.sort((a, b) => rank(a.name) - rank(b.name));
}

function normalise(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9\s]/g, " ");
}

/** Words too common in this corpus to tell two articles apart. */
const STOP = new Set([
  "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
  "it", "this", "that", "my", "i", "how", "do", "does", "can", "not", "no",
  "with", "at", "be", "was", "when", "what", "why", "cannot", "cant", "wont",
  "class", "classes", "timetable",
]);

/**
 * Word-overlap score per article, in 0..1. Title and keyword hits are weighted
 * far above body hits, because a word appearing somewhere in an article's prose
 * says very little — nearly every article here mentions "lecturer" somewhere.
 *
 * Returned for every article rather than as a ranked list, because the real
 * search blends these with the semantic scores; see `search` in ./search.
 */
export function keywordScores(query: string): Map<string, number> {
  const scores = new Map<string, number>();
  const terms = normalise(query)
    .split(/\s+/)
    .filter((t) => t.length > 1 && !STOP.has(t));
  if (!terms.length) return scores;

  // The most one term can contribute, used to bring the total into 0..1.
  const perTermMax = 10;
  for (const article of HELP_ARTICLES) {
    const title = normalise(article.title);
    const keywords = normalise(article.keywords.join(" "));
    const body = normalise(article.body);

    let score = 0;
    for (const term of terms) {
      if (title.includes(term)) score += 6;
      if (keywords.includes(term)) score += 4;
      else if (body.includes(term)) score += 1;
    }
    if (score > 0) {
      // Divided by the theoretical maximum so a long query is not automatically
      // a better match than a short one.
      scores.set(article.id, Math.min(1, score / (terms.length * perTermMax)));
    }
  }
  return scores;
}

/**
 * Articles where a query word hit the **title or keywords** — not merely the
 * prose. Used as corroborating evidence that a query is about this app at all.
 *
 * The distinction matters: nearly every article's body contains ordinary words
 * like "room" or "week", so a body hit is close to no evidence. A hit on a
 * curated keyword line is a deliberate signal that someone anticipated this
 * phrasing.
 */
export function lexicalHitIds(query: string): Set<string> {
  const ids = new Set<string>();
  const terms = normalise(query)
    .split(/\s+/)
    .filter((t) => t.length > 2 && !STOP.has(t));
  if (!terms.length) return ids;

  for (const article of HELP_ARTICLES) {
    const haystack = `${normalise(article.title)} ${normalise(article.keywords.join(" "))}`;
    if (terms.some((t) => haystack.includes(t))) ids.add(article.id);
  }
  return ids;
}

/** Ranked list from word overlap alone — what search falls back to. */
export function keywordSearch(query: string, limit = 12): HelpHit[] {
  const scores = keywordScores(query);
  const hits: HelpHit[] = [];
  for (const article of HELP_ARTICLES) {
    const score = scores.get(article.id);
    if (score) hits.push({ article, score, via: "keyword" });
  }
  return hits.sort((a, b) => b.score - a.score).slice(0, limit);
}

/** First sentence or so of an article, for the result list.
 *
 * Only the opening prose. An article that gets to the point with a list would
 * otherwise show "1. Set Week beginning" as its summary, which reads like a
 * fragment rather than a description of what the article is for.
 */
export function snippet(article: HelpArticle, max = 140): string {
  const lead: string[] = [];
  for (const line of article.body.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (lead.length) break; // end of the first paragraph
      continue;
    }
    if (/^([-*]\s|\d+\.\s|#{1,4}\s)/.test(trimmed)) break;
    lead.push(trimmed);
  }
  const text = (lead.join(" ") || article.body)
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[*_`#>]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (text.length <= max) return text;
  const cut = text.slice(0, max);
  const stop = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf(" "));
  return `${cut.slice(0, stop > 40 ? stop : max)}…`;
}
