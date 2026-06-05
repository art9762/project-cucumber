import { motion } from "framer-motion";
import { useState, type FormEvent } from "react";

import { useSearch } from "../api/hooks";
import type { SearchHitOut } from "../api/types";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { Input } from "../components/Input";
import { SearchResultCard } from "../components/SearchResultCard";
import { Spinner } from "../components/Spinner";

const LIMIT_OPTIONS = [10, 20, 50] as const;
type Limit = (typeof LIMIT_OPTIONS)[number];

export function SearchPage() {
  const search = useSearch();

  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState<Limit>(10);
  /** The query string backing the currently-displayed results. */
  const [activeQuery, setActiveQuery] = useState<string | null>(null);

  const results: SearchHitOut[] = search.data ?? [];

  function runSearch(nextLimit: Limit) {
    const trimmed = query.trim();
    if (!trimmed) return;
    setActiveQuery(trimmed);
    search.mutate({ query: trimmed, limit: nextLimit });
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    runSearch(limit);
  }

  function onLimitChange(next: Limit) {
    setLimit(next);
    // Re-run immediately if results are already on screen.
    if (activeQuery !== null) runSearch(next);
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold text-fg">Semantic search</h1>
        <p className="mt-1 text-sm text-muted">
          Describe an idea in your own words — get the closest items from the
          base by meaning, not keywords.
        </p>
      </header>

      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <Input
              label="Query"
              value={query}
              autoFocus
              placeholder="e.g. lightweight on-device vector database"
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <Button
            type="submit"
            disabled={search.isPending || query.trim().length === 0}
            className="shrink-0"
          >
            {search.isPending ? "Searching…" : "Search"}
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-muted">
            Results
          </span>
          <div className="inline-flex overflow-hidden rounded-xl border border-border">
            {LIMIT_OPTIONS.map((opt) => {
              const active = opt === limit;
              return (
                <button
                  key={opt}
                  type="button"
                  onClick={() => onLimitChange(opt)}
                  className={
                    "h-8 px-3 text-sm transition-colors " +
                    (active
                      ? "bg-accent/15 font-semibold text-accent"
                      : "text-muted hover:bg-surface-2/60 hover:text-fg")
                  }
                  aria-pressed={active}
                >
                  {opt}
                </button>
              );
            })}
          </div>
        </div>
      </form>

      <Results
        isPending={search.isPending}
        isError={search.isError}
        error={search.error}
        results={results}
        activeQuery={activeQuery}
        onRetry={() => runSearch(limit)}
      />
    </div>
  );
}

interface ResultsProps {
  isPending: boolean;
  isError: boolean;
  error: unknown;
  results: SearchHitOut[];
  activeQuery: string | null;
  onRetry: () => void;
}

function Results({
  isPending,
  isError,
  error,
  results,
  activeQuery,
  onRetry,
}: ResultsProps) {
  if (isPending) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size={24} label="Searching by meaning…" />
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState error={error} onRetry={onRetry} title="Search failed" />
    );
  }

  // Nothing searched yet — friendly intro.
  if (activeQuery === null) {
    return (
      <EmptyState
        title="Start with an idea"
        description="Type a description of what you're looking for and hit Search. We compare meaning using embeddings, so synonyms and paraphrases work too."
      />
    );
  }

  if (results.length === 0) {
    return (
      <EmptyState
        title="No matches"
        description={
          <>
            Nothing in the base came close to{" "}
            <span className="font-medium text-fg">“{activeQuery}”</span>. Try
            rephrasing or broadening the idea.
          </>
        }
      />
    );
  }

  return (
    <section className="flex flex-col gap-2">
      <motion.p
        key={activeQuery + results.length}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="text-xs text-muted"
      >
        {results.length} {results.length === 1 ? "match" : "matches"} for{" "}
        <span className="font-medium text-fg">“{activeQuery}”</span>
      </motion.p>
      <ul className="flex flex-col gap-3">
        {results.map((hit, i) => (
          <SearchResultCard
            key={hit.item_id}
            hit={hit}
            rank={i + 1}
            index={i}
          />
        ))}
      </ul>
    </section>
  );
}
