/** The Help panel: a search box, a ranked list, and the article you picked.
 *
 * Search runs twice on purpose. Keyword results appear immediately from the
 * bundled index, then the semantic results replace them once the model is warm.
 * The alternative — a spinner until a 34 MB download finishes — would make the
 * first minute of Help worse than no Help at all, and someone looking up
 * "room too small" never needs the clever search anyway.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  articleById,
  helpCategories,
  keywordSearch,
  snippet,
  type HelpArticle,
  type HelpHit,
} from "./helpIndex";
import { HelpMarkdown } from "./markdown";
import { search } from "./search";
import { loadModel, modelState, onModelState, type ModelState } from "./semanticSearch";

type Props = { onClose: () => void };

/** Long enough that a half-typed word does not trigger a model run. */
const DEBOUNCE_MS = 180;

export function HelpPanel({ onClose }: Props) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<HelpHit[]>([]);
  const [open, setOpen] = useState<HelpArticle | null>(null);
  const [state, setState] = useState<ModelState>(modelState);
  const inputRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const categories = useMemo(helpCategories, []);

  // Start the download as soon as Help is opened, not on first keystroke, so
  // the model is usually ready by the time anyone has finished typing.
  useEffect(() => {
    void loadModel().catch(() => {
      /* keyword search carries on; the panel says so */
    });
    return onModelState(setState);
  }, []);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Immediate keyword pass, then a debounced semantic pass that supersedes it.
  useEffect(() => {
    const text = query.trim();
    if (!text) {
      setHits([]);
      return;
    }
    setHits(keywordSearch(text));

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void search(text)
        .then((results) => {
          // A blended pass that finds nothing must not wipe out usable keyword
          // hits -- it only ever replaces them with something better.
          if (!cancelled && results.length) setHits(results);
        })
        .catch(() => {
          /* keyword results stand */
        });
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, state]);

  const openArticle = useCallback((article: HelpArticle) => {
    setOpen(article);
    bodyRef.current?.scrollTo({ top: 0 });
  }, []);

  const navigate = useCallback((id: string) => {
    const target = articleById(id);
    if (target) {
      setOpen(target);
      bodyRef.current?.scrollTo({ top: 0 });
    }
  }, []);

  const searching = query.trim().length > 0;

  return (
    <aside className="help-panel" role="complementary" aria-label="Help">
      <header className="help-head">
        <h2 className="help-title">Help</h2>
        <button
          type="button"
          className="btn-ghost btn-xs help-close"
          onClick={onClose}
          aria-label="Close help"
          title="Close help (Escape)"
        >
          ✕
        </button>
      </header>

      <div className="help-search">
        <input
          ref={inputRef}
          type="search"
          className="field-input"
          placeholder="Describe the problem…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(null);
          }}
          aria-label="Search help"
        />
      </div>

      <p className="help-status muted">
        {state === "loading" && "Loading the search model — word matching until it is ready."}
        {state === "failed" && "Search model unavailable — using word matching."}
        {state === "ready" && "Type what is going wrong, in your own words."}
        {state === "idle" && "Type what is going wrong, in your own words."}
      </p>

      <div className="help-body" ref={bodyRef}>
        {open && (
          <article className="help-article">
            <button type="button" className="help-back" onClick={() => setOpen(null)}>
              ‹ {searching ? "Back to results" : "All topics"}
            </button>
            <h3 className="help-article-title">{open.title}</h3>
            <p className="help-article-cat muted">{open.category}</p>
            <div className="help-article-body">
              <HelpMarkdown markdown={open.body} onNavigate={navigate} />
            </div>
          </article>
        )}

        {!open && searching && hits.length > 0 && (
          <ul className="help-results">
            {hits.map((hit) => (
              <li key={hit.article.id}>
                <button
                  type="button"
                  className="help-result"
                  onClick={() => openArticle(hit.article)}
                >
                  <span className="help-result-title">{hit.article.title}</span>
                  <span className="help-result-snippet">{snippet(hit.article)}</span>
                  <span className="help-result-cat">{hit.article.category}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {!open && searching && hits.length === 0 && (
          <div className="help-empty">
            <p>
              Nothing matched that closely. Try describing what you were doing when it went
              wrong, or browse the topics below.
            </p>
            <HelpBrowse categories={categories} onOpen={openArticle} />
          </div>
        )}

        {!open && !searching && <HelpBrowse categories={categories} onOpen={openArticle} />}
      </div>
    </aside>
  );
}

function HelpBrowse({
  categories,
  onOpen,
}: {
  categories: { name: string; articles: HelpArticle[] }[];
  onOpen: (a: HelpArticle) => void;
}) {
  return (
    <div className="help-browse">
      {categories.map((group) => (
        <section key={group.name} className="help-cat">
          <h3 className="help-cat-title">{group.name}</h3>
          <ul className="help-cat-list">
            {group.articles.map((article) => (
              <li key={article.id}>
                <button type="button" className="help-cat-link" onClick={() => onOpen(article)}>
                  {article.title}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export default HelpPanel;
