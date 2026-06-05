import { forwardRef, useId, type InputHTMLAttributes } from "react";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, className = "", id, ...rest },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label
          htmlFor={inputId}
          className="text-xs font-medium uppercase tracking-wide text-muted"
        >
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        className={
          "h-10 rounded-xl border border-border bg-surface-2 px-3 text-sm text-fg " +
          "placeholder:text-muted/60 transition-colors focus:border-accent " +
          "focus-visible:outline-none " +
          (error ? "border-danger " : "") +
          className
        }
        {...rest}
      />
      {error && <span className="text-xs text-danger">{error}</span>}
    </div>
  );
});
