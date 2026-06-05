import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";

import { useCategories, useTierlist } from "../api/hooks";
import type { CategoryTreeNode, TierItemOut } from "../api/types";
import { Card } from "../components/Card";
import { CategoryTree } from "../components/CategoryTree";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { Spinner } from "../components/Spinner";
import { TierlistRow } from "../components/TierlistRow";

const TIER_OPTIONS = ["all", "S", "A", "B", "C", "D"] as const;
const LIMIT_OPTIONS = [25, 50, 100, 250] as const;

/** Flatten the category tree into an id → title map for row labels. */
function buildTitleMap(nodes: CategoryTreeNode[]): Map<string, string> {
  const map = new Map<string, string>();
  const walk = (list: CategoryTreeNode[]) => {
    for (const node of list) {
      map.set(node.id, node.title);
      if (node.children.length > 0) walk(node.children);
    }
  };
  walk(nodes);
  return map;
}

function sortByCoefficient(items: TierItemOut[]): TierItemOut[] {
  return [...items].sort((a, b) => {
    const av = a.coefficient ?? -Infinity;
    const bv = b.coefficient ?? -Infinity;
    return bv - av;
  });
}

export function TierlistPage() {
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [tier, setTier] = useState<(typeof TIER_OPTIONS)[number]>("all");
  const [limit, setLimit] = useState<number>(50);

  const categories = useCategories();
  const tierlist = useTierlist({
    tier: tier === "all" ? undefined : tier,
    category_id: categoryId ?? undefined,
    limit,
  });

  const titleMap = useMemo(
    () => buildTitleMap(categories.data ?? []),
    [categories.data],
  );

  const rows = useMemo(
    () => sortByCoefficient(tierlist.data ?? []),
    [tierlist.data],
  );

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-fg">Tierlist</h2>
        <p className="text-sm text-muted">
          Browse ranked items by category and tier.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
        {/* Category tree */}
        <div className="lg:sticky lg:top-6 lg:self-start">
          <Card title="Categories">
            {categories.isLoading ? (
              <div className="flex justify-center py-6">
                <Spinner label="Loading…" />
              </div>
            ) : categories.isError ? (
              <ErrorState
                error={categories.error}
                onRetry={() => void categories.refetch()}
                title="Could not load categories"
              />
            ) : (categories.data?.length ?? 0) === 0 ? (
              <p className="text-sm text-muted">No categories yet.</p>
            ) : (
              <CategoryTree
                nodes={categories.data ?? []}
                selectedId={categoryId}
                onSelect={setCategoryId}
              />
            )}
          </Card>
        </div>

        {/* Main column */}
        <div className="space-y-4">
          {/* Filter bar */}
          <Card static>
            <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
              <div className="flex flex-col gap-1.5">
                <span className="text-xs font-medium uppercase tracking-wide text-muted">
                  Tier
                </span>
                <div className="flex gap-1">
                  {TIER_OPTIONS.map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setTier(opt)}
                      className={
                        "h-8 min-w-9 rounded-lg border px-2.5 text-xs font-semibold transition-colors " +
                        (tier === opt
                          ? "border-accent/50 bg-accent/15 text-accent"
                          : "border-border bg-surface-2 text-muted hover:text-fg")
                      }
                    >
                      {opt === "all" ? "All" : opt}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="text-xs font-medium uppercase tracking-wide text-muted">
                  Limit
                </span>
                <div className="flex gap-1">
                  {LIMIT_OPTIONS.map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setLimit(opt)}
                      className={
                        "h-8 min-w-9 rounded-lg border px-2.5 text-xs font-semibold transition-colors " +
                        (limit === opt
                          ? "border-accent/50 bg-accent/15 text-accent"
                          : "border-border bg-surface-2 text-muted hover:text-fg")
                      }
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              </div>

              <div className="ml-auto self-center text-xs text-muted">
                {tierlist.isFetching ? (
                  <Spinner label="Loading…" />
                ) : (
                  `${rows.length} item${rows.length === 1 ? "" : "s"}`
                )}
              </div>
            </div>
          </Card>

          {/* Results */}
          {tierlist.isLoading ? (
            <div className="flex justify-center py-12">
              <Spinner size={28} label="Loading tierlist…" />
            </div>
          ) : tierlist.isError ? (
            <ErrorState
              error={tierlist.error}
              onRetry={() => void tierlist.refetch()}
              title="Could not load tierlist"
            />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No items match these filters"
              description="Try clearing the category or tier filter, or raise the limit."
            />
          ) : (
            <motion.div layout className="flex flex-col gap-2">
              <AnimatePresence initial={false}>
                {rows.map((item) => (
                  <motion.div
                    key={item.item_id}
                    layout
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.18 }}
                  >
                    <TierlistRow
                      item={item}
                      categoryTitle={
                        item.category_id
                          ? titleMap.get(item.category_id)
                          : undefined
                      }
                    />
                  </motion.div>
                ))}
              </AnimatePresence>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}
