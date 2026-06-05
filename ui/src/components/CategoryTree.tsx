import { useState } from "react";

import type { CategoryTreeNode } from "../api/types";

/**
 * Recursive, collapsible category tree. Selecting a node reports its id to the
 * parent (which filters the tierlist). The synthetic "All" row clears the
 * selection (reported as `null`).
 */
export interface CategoryTreeProps {
  nodes: CategoryTreeNode[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

interface NodeRowProps {
  node: CategoryTreeNode;
  depth: number;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className={"transition-transform " + (open ? "rotate-90" : "")}
    >
      <path
        d="M9 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function NodeRow({ node, depth, selectedId, onSelect }: NodeRowProps) {
  const [open, setOpen] = useState(true);
  const hasChildren = node.children.length > 0;
  const isSelected = node.id === selectedId;

  return (
    <li>
      <div
        className={
          "group flex items-center gap-1 rounded-lg pr-2 text-sm transition-colors " +
          (isSelected
            ? "bg-accent/15 text-accent"
            : "text-muted hover:bg-surface-2/60 hover:text-fg")
        }
        style={{ paddingLeft: `${depth * 0.85 + 0.25}rem` }}
      >
        <button
          type="button"
          aria-label={open ? "Collapse" : "Expand"}
          onClick={() => setOpen((v) => !v)}
          className={
            "flex h-6 w-5 shrink-0 items-center justify-center " +
            (hasChildren ? "opacity-70 hover:opacity-100" : "invisible")
          }
        >
          {hasChildren && <Chevron open={open} />}
        </button>
        <button
          type="button"
          onClick={() => onSelect(node.id)}
          className="flex min-w-0 flex-1 items-center gap-2 py-1.5 text-left"
          title={node.title}
        >
          <span className="truncate">{node.title}</span>
          {!node.approved && (
            <span
              className="shrink-0 rounded-md bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-300"
              title="Pending approval"
            >
              pending
            </span>
          )}
        </button>
      </div>
      {hasChildren && open && (
        <ul>
          {node.children.map((child) => (
            <NodeRow
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function CategoryTree({
  nodes,
  selectedId,
  onSelect,
}: CategoryTreeProps) {
  return (
    <ul className="flex flex-col gap-0.5">
      <li>
        <button
          type="button"
          onClick={() => onSelect(null)}
          className={
            "w-full rounded-lg px-3 py-1.5 text-left text-sm transition-colors " +
            (selectedId === null
              ? "bg-accent/15 text-accent"
              : "text-muted hover:bg-surface-2/60 hover:text-fg")
          }
        >
          All categories
        </button>
      </li>
      {nodes.map((node) => (
        <NodeRow
          key={node.id}
          node={node}
          depth={0}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </ul>
  );
}
