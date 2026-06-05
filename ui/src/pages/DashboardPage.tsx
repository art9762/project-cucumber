import { motion } from "framer-motion";
import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { useHealth, useResearchList, useTierlist } from "../api/hooks";
import type { ItemResearchOut, TierItemOut } from "../api/types";
import { Card } from "../components/Card";
import { ErrorState } from "../components/ErrorState";
import { Spinner } from "../components/Spinner";
import { TierBadge } from "../components/TierBadge";

const TIER_ORDER = ["S", "A", "B", "C", "D"] as const;

/** Pull a large slice so dashboard counts reflect the whole corpus. */
const DASHBOARD_LIMIT = 1000;

interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: string;
  index: number;
}

function StatCard({ label, value, hint, index }: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut", delay: index * 0.04 }}
    >
      <div className="rounded-2xl border border-border bg-surface/70 p-5 shadow-lg shadow-black/20 backdrop-blur-sm">
        <div className="text-xs font-medium uppercase tracking-wide text-muted">
          {label}
        </div>
        <div className="mt-2 text-3xl font-semibold tabular-nums text-fg">
          {value}
        </div>
        {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
      </div>
    </motion.div>
  );
}

function HealthPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="flex items-center gap-2 text-sm text-fg">
      <span
        className={
          "h-2.5 w-2.5 rounded-full " + (ok ? "bg-emerald-400" : "bg-danger")
        }
      />
      {label}
    </span>
  );
}

function countByTier(items: TierItemOut[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of items) {
    const key = item.tier?.toUpperCase() ?? "";
    if (!key) continue;
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}

function countResearched(items: ItemResearchOut[]): {
  researched: number;
  withCompetitors: number;
} {
  let withCompetitors = 0;
  for (const item of items) {
    if (item.competitors.length > 0) withCompetitors += 1;
  }
  return { researched: items.length, withCompetitors };
}

export function DashboardPage() {
  const health = useHealth();
  const tierlist = useTierlist({ limit: DASHBOARD_LIMIT });
  const research = useResearchList({ limit: DASHBOARD_LIMIT });

  const tierCounts = useMemo(
    () => countByTier(tierlist.data ?? []),
    [tierlist.data],
  );
  const researchStats = useMemo(
    () => countResearched(research.data ?? []),
    [research.data],
  );

  const totalItems = tierlist.data?.length ?? 0;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-fg">Dashboard</h2>
        <p className="text-sm text-muted">
          At-a-glance overview of the analysis corpus.
        </p>
      </div>

      <Card title="System health">
        {health.isLoading ? (
          <Spinner label="Checking…" />
        ) : health.isError ? (
          <ErrorState
            error={health.error}
            onRetry={() => void health.refetch()}
            title="Health check failed"
          />
        ) : (
          <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
            <HealthPill
              ok={health.data?.status === "ok"}
              label={`Status: ${health.data?.status ?? "unknown"}`}
            />
            <HealthPill
              ok={Boolean(health.data?.database)}
              label={`Database ${health.data?.database ? "connected" : "down"}`}
            />
            <HealthPill
              ok={Boolean(health.data?.trinity_configured)}
              label={`Trinity ${
                health.data?.trinity_configured
                  ? "configured"
                  : "not configured"
              }`}
            />
          </div>
        )}
      </Card>

      {tierlist.isError ? (
        <ErrorState
          error={tierlist.error}
          onRetry={() => void tierlist.refetch()}
          title="Could not load tierlist stats"
        />
      ) : tierlist.isLoading ? (
        <div className="flex justify-center py-10">
          <Spinner size={28} label="Loading stats…" />
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard index={0} label="Total items" value={totalItems} />
            <StatCard
              index={1}
              label="Researched"
              value={research.isLoading ? "…" : researchStats.researched}
              hint={
                research.isLoading
                  ? undefined
                  : `${researchStats.withCompetitors} with competitors`
              }
            />
            <StatCard
              index={2}
              label="Tier S + A"
              value={(tierCounts.S ?? 0) + (tierCounts.A ?? 0)}
              hint="top-rated items"
            />
            <StatCard
              index={3}
              label="Unscored"
              value={
                totalItems -
                TIER_ORDER.reduce((sum, t) => sum + (tierCounts[t] ?? 0), 0)
              }
              hint="no tier assigned"
            />
          </div>

          <Card title="Distribution by tier">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
              {TIER_ORDER.map((tier, i) => (
                <motion.div
                  key={tier}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, delay: i * 0.04 }}
                  className="flex flex-col items-center gap-2 rounded-xl border border-border bg-surface-2/40 py-4"
                >
                  <TierBadge tier={tier} />
                  <span className="text-2xl font-semibold tabular-nums text-fg">
                    {tierCounts[tier] ?? 0}
                  </span>
                </motion.div>
              ))}
            </div>
          </Card>
        </>
      )}

      <Card title="Quick links">
        <div className="flex flex-wrap gap-3">
          <Link
            to="/tierlist"
            className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-fg transition-colors hover:bg-accent/90"
          >
            Browse tierlist
          </Link>
          <Link
            to="/search"
            className="rounded-xl border border-border bg-surface-2 px-4 py-2 text-sm font-medium text-fg transition-colors hover:bg-surface-2/70"
          >
            Semantic search
          </Link>
          <Link
            to="/control"
            className="rounded-xl border border-border bg-surface-2 px-4 py-2 text-sm font-medium text-fg transition-colors hover:bg-surface-2/70"
          >
            Control panel
          </Link>
        </div>
      </Card>
    </div>
  );
}
