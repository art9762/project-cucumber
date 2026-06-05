import { useState } from "react";

import { ApiError } from "../api/client";
import {
  useApproveCategory,
  usePendingCategories,
  useRejectCategory,
  useRunClassify,
  useRunEmbed,
  useRunResearch,
  useRunScore,
} from "../api/hooks";
import type {
  CategoryOut,
  ClassifyRunOut,
  EmbedRunOut,
  ResearchRunOut,
  RunLimitParams,
  RunResearchParams,
  ScoreRunOut,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { Input } from "../components/Input";
import { Spinner } from "../components/Spinner";
import { StageRunnerCard, StatChip } from "../components/StageRunnerCard";
import { TierBadge } from "../components/TierBadge";

const TIER_OPTIONS = ["S", "A", "B", "C", "D"] as const;

/** Parse a limit text field into a number | undefined (blank = no limit). */
function parseLimit(raw: string): number | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return undefined;
  const n = Number(trimmed);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : undefined;
}

export function ControlPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
      <header>
        <h1 className="text-lg font-semibold text-fg">Pipeline control</h1>
        <p className="mt-1 text-sm text-muted">
          Run the analysis stages and moderate the category tree. Stage runs and
          approvals require an admin account.
        </p>
        {!isAdmin && (
          <p className="mt-3 inline-flex rounded-xl border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
            You are signed in as a viewer. Run and moderation actions are
            disabled and will be rejected by the server.
          </p>
        )}
      </header>

      <section className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <ClassifyRunner canRun={isAdmin} />
        <ScoreRunner canRun={isAdmin} />
        <ResearchRunner canRun={isAdmin} />
        <EmbedRunner canRun={isAdmin} />
      </section>

      <CategoryApproval canRun={isAdmin} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stage runners
// ---------------------------------------------------------------------------

function ClassifyRunner({ canRun }: { canRun: boolean }) {
  const mutation = useRunClassify();
  const [limit, setLimit] = useState("");

  return (
    <StageRunnerCard<ClassifyRunOut, RunLimitParams | void>
      title="Classify"
      description="Assign items to categories and suggest new ones."
      mutation={mutation}
      canRun={canRun}
      buildParams={() => ({ limit: parseLimit(limit) })}
      selectErrors={(d) => d.errors}
      controls={
        <Input
          label="Limit (optional)"
          type="number"
          min={1}
          placeholder="all pending"
          value={limit}
          onChange={(e) => setLimit(e.target.value)}
        />
      }
      renderStats={(d) => (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <StatChip label="Seen" value={d.seen} />
          <StatChip label="Classified" value={d.classified} tone="good" />
          <StatChip label="Suggested" value={d.suggested} />
          <StatChip
            label="Failed"
            value={d.failed}
            tone={d.failed > 0 ? "bad" : "default"}
          />
        </div>
      )}
    />
  );
}

function ScoreRunner({ canRun }: { canRun: boolean }) {
  const mutation = useRunScore();
  const [limit, setLimit] = useState("");

  return (
    <StageRunnerCard<ScoreRunOut, RunLimitParams | void>
      title="Score"
      description="Compute tier and coefficient for classified items."
      mutation={mutation}
      canRun={canRun}
      buildParams={() => ({ limit: parseLimit(limit) })}
      selectErrors={(d) => d.errors}
      controls={
        <Input
          label="Limit (optional)"
          type="number"
          min={1}
          placeholder="all"
          value={limit}
          onChange={(e) => setLimit(e.target.value)}
        />
      }
      renderStats={(d) => (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <StatChip label="Seen" value={d.seen} />
            <StatChip label="Scored" value={d.scored} tone="good" />
            <StatChip label="Escalated" value={d.escalated} tone="warn" />
            <StatChip
              label="Failed"
              value={d.failed}
              tone={d.failed > 0 ? "bad" : "default"}
            />
          </div>
          <TierCounts counts={d.tier_counts} />
        </div>
      )}
    />
  );
}

function TierCounts({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  if (entries.length === 0) return null;
  // Show known tiers first in canonical order, then any extras.
  const ordered = [
    ...TIER_OPTIONS.filter((t) => t in counts).map(
      (t) => [t, counts[t]] as const,
    ),
    ...entries.filter(([k]) => !(TIER_OPTIONS as readonly string[]).includes(k)),
  ];
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs uppercase tracking-wide text-muted">Tiers</span>
      {ordered.map(([tier, count]) => (
        <span key={tier} className="inline-flex items-center gap-1.5">
          <TierBadge tier={tier} />
          <span className="text-sm text-fg">{count}</span>
        </span>
      ))}
    </div>
  );
}

