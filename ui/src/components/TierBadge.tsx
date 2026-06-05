/** Colored badge for a tier letter (S/A/B/C/D). Unknown/null → neutral. */
export interface TierBadgeProps {
  tier: string | null | undefined;
  className?: string;
}

const TIER_STYLES: Record<string, string> = {
  S: "bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/40",
  A: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  B: "bg-sky-500/15 text-sky-300 border-sky-500/40",
  C: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  D: "bg-rose-500/15 text-rose-300 border-rose-500/40",
};

const NEUTRAL = "bg-surface-2 text-muted border-border";

export function TierBadge({ tier, className = "" }: TierBadgeProps) {
  const key = tier?.toUpperCase() ?? "";
  const style = TIER_STYLES[key] ?? NEUTRAL;
  return (
    <span
      className={
        "inline-flex h-6 min-w-6 items-center justify-center rounded-lg border " +
        "px-2 text-xs font-bold tracking-wide " +
        style +
        " " +
        className
      }
      title={tier ? `Tier ${key}` : "Unscored"}
    >
      {tier ? key : "—"}
    </span>
  );
}
