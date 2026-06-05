import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import type { TierItemOut } from "../api/types";
import { ScoreBreakdown } from "./ScoreBreakdown";
import { TierBadge } from "./TierBadge";

/**
 * One tierlist row. Collapsed it shows tier, title (external link), category
 * and coefficient. Clicking the row toggles an expanded panel with the
 * per-criterion score breakdown.
 */
export interface TierlistRowProps {
  item: TierItemOut;
  /** Resolved human-readable category title, if known. */
  categoryTitle?: string;
}

function formatCoefficient(value: number | null): string {
  if (value === null) return "—";
  return value.toFixed(3);
}

function ExternalLinkIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className="shrink-0"
    >
      <path
        d="M14 5h5v5M19 5l-8 8M11 5H6a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function TierlistRow({ item, categoryTitle }: TierlistRowProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface/60">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-2/40"
      >
        <TierBadge tier={item.tier} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-fg">
              {item.title}
            </span>
          </div>
          {categoryTitle && (
            <span className="block truncate text-xs text-muted">
              {categoryTitle}
            </span>
          )}
        </div>
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="flex shrink-0 items-center gap-1 text-xs text-muted transition-colors hover:text-accent"
          title={item.url}
        >
          <span className="hidden sm:inline">open</span>
          <ExternalLinkIcon />
        </a>
        <div className="shrink-0 text-right">
          <div className="text-[10px] uppercase tracking-wide text-muted">
            coef
          </div>
          <div className="text-sm font-semibold tabular-nums text-fg">
            {formatCoefficient(item.coefficient)}
          </div>
        </div>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
          className={
            "shrink-0 text-muted transition-transform " +
            (expanded ? "rotate-180" : "")
          }
        >
          <path
            d="M6 9l6 6 6-6"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden border-t border-border"
          >
            <div className="px-4 py-4">
              <ScoreBreakdown scores={item.scores} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
