/**
 * Small labelled meter for a 0..1 signal (maturity / potential).
 * Null/undefined renders a muted "n/a". Unique name to avoid collisions.
 */
export interface SignalMeterProps {
  label: string;
  /** Expected range 0..1; clamped for display. Null → "n/a". */
  value: number | null | undefined;
  className?: string;
}

export function SignalMeter({ label, value, className = "" }: SignalMeterProps) {
  const hasValue = typeof value === "number" && Number.isFinite(value);
  const clamped = hasValue ? Math.min(1, Math.max(0, value)) : 0;
  const pct = Math.round(clamped * 100);

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted">
          {label}
        </span>
        <span className="text-xs font-semibold tabular-nums text-fg">
          {hasValue ? `${pct}%` : "n/a"}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-accent transition-all"
          style={{ width: hasValue ? `${pct}%` : "0%" }}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}
