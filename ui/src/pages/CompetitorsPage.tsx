import { motion } from "framer-motion";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { useCompetitors, useItemResearch } from "../api/hooks";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { ItemPicker, type PickableItem } from "../components/ItemPicker";
import { SignalMeter } from "../components/SignalMeter";
import { Spinner } from "../components/Spinner";
import { VectorCompetitorCard } from "../components/VectorCompetitorCard";

const LIMIT_OPTIONS = [5, 10, 20, 50] as const;

/** Section 1: vector "similar from our base". */
function SimilarSection({ itemId, limit }: { itemId: string; limit: number }) {
  const { data, isLoading, isError, error, refetch } = useCompetitors(
    itemId,
    limit,
  );

  let body;
  if (isLoading) {
    body = (
      <div className="flex justify-center py-8">
        <Spinner label="Finding similar ideas…" />
      </div>
    );
  } else if (isError) {
    body = <ErrorState error={error} onRetry={() => void refetch()} />;
  } else if (!data || data.length === 0) {
    body = (
      <EmptyState
        title="No similar items found"
        description="Nothing in our base is close enough to this idea. It may need embeddings first (run from the Control page)."
      />
    );
  } else {
    body = (
      <ul className="flex flex-col gap-2">
        {data.map((hit, i) => (
          <VectorCompetitorCard key={hit.item_id} hit={hit} rank={i + 1} />
        ))}
      </ul>
    );
  }

  return body;
}

/** Section 2: web research summary + competitors + sources + signals. */
function ResearchSection({ itemId }: { itemId: string }) {
  const { data, isLoading, isError, error, refetch } = useItemResearch(itemId);

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner label="Loading research…" />
      </div>
    );
  }

  if (isError) {
    // A 404 means "no research row yet" — treat that as an empty state.
    if (error instanceof ApiError && error.status === 404) {
      return (
        <EmptyState
          title="No web research yet"
          description="This idea hasn't been researched. Run a research pass from the Control page to populate competitors and a market summary."
        />
      );
    }
    return <ErrorState error={error} onRetry={() => void refetch()} />;
  }

  if (!data) {
    return <EmptyState title="No web research yet" />;
  }

  return (
    <div className="flex flex-col gap-5">
      {data.summary && (
        <p className="text-sm leading-relaxed text-fg/90">{data.summary}</p>
      )}

      <div className="grid grid-cols-2 gap-4">
        <SignalMeter label="Maturity" value={data.maturity_signal} />
        <SignalMeter label="Potential" value={data.potential_signal} />
      </div>

      <div>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
          Competitors ({data.competitors.length})
        </h4>
        {data.competitors.length === 0 ? (
          <p className="text-sm text-muted">No competitors recorded.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {data.competitors.map((c, i) => (
              <li
                key={`${c.name}-${i}`}
                className="rounded-xl border border-border bg-surface-2/50 px-4 py-3"
              >
                <div className="flex items-center justify-between gap-3">
                  {c.url ? (
                    <a
                      href={c.url}
                      target="_blank"
                      rel="noreferrer"
                      className="truncate text-sm font-medium text-fg hover:text-accent"
                      title={c.name}
                    >
                      {c.name}
                    </a>
                  ) : (
                    <span className="truncate text-sm font-medium text-fg">
                      {c.name}
                    </span>
                  )}
                </div>
                {c.note && (
                  <p className="mt-1 text-xs leading-relaxed text-muted">
                    {c.note}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {data.sources.length > 0 && (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Sources
          </h4>
          <ul className="flex flex-col gap-1">
            {data.sources.map((src, i) => (
              <li key={`${src}-${i}`}>
                <a
                  href={src}
                  target="_blank"
                  rel="noreferrer"
                  className="block truncate text-xs text-accent/90 hover:text-accent"
                  title={src}
                >
                  {src}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.model_used && (
        <p className="text-[11px] text-muted">
          Model: <span className="text-fg/70">{data.model_used}</span>
        </p>
      )}
    </div>
  );
}

export function CompetitorsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selected, setSelected] = useState<PickableItem | null>(null);
  const [limit, setLimit] = useState<number>(10);

  // Deep-link support: ?item=<id> seeds the initial selection.
  const itemParam = searchParams.get("item");
  const selectedId = selected?.itemId ?? itemParam ?? null;

  function handleSelect(item: PickableItem) {
    setSelected(item);
    const next = new URLSearchParams(searchParams);
    next.set("item", item.itemId);
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold text-fg">Competitor finder</h1>
        <p className="mt-1 text-sm text-muted">
          Pick an idea to see the closest items in our base and any web research
          on the competitive landscape.
        </p>
      </div>

      <Card title="Choose an idea">
        <ItemPicker selectedId={selectedId} onSelect={handleSelect} />
      </Card>

      {!selectedId ? (
        <EmptyState
          title="No idea selected"
          description="Search and pick an idea above to find its competitors."
        />
      ) : (
        <motion.div
          key={selectedId}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="grid grid-cols-1 gap-6 lg:grid-cols-2"
        >
          <Card
            title="Similar from our base"
            action={
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-muted">limit</span>
                {LIMIT_OPTIONS.map((opt) => (
                  <Button
                    key={opt}
                    size="sm"
                    variant={limit === opt ? "primary" : "ghost"}
                    onClick={() => setLimit(opt)}
                  >
                    {opt}
                  </Button>
                ))}
              </div>
            }
          >
            <SimilarSection itemId={selectedId} limit={limit} />
          </Card>

          <Card title="Web research">
            <ResearchSection itemId={selectedId} />
          </Card>
        </motion.div>
      )}
    </div>
  );
}
