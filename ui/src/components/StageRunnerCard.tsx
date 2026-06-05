import { AnimatePresence, motion } from "framer-motion";
import { useState, type ReactNode } from "react";
import type { UseMutationResult } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { Button } from "./Button";
import { Card } from "./Card";
import { Spinner } from "./Spinner";

/**
 * Generic "stage runner" card for a single pipeline pass (classify / score /
 * research / embed). Owns the Run button, pending Spinner, a results panel
 * rendered by the caller, friendly 403 handling and a collapsible errors list.
 *
 * `TOut` is the stage's RunOut result; `TParams` is the mutation param shape.
 * The caller supplies the params (built from its own controls), how to render
 * the stats, and how to extract the `errors[]` array from a result.
 */
export interface StageRunnerCardProps<TOut, TParams> {
  title: string;
  description: string;
  /** The useMutation result returned by the stage hook. */
  mutation: UseMutationResult<TOut, unknown, TParams>;
  /** Builds the param object passed to `mutation.mutate`. */
  buildParams: () => TParams;
  /** Renders the success stats panel for a completed run. */
  renderStats: (data: TOut) => ReactNode;
  /** Pulls the errors[] array out of a result (empty when none). */
  selectErrors: (data: TOut) => string[];
  /** Extra controls (limit input, selects…) rendered above the Run button. */
  controls?: ReactNode;
  /** When false the user is not an admin: Run is disabled with a hint. */
  canRun?: boolean;
}

export function StageRunnerCard<TOut, TParams>({
  title,
  description,
  mutation,
  buildParams,
  renderStats,
  selectErrors,
  controls,
  canRun = true,
}: StageRunnerCardProps<TOut, TParams>) {
  const [showErrors, setShowErrors] = useState(false);
  const { isPending, isError, error, data } = mutation;

  const forbidden = error instanceof ApiError && error.status === 403;
  const errorMessage = forbidden
    ? "This action requires an admin account."
    : error instanceof ApiError
      ? error.status === 0
        ? "Could not reach the server."
        : error.message
      : "Run failed. Please try again.";

  const errors = data ? selectErrors(data) : [];

  return (
    <Card title={title}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-muted">{description}</p>

        {controls && <div className="flex flex-col gap-3">{controls}</div>}

        <div className="flex items-center gap-3">
          <Button
            onClick={() => mutation.mutate(buildParams())}
            disabled={isPending || !canRun}
            title={canRun ? undefined : "Requires admin"}
          >
            {isPending ? "Running…" : "Run"}
          </Button>
          {isPending && <Spinner size={18} label="Working…" />}
          {!canRun && !isPending && (
            <span className="text-xs text-muted">Admins only</span>
          )}
        </div>

        {isError && (
          <p
            className="rounded-xl border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger"
            role="alert"
          >
            {errorMessage}
          </p>
        )}

        <AnimatePresence mode="wait">
          {data && !isPending && (
            <motion.div
              key="stats"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="flex flex-col gap-3 rounded-xl border border-border bg-surface-2/40 p-4"
            >
              {renderStats(data)}

              {errors.length > 0 && (
                <div className="flex flex-col gap-2">
                  <button
                    type="button"
                    onClick={() => setShowErrors((v) => !v)}
                    className="self-start text-xs font-medium text-amber-300 hover:underline"
                  >
                    {showErrors ? "Hide" : "Show"} {errors.length}{" "}
                    {errors.length === 1 ? "error" : "errors"}
                  </button>
                  {showErrors && (
                    <ul className="flex flex-col gap-1 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                      {errors.map((err, i) => (
                        <li
                          key={i}
                          className="break-words font-mono text-xs text-amber-200/90"
                        >
                          {err}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </Card>
  );
}

/** Small labelled number chip used inside stage stats panels. */
export function StatChip({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  const toneClass =
    tone === "good"
      ? "text-emerald-300"
      : tone === "warn"
        ? "text-amber-300"
        : tone === "bad"
          ? "text-rose-300"
          : "text-fg";
  return (
    <div className="flex flex-col gap-0.5 rounded-lg bg-surface/60 px-3 py-2">
      <span className="text-xs uppercase tracking-wide text-muted">{label}</span>
      <span className={`text-lg font-semibold ${toneClass}`}>{value}</span>
    </div>
  );
}
