/** Ranking: what the panel actually calls.
 *
 * Neither signal is good enough alone.
 *
 * The embedding model understands paraphrase, which is the whole point — "the
 * students would have to be in two places at once" finds *Course class overlap*
 * without sharing a word with it. But its absolute scores are not comparable
 * between queries. Measured on this corpus, the right article for "someone rang
 * in sick and I need to find a replacement" scores 0.19, while "how do I book a
 * holiday to spain" reaches 0.27 against something irrelevant. A fixed cut
 * therefore cannot separate them.
 *
 * Plain word matching has the opposite shape: precise when a word lands, blind
 * when it does not. "Sick" is literally in the cover article's keywords, so it
 * rescues exactly the query the model was weakest on.
 *
 * So: blend the two, then cut *relative* to the best hit for this query rather
 * than against a global number. Whether the top result is 0.2 or 0.7 tells us
 * little; whether the fourth result is close to the first tells us a lot.
 */
import {
  HELP_ARTICLES,
  articleById,
  keywordScores,
  keywordSearch,
  lexicalHitIds,
  type HelpHit,
} from "./helpIndex";
import { semanticScores } from "./semanticSearch";

/** How much of the blended score comes from word overlap. */
const KEYWORD_WEIGHT = 0.35;

/** Results scoring below this share of the top hit are dropped as also-rans. */
const RELATIVE_CUT = 0.55;

/** A floor for the blended score, below which nothing is worth showing. */
const ABSOLUTE_FLOOR = 0.12;

/**
 * Semantic score at which the model alone is convincing enough to answer.
 * Below it, the top hit also needs a word from the query to have landed on
 * some article's title or keywords — corroboration that the question is about
 * this app rather than the model reaching for the nearest thing it has.
 *
 * Measured: real questions clear 0.35 outright, or fall below it while still
 * matching a curated keyword ("rang in sick" → the cover article's "sick").
 * "What is for lunch in the cafeteria today" does neither, and gets the
 * no-match state.
 */
const CONFIDENT_SEMANTIC = 0.35;

const MAX_RESULTS = 8;

export async function search(query: string): Promise<HelpHit[]> {
  const text = query.trim();
  if (!text) return [];

  const [semantic, keyword] = [await semanticScores(text), keywordScores(text)];
  if (!semantic.size) return keywordSearch(text);
  const lexical = lexicalHitIds(text);

  const blended: HelpHit[] = HELP_ARTICLES.map((article) => {
    const s = Math.max(0, semantic.get(article.id) ?? 0);
    const k = keyword.get(article.id) ?? 0;
    return {
      article,
      score: s * (1 - KEYWORD_WEIGHT) + k * KEYWORD_WEIGHT,
      via: "semantic" as const,
    };
  }).sort((a, b) => b.score - a.score);

  const top = blended[0];
  if (!top || top.score < ABSOLUTE_FLOOR) return [];

  // Is the best hit actually evidence of anything?
  const confident =
    (semantic.get(top.article.id) ?? 0) >= CONFIDENT_SEMANTIC || lexical.has(top.article.id);
  if (!confident) return [];

  const cut = Math.max(ABSOLUTE_FLOOR, top.score * RELATIVE_CUT);
  return blended.filter((hit) => hit.score >= cut).slice(0, MAX_RESULTS);
}

export { articleById };
