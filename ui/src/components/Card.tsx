import { motion } from "framer-motion";
import type { ReactNode } from "react";

export interface CardProps {
  children: ReactNode;
  className?: string;
  /** Optional header title rendered above the body. */
  title?: ReactNode;
  /** Optional element rendered at the top-right of the header. */
  action?: ReactNode;
  /** Disable the mount animation (useful inside lists). */
  static?: boolean;
}

export function Card({
  children,
  className = "",
  title,
  action,
  static: isStatic = false,
}: CardProps) {
  const body = (
    <div
      className={
        "rounded-2xl border border-border bg-surface/70 shadow-lg shadow-black/20 " +
        "backdrop-blur-sm " +
        className
      }
    >
      {(title || action) && (
        <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-3.5">
          {title && (
            <h3 className="text-sm font-semibold tracking-wide text-fg">
              {title}
            </h3>
          )}
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );

  if (isStatic) return body;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
    >
      {body}
    </motion.div>
  );
}
