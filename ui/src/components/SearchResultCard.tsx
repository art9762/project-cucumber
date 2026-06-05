import { motion } from "framer-motion";

import { Card } from "./Card";
import { TierBadge } from "./TierBadge";
import type { SearchHitOut } from "../api/types";

export interface SearchResultCardProps {
  hit: SearchHitOut;
  /** 1-based position in the ranked list. */
  rank: number;
  /** Stagger index for the mount animation. */
  index: number;
}

/** Clamp a 0..1 similarity to a whole-number percentage. */
function toPercent(similarity: number): number {
  const pct = Math.round(similarity * 100);
  if (pct < 0) return 0;
  if (pct > 100) return 100;
  return pct;
}

export function SearchResultCard({ hit, rank, index }: SearchResultCardProps) {
  const percent = toPercent(hit.similarity);

  return (
    <motion.li
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut", delay: index * 0.04 }}
    >
      <Card static className="transition-colors hover:border-accent/40">
        <div className="flex items-start gap-4">
          <span className="mt-0.5 w-7 shrink-0 text-right font-mono text-sm font-semibold tabular-nums text-muted">
            {rank}
          </span>

          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-3">
              <a
                href={hit.url}
                target="_blank"
                rel="noopener noreferrer"
                className="truncate text-sm font-semibold text-fg transition-colors hover:text-accent"
                title={hit.title}
              >
                {hit.title}
              </a>
              <TierBadge tier={hit.tier} className="shrink-0" />
            </div>

            <a
              href={hit.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-0.5 block truncate text-xs text-muted/80 transition-colors hover:text-muted"
              title={hit.url}
            >
              {hit.url}
            </a>

            <div className="mt-3 flex items-center gap-3">
              <div
                className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2"
                role="progressbar"
                aria-valuenow={percent}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="similarity"
              >
                <motion.div
                  className="h-full rounded-full bg-accent"
                  initial={{ width: 0 }}
                  animate={{ width: `${percent}%` }}
                  transition={{
                    duration: 0.5,
                    ease: "easeOut",
                    delay: index * 0.04 + 0.1,
                  }}
                />
              </div>
              <span className="w-12 shrink-0 text-right text-xs font-semibold tabular-nums text-fg">
                {percent}%
              </span>
            </div>

            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
              <span title="cosine distance">
                distance{" "}
                <span className="font-mono tabular-nums text-muted/90">
                  {hit.distance.toFixed(4)}
                </span>
              </span>
              {hit.coefficient !== null && (
                <span title="scoring coefficient">
                  coefficient{" "}
                  <span className="font-mono tabular-nums text-muted/90">
                    {hit.coefficient.toFixed(2)}
                  </span>
                </span>
              )}
            </div>
          </div>
        </div>
      </Card>
    </motion.li>
  );
}
