/** Semantic help search, running entirely on the user's own machine.
 *
 * The article embeddings were computed at build time (scripts/build-help-index.mjs)
 * and ship inside the bundle, so at runtime the only thing that needs encoding
 * is the handful of words the user typed. That is one short forward pass, which
 * is why search feels instant once the model is warm.
 *
 * Nothing here talks to the network beyond fetching our own model files from
 * this origin: `allowRemoteModels` is off and the ONNX runtime's wasm is
 * self-hosted, so the feature works on a locked-down campus network and keeps
 * working offline. It also means nothing a user types into the help box leaves
 * their machine, which matters when the thing they are stuck on has a student's
 * name in it.
 */
import { HELP_ARTICLES, HELP_MODEL_ID } from "./helpIndex";

/** Where our copies live, relative to the app origin. */
const MODEL_ROOT = "/models/";

/** The ONNX runtime loads its wasm glue with a runtime `import()`.
 *
 * That has to be an absolute URL. Given a bare "/ort/" the bundler treats it as
 * a source import and refuses -- these files live in public/ and are copied
 * verbatim, never passed through the pipeline. Building the URL from the
 * current origin keeps it opaque to the bundler and correct at runtime. */
function wasmRoot(): string {
  return new URL("/ort/", window.location.origin).href;
}

export type ModelState = "idle" | "loading" | "ready" | "failed";

type Extractor = (
  text: string,
  opts: { pooling: "mean"; normalize: boolean },
) => Promise<{ data: Float32Array | number[] }>;

let extractorPromise: Promise<Extractor> | null = null;
let state: ModelState = "idle";
const listeners = new Set<(s: ModelState) => void>();

function setState(next: ModelState) {
  state = next;
  for (const listener of listeners) listener(next);
}

export function modelState(): ModelState {
  return state;
}

export function onModelState(listener: (s: ModelState) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * Load the encoder. Safe to call repeatedly — the promise is cached, so a user
 * who opens and closes the panel three times still only downloads once.
 */
export function loadModel(): Promise<Extractor> {
  if (extractorPromise) return extractorPromise;
  setState("loading");
  extractorPromise = (async () => {
    const { env, pipeline } = await import("@huggingface/transformers");

    // Our files only. Without this, a missing local file silently becomes a
    // request to a CDN, which is exactly the failure we cannot have here.
    env.allowRemoteModels = false;
    env.allowLocalModels = true;
    env.localModelPath = MODEL_ROOT;

    // Typed as optional because the same env object serves the Node build,
    // where there is no wasm backend at all.
    const wasm = env.backends.onnx.wasm;
    if (wasm) {
      wasm.wasmPaths = wasmRoot();
      // Threads need cross-origin isolation, which this app does not set.
      // Asking for one thread avoids ORT probing for SharedArrayBuffer and
      // warning when it is absent; encoding one short query is not worth
      // isolating the whole page for.
      wasm.numThreads = 1;
    }

    const extractor = (await pipeline("feature-extraction", HELP_MODEL_ID, {
      dtype: "q8",
      device: "wasm",
    })) as unknown as Extractor;

    // Warm the graph on a throwaway string so the first real search does not
    // pay for lazy allocation on top of everything else.
    await extractor("warm up", { pooling: "mean", normalize: true });
    setState("ready");
    return extractor;
  })().catch((err) => {
    setState("failed");
    extractorPromise = null; // let a later open try again
    throw err;
  });
  return extractorPromise;
}

/** Both sides are unit vectors, so the dot product is the cosine. */
function cosine(a: ArrayLike<number>, b: ArrayLike<number>): number {
  let sum = 0;
  for (let i = 0; i < b.length; i++) sum += (a[i] ?? 0) * b[i];
  return sum;
}

/**
 * Cosine similarity of the query against every article, unfiltered.
 *
 * No threshold is applied here, deliberately. Measured against this corpus, the
 * absolute cosine is not comparable between differently-phrased queries: a long
 * conversational question dilutes the query vector, so the *correct* article for
 * "someone rang in sick and I need to find a replacement" scores 0.19 while an
 * off-topic question can reach 0.27 against something irrelevant. Any fixed cut
 * either loses real answers or admits nonsense. Ranking and cutting is done in
 * ./search, relative to the best hit for that particular query.
 */
export async function semanticScores(query: string): Promise<Map<string, number>> {
  const scores = new Map<string, number>();
  const text = query.trim();
  if (!text) return scores;

  const extractor = await loadModel();
  const encoded = await extractor(text, { pooling: "mean", normalize: true });
  const vector = encoded.data;

  for (const article of HELP_ARTICLES) {
    scores.set(article.id, cosine(vector, article.embedding));
  }
  return scores;
}
