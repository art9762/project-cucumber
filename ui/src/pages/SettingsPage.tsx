import { useState } from "react";

import { API_BASE } from "../api/client";
import { useHealth } from "../api/hooks";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Spinner } from "../components/Spinner";

/** A coloured status pill for boolean / status values. */
function StatusPill({
  ok,
  okLabel,
  badLabel,
}: {
  ok: boolean;
  okLabel: string;
  badLabel: string;
}) {
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 rounded-lg border px-2 py-0.5 text-xs font-medium " +
        (ok
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
          : "border-rose-500/40 bg-rose-500/10 text-rose-300")
      }
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-400" : "bg-rose-400"}`}
      />
      {ok ? okLabel : badLabel}
    </span>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <span className="text-sm text-muted">{label}</span>
      <span className="text-right text-sm text-fg">{children}</span>
    </div>
  );
}

export function SettingsPage() {
  const { user, logout } = useAuth();
  const health = useHealth();
  const [loggingOut, setLoggingOut] = useState(false);

  async function onLogout() {
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold text-fg">Settings</h1>
        <p className="mt-1 text-sm text-muted">
          Account, backend status and environment information.
        </p>
      </header>

      <Card title="Account">
        <div className="flex flex-col gap-4">
          <div className="divide-y divide-border">
            <Row label="Username">
              <span className="font-medium">{user?.username ?? "—"}</span>
            </Row>
            <Row label="Role">
              <span className="inline-flex rounded-lg border border-border bg-surface-2 px-2 py-0.5 text-xs font-medium uppercase tracking-wide text-fg">
                {user?.role ?? "—"}
              </span>
            </Row>
          </div>
          <div>
            <Button
              variant="danger"
              onClick={() => void onLogout()}
              disabled={loggingOut}
            >
              {loggingOut ? "Logging out…" : "Log out"}
            </Button>
          </div>
        </div>
      </Card>

      <Card title="Backend status">
        {health.isLoading ? (
          <div className="flex justify-center py-6">
            <Spinner size={20} label="Checking…" />
          </div>
        ) : health.isError ? (
          <div className="divide-y divide-border">
            <Row label="API">
              <StatusPill ok={false} okLabel="reachable" badLabel="unreachable" />
            </Row>
          </div>
        ) : (
          <div className="divide-y divide-border">
            <Row label="API status">
              <StatusPill
                ok={health.data?.status === "ok"}
                okLabel={health.data?.status ?? "ok"}
                badLabel={health.data?.status ?? "degraded"}
              />
            </Row>
            <Row label="Database">
              <StatusPill
                ok={Boolean(health.data?.database)}
                okLabel="connected"
                badLabel="down"
              />
            </Row>
            <Row label="Trinity (LLM gateway)">
              <StatusPill
                ok={Boolean(health.data?.trinity_configured)}
                okLabel="configured"
                badLabel="not configured"
              />
            </Row>
          </div>
        )}
      </Card>

      <Card title="About / environment">
        <div className="flex flex-col gap-3">
          <div className="divide-y divide-border">
            <Row label="API base">
              <span className="break-all font-mono text-xs">{API_BASE}</span>
            </Row>
            <Row label="Mode">
              <span className="font-mono text-xs">
                {import.meta.env.MODE}
              </span>
            </Row>
          </div>
          <p className="text-xs text-muted">
            Project cucumber control panel. Settings are read-only for now —
            secrets are configured on the server.
          </p>
        </div>
      </Card>
    </div>
  );
}
