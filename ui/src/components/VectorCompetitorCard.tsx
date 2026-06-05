import { motion } from "framer-motion";

import type { SearchHitOut } from "../api/types";
import { TierBadge } from "./TierBadge";

/**
 * Ranked "similar from our base" card for one vector SearchHitOut.
 * Unique name (VectorCompetitorCard) to avoid colliding with any web
 * CompetitorOut renderer the lead may add.
 */
export interface VectorCompetitorCardProps {
  hit: SearchHitOut;
  rank: number;
}

export function VectorCompetitorCard({ hit, rank }: VectorCompetitorCardProps) {
  const similarityPct = Math.round(Math.min(1, Math.max(0, hit.similarity)) * 100);

  return (
    <motion.li
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="flex items-center gap-3 rounded-xl border border-border bg-surface-2/50 px-4 py-3"
    >
      <span className="w-6 shrink-0 text-center text-sm font-semibold tabular-nums text-muted">
        {rank}
      </span>
      <TierBadge tier={hit.tier} />
      <div className="min-w-0 flex-1">
        <a
          href={hit.url}
          target="_blank"
          rel="noreferrer"
          className="block truncate text-sm font-medium text-fg hover:text-accent"
          title={hit.title}
        >
          {hit.title}
        </a>
        <div className="mt-0.5 flex items-center gap-3 text-xs text-muted">
          <span className="tabular-nums">{similarityPct}% similar</span>
          {hit.coefficient !== null && (
            <span className="tabular-nums">
              coeff {hit.coefficient.toFixed(2)}
            </span>
          )}
        </div>
      </div>
    </motion.li>
  );
}
