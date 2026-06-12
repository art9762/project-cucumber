import { useEffect, useState } from "react";

import { ApiError } from "../api/client";
import {
  useCollectJob,
  useCollectorSchedule,
  useCollectorSources,
  useRunCollect,
  useUpdateSchedule,
} from "../api/hooks";
import type { CollectJobOut } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Input } from "../components/Input";
import { Spinner } from "../components/Spinner";
import { StatChip } from "../components/StageRunnerCard";

// ---------------------------------------------------------------------------
// Per-source manual run
// ---------------------------------------------------------------------------

function SourceRunner({
  source,
  canRun,
}: {
  source: string;
  canRun: boolean;
}) {
  const runCollect = useRunCollect();
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useCollectJob(jobId);

  function handleRun() {
    runCollect.mutate(
      { source },
      { onSuccess: (data) => setJobId((data as CollectJobOut).id) },
    );
  }

  const isActive = runCollect.isPending || job.data?.status === "queued" || job.data?.status === "running";
  const jobData = job.data;
  const runErrorMsg = runCollect.isError
    ? runCollect.error instanceof ApiError
      ? runCollect.error.message
      : "Run failed. Please try again."
    : null;

  return (
    <Card title={source}>
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <Button
            onClick={handleRun}
            disabled={isActive || !canRun}
            title={canRun ? undefined : "Requires admin"}
          >
            {isActive ? "Running…" : "Run"}
          </Button>
          {isActive && <Spinner size={18} label="Collecting…" />}
          {!canRun && !isActive && (
            <span className="text-xs text-muted">Admins only</span>
          )}
        </div>

        {runErrorMsg && (
          <p
            className="rounded-xl border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger"
            role="alert"
          >
            {runErrorMsg}
          </p>
        )}

        {jobData && (
          <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface-2/40 p-4">
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wide text-muted">Status</span>
              <span
                className={
                  jobData.status === "success"
                    ? "text-sm font-medium text-emerald-300"
                    : jobData.status === "failed"
                      ? "text-sm font-medium text-rose-300"
                      : "text-sm font-medium text-amber-300"
                }
              >
                {jobData.status}
              </span>
            </div>
            {jobData.status !== "queued" && (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <StatChip label="Fetched" value={jobData.stats.fetched} />
                <StatChip label="Inserted" value={jobData.stats.inserted} tone="good" />
                <StatChip label="Updated" value={jobData.stats.updated} />
                <StatChip label="Skipped" value={jobData.stats.skipped} />
              </div>
            )}
            {jobData.error && (
              <p className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 font-mono text-xs text-danger">
                {jobData.error}
              </p>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Schedule editor
// ---------------------------------------------------------------------------

function ScheduleRow({
  source,
  initial,
  canRun,
}: {
  source: string;
  initial: string;
  canRun: boolean;
}) {
  const [cron, setCron] = useState(initial);
  const [saved, setSaved] = useState(false);
  const update = useUpdateSchedule();

  useEffect(() => { setCron(initial); }, [initial]);

  function handleSave() {
    setSaved(false);
    update.mutate(
      { source, cron },
      { onSuccess: () => setSaved(true) },
    );
  }

  const saveError =
    update.error instanceof ApiError ? update.error.message : null;

  return (
    <li className="flex flex-wrap items-end gap-3 px-4 py-3 odd:bg-surface-2/20">
      <span className="w-28 shrink-0 text-sm font-medium text-fg">{source}</span>
      <div className="flex-1 min-w-36">
        <Input
          label=""
          placeholder="0 6 * * *"
          value={cron}
          onChange={(e) => { setCron(e.target.value); setSaved(false); }}
          disabled={!canRun || update.isPending}
        />
      </div>
      <Button
        size="sm"
        variant="secondary"
        onClick={handleSave}
        disabled={!canRun || update.isPending}
      >
        {update.isPending ? "Saving…" : "Save"}
      </Button>
      {saved && (
        <span className="text-xs text-emerald-400">Saved</span>
      )}
      {saveError && (
        <span className="text-xs text-danger">{saveError}</span>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function CollectPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const sources = useCollectorSources();
  const schedule = useCollectorSchedule();

  const sourceList: string[] = sources.data?.sources ?? [];
  const schedules: Record<string, string> = schedule.data?.schedules ?? {};

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
      <header>
        <h1 className="text-lg font-semibold text-fg">Data collection</h1>
        <p className="mt-1 text-sm text-muted">
          Manually trigger a collect run per source or edit cron schedules.
          Run and schedule actions require an admin account.
        </p>
        {!isAdmin && (
          <p className="mt-3 inline-flex rounded-xl border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
            You are signed in as a viewer. Run and schedule actions are
            disabled and will be rejected by the server.
          </p>
        )}
      </header>

      <section>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted">
          Manual run
        </h2>
        {sources.isLoading ? (
          <div className="flex justify-center py-10">
            <Spinner size={22} label="Loading sources…" />
          </div>
        ) : sources.isError ? (
          <p className="text-sm text-danger">Could not load sources.</p>
        ) : (
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            {sourceList.map((src) => (
              <SourceRunner key={src} source={src} canRun={isAdmin} />
            ))}
          </div>
        )}
      </section>

      <Card title="Collection schedule">
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted">
            5-field cron, UTC (e.g. <span className="font-mono">0 6 * * *</span>{" "}
            = daily at 06:00 UTC). Leave blank to disable.
          </p>
          {schedule.isLoading ? (
            <div className="flex justify-center py-6">
              <Spinner size={18} label="Loading schedules…" />
            </div>
          ) : schedule.isError ? (
            <p className="text-sm text-danger">Could not load schedules.</p>
          ) : (
            <ul className="overflow-hidden rounded-xl border border-border divide-y divide-border">
              {sourceList.map((src) => (
                <ScheduleRow
                  key={src}
                  source={src}
                  initial={schedules[src] ?? ""}
                  canRun={isAdmin}
                />
              ))}
            </ul>
          )}
        </div>
      </Card>
    </div>
  );
}
