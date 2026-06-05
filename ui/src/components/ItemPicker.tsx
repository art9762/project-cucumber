import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useRef, useState } from "react";

import { useResearchList, useTierlist } from "../api/hooks";
import { Input } from "./Input";
import { Spinner } from "./Spinner";
import { TierBadge } from "./TierBadge";

/** A pickable idea row, deduped across research + tierlist sources. */
export interface PickableItem {
  itemId: string;
  title: string;
  tier: string | null;
  /** True when this item has a web-research row available. */
  hasResearch: boolean;
}

export interface ItemPickerProps {
  selectedId: string | null;
  onSelect: (item: PickableItem) => void;
}

function usePickableItems(): {
  items: PickableItem[];
  isLoading: boolean;
} {
  // Research list gives us the "hasResearch" flag; tierlist gives breadth + tiers.
  const research = useResearchList({});
  const tierlist = useTierlist({ limit: 200 });

  const items = useMemo<PickableItem[]>(() => {
    const byId = new Map<string, PickableItem>();

    for (const t of tierlist.data ?? []) {
      byId.set(t.item_id, {
        itemId: t.item_id,
        title: t.title,
        tier: t.tier,
        hasResearch: false,
      });
    }
    for (const r of research.data ?? []) {
      const existing = byId.get(r.item_id);
      if (existing) {
        existing.hasResearch = true;
      } else {
        byId.set(r.item_id, {
          itemId: r.item_id,
          title: r.title,
          tier: null,
          hasResearch: true,
        });
      }
    }

    return Array.from(byId.values()).sort((a, b) =>
      a.title.localeCompare(b.title),
    );
  }, [research.data, tierlist.data]);

  return {
    items,
    isLoading: research.isLoading || tierlist.isLoading,
  };
}

export function ItemPicker({ selectedId, onSelect }: ItemPickerProps) {
  const { items, isLoading } = usePickableItems();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const blurTimer = useRef<number | null>(null);

  const selected = items.find((i) => i.itemId === selectedId) ?? null;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const base = q
      ? items.filter((i) => i.title.toLowerCase().includes(q))
      : items;
    return base.slice(0, 50);
  }, [items, query]);

  function handleSelect(item: PickableItem) {
    onSelect(item);
    setQuery("");
    setOpen(false);
  }

  return (
    <div className="relative">
      <Input
        label="Idea"
        placeholder={
          isLoading ? "Loading ideas…" : "Search ideas by title…"
        }
        value={open ? query : selected?.title ?? query}
        disabled={isLoading}
        onFocus={() => {
          if (blurTimer.current) window.clearTimeout(blurTimer.current);
          setOpen(true);
        }}
        onBlur={() => {
          // Delay so an option mousedown registers before we close.
          blurTimer.current = window.setTimeout(() => setOpen(false), 120);
        }}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
      />
      {isLoading && (
        <div className="absolute right-3 top-9">
          <Spinner size={16} />
        </div>
      )}

      <AnimatePresence>
        {open && !isLoading && (
          <motion.ul
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-xl border border-border bg-surface shadow-lg shadow-black/30 backdrop-blur-sm"
          >
            {filtered.length === 0 ? (
              <li className="px-4 py-3 text-sm text-muted">No matching ideas.</li>
            ) : (
              filtered.map((item) => (
                <li key={item.itemId}>
                  <button
                    type="button"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      handleSelect(item);
                    }}
                    className={
                      "flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors " +
                      (item.itemId === selectedId
                        ? "bg-accent/15 text-accent"
                        : "text-fg hover:bg-surface-2/60")
                    }
                  >
                    <TierBadge tier={item.tier} />
                    <span className="min-w-0 flex-1 truncate" title={item.title}>
                      {item.title}
                    </span>
                    {item.hasResearch && (
                      <span className="shrink-0 rounded-md border border-border bg-surface-2 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted">
                        research
                      </span>
                    )}
                  </button>
                </li>
              ))
            )}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
