/**
 * Renders the per-criterion `scores` object of a tierlist item as a clean
 * grid of labelled bars. Scores are assumed to be on a 0–10 scale; the bar
 * width is clamped so out-of-range values still render sensibly.
 */
export interface ScoreBreakdownProps {
  scores: Record<string, number> | null;
}

/** Turn a snake_case / kebab key into a Title Case label. */
function humanize(key: string): string {
  return key
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function barWidth(value: number): string {
  const pct = Math.max(0, Math.min(100, (value / 10) * 100));
  return `${pct}%`;
}

export function ScoreBreakdown({ scores }: ScoreBreakdownProps) {
  const entries = scores ? Object.entries(scores) : [];

  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted">No score breakdown available.</p>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs font-medium uppercase tracking-wide text-muted">
              {humanize(key)}
            </span>
            <span className="text-sm font-semibold tabular-nums text-fg">
              {value.toFixed(2)}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
            <div
              className="h-full rounded-full bg-accent"
              style={{ width: barWidth(value) }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
