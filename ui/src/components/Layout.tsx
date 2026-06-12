import { motion } from "framer-motion";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { useHealth } from "../api/hooks";
import { Button } from "./Button";

interface NavItem {
  to: string;
  label: string;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard" },
  { to: "/tierlist", label: "Tierlist" },
  { to: "/search", label: "Search" },
  { to: "/competitors", label: "Competitors" },
  { to: "/collect", label: "Collect" },
  { to: "/control", label: "Control" },
  { to: "/settings", label: "Settings" },
];

function HealthDot() {
  const { data, isError } = useHealth();
  const ok = !isError && data?.status === "ok";
  const color = isError
    ? "bg-danger"
    : data
      ? ok
        ? "bg-emerald-400"
        : "bg-amber-400"
      : "bg-muted";
  const label = isError
    ? "API unreachable"
    : data
      ? `API ${data.status} · db ${data.database ? "up" : "down"}`
      : "checking…";
  return (
    <span className="flex items-center gap-2 text-xs text-muted" title={label}>
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {label}
    </span>
  );
}

export function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="flex min-h-screen bg-bg text-fg">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-surface/50 px-4 py-6 md:flex">
        <div className="mb-8 px-2">
          <div className="text-sm font-semibold tracking-wide text-fg">
            Project cucumber
          </div>
          <div className="text-xs text-muted">control panel</div>
        </div>
        <nav className="flex flex-1 flex-col gap-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                "rounded-xl px-3 py-2 text-sm transition-colors " +
                (isActive
                  ? "bg-accent/15 text-accent"
                  : "text-muted hover:bg-surface-2/60 hover:text-fg")
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="px-2 pt-4">
          <HealthDot />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-4 border-b border-border bg-surface/40 px-6 py-3.5 backdrop-blur-sm">
          <div className="md:hidden">
            <HealthDot />
          </div>
          <div className="ml-auto flex items-center gap-3">
            {user && (
              <div className="text-right leading-tight">
                <div className="text-sm font-medium text-fg">
                  {user.username}
                </div>
                <div className="text-xs text-muted">{user.role}</div>
              </div>
            )}
            <Button variant="ghost" size="sm" onClick={() => void logout()}>
              Log out
            </Button>
          </div>
        </header>

        <motion.main
          key="main"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.2 }}
          className="flex-1 overflow-y-auto px-6 py-6"
        >
          <Outlet />
        </motion.main>
      </div>
    </div>
  );
}