function ResearchRunner({ canRun }: { canRun: boolean }) {
  const mutation = useRunResearch();
  const [limit, setLimit] = useState("");
  const [minTier, setMinTier] = useState<string>("");
  const [minCoefficient, setMinCoefficient] = useState("");

  return (
    <StageRunnerCard<ResearchRunOut, RunResearchParams | void>
      title="Research"
      description="Run web research to find competitors and signals."
      mutation={mutation}
      canRun={canRun}
      buildParams={() => {
        const coef = Number(minCoefficient.trim());
        return {
          limit: parseLimit(limit),
          min_tier: minTier || undefined,
          min_coefficient:
            minCoefficient.trim() && Number.isFinite(coef) ? coef : undefined,
        };
      }}
      selectErrors={(d) => d.errors}
      controls={
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Input
            label="Limit"
            type="number"
            min={1}
            placeholder="all"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="research-min-tier"
              className="text-xs font-medium uppercase tracking-wide text-muted"
            >
              Min tier
            </label>
            <select
              id="research-min-tier"
              value={minTier}
              onChange={(e) => setMinTier(e.target.value)}
              className="h-10 rounded-xl border border-border bg-surface-2 px-3 text-sm text-fg transition-colors focus:border-accent focus-visible:outline-none"
            >
              <option value="">any</option>
              {TIER_OPTIONS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <Input
            label="Min coef."
            type="number"
            step="0.01"
            placeholder="any"
            value={minCoefficient}
            onChange={(e) => setMinCoefficient(e.target.value)}
          />
        </div>
      }
      renderStats={(d) => (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <StatChip label="Seen" value={d.seen} />
          <StatChip label="Researched" value={d.researched} tone="good" />
          <StatChip label="Competitors" value={d.competitors_found} />
          <StatChip
            label="Failed"
            value={d.failed}
            tone={d.failed > 0 ? "bad" : "default"}
          />
        </div>
      )}
    />
  );
}

function EmbedRunner({ canRun }: { canRun: boolean }) {
  const mutation = useRunEmbed();
  const [limit, setLimit] = useState("");

  return (
    <StageRunnerCard<EmbedRunOut, RunLimitParams | void>
      title="Embed"
      description="Generate vector embeddings for semantic search."
      mutation={mutation}
      canRun={canRun}
      buildParams={() => ({ limit: parseLimit(limit) })}
      selectErrors={(d) => d.errors}
      controls={
        <Input
          label="Limit (optional)"
          type="number"
          min={1}
          placeholder="all"
          value={limit}
          onChange={(e) => setLimit(e.target.value)}
        />
      }
      renderStats={(d) => (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <StatChip label="Seen" value={d.seen} />
            <StatChip label="Embedded" value={d.embedded} tone="good" />
            <StatChip
              label="Failed"
              value={d.failed}
              tone={d.failed > 0 ? "bad" : "default"}
            />
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
            <span>
              Model:{" "}
              <span className="font-mono text-fg">{d.model ?? "—"}</span>
            </span>
            <span>
              Dim: <span className="font-mono text-fg">{d.dim ?? "—"}</span>
            </span>
          </div>
        </div>
      )}
    />
  );
}

// ---------------------------------------------------------------------------
// Category approval
// ---------------------------------------------------------------------------

function CategoryApproval({ canRun }: { canRun: boolean }) {
  const pending = usePendingCategories();
  const approve = useApproveCategory();
  const reject = useRejectCategory();
  const [actionError, setActionError] = useState<string | null>(null);

  function handle(mutate: (id: string) => void, id: string) {
    setActionError(null);
    mutate(id);
  }

  // Surface a friendly 403 from either mutation.
  const forbidden =
    (approve.error instanceof ApiError && approve.error.status === 403) ||
    (reject.error instanceof ApiError && reject.error.status === 403);

  return (
    <Card title="Category approval">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-muted">
          Suggested categories awaiting moderation. Approving adds them to the
          live tree; rejecting discards them.
        </p>

        {(forbidden || actionError) && (
          <p
            className="rounded-xl border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger"
            role="alert"
          >
            {forbidden
              ? "Moderation requires an admin account."
              : actionError}
          </p>
        )}

        <PendingList
          pending={pending}
          canRun={canRun}
          isBusy={approve.isPending || reject.isPending}
          pendingApproveId={approve.isPending ? approve.variables : undefined}
          pendingRejectId={reject.isPending ? reject.variables : undefined}
          onApprove={(id) => handle(approve.mutate, id)}
          onReject={(id) => handle(reject.mutate, id)}
        />
      </div>
    </Card>
  );
}

interface PendingListProps {
  pending: ReturnType<typeof usePendingCategories>;
  canRun: boolean;
  isBusy: boolean;
  pendingApproveId?: string;
  pendingRejectId?: string;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}

function PendingList({
  pending,
  canRun,
  isBusy,
  pendingApproveId,
  pendingRejectId,
  onApprove,
  onReject,
}: PendingListProps) {
  if (pending.isLoading) {
    return (
      <div className="flex justify-center py-10">
        <Spinner size={22} label="Loading pending categories…" />
      </div>
    );
  }

  if (pending.isError) {
    return (
      <ErrorState
        error={pending.error}
        onRetry={() => void pending.refetch()}
        title="Could not load categories"
      />
    );
  }

  const items: CategoryOut[] = pending.data ?? [];
  if (items.length === 0) {
    return (
      <EmptyState
        title="Nothing pending"
        description="No suggested categories are waiting for review."
      />
    );
  }

  return (
    <ul className="flex flex-col divide-y divide-border overflow-hidden rounded-xl border border-border">
      {items.map((cat) => (
        <li
          key={cat.id}
          className="flex items-center justify-between gap-4 bg-surface-2/30 px-4 py-3"
        >
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-fg">
              {cat.title}
            </div>
            <div className="truncate font-mono text-xs text-muted">
              {cat.slug}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={!canRun || isBusy}
              onClick={() => onApprove(cat.id)}
            >
              {pendingApproveId === cat.id ? "…" : "Approve"}
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={!canRun || isBusy}
              onClick={() => onReject(cat.id)}
            >
              {pendingRejectId === cat.id ? "…" : "Reject"}
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
