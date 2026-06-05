import { ApiError } from "../api/client";
import { Button } from "./Button";

export interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}

function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return "Could not reach the server.";
    return `${error.message}`;
  }
  if (error instanceof Error) return error.message;
  return "An unexpected error occurred.";
}

export function ErrorState({ error, onRetry, title }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-danger/30 bg-danger/5 px-6 py-10 text-center">
      <h4 className="text-sm font-semibold text-danger">
        {title ?? "Something went wrong"}
      </h4>
      <p className="max-w-md text-sm text-muted">{messageOf(error)}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}
