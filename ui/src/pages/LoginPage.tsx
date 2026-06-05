import { motion } from "framer-motion";
import { useState, type FormEvent } from "react";
import { useLocation, useNavigate, Navigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";
import { Button } from "../components/Button";
import { Input } from "../components/Input";

interface LocationState {
  from?: { pathname?: string };
}

export function LoginPage() {
  const { user, login, isLoading: authLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const redirectTo =
    (location.state as LocationState | null)?.from?.pathname ?? "/";

  if (!authLoading && user) {
    return <Navigate to={redirectTo} replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Invalid username or password.");
      } else if (err instanceof ApiError && err.status === 0) {
        setError("Could not reach the server.");
      } else {
        setError("Login failed. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="w-full max-w-sm"
      >
        <div className="mb-6 text-center">
          <h1 className="text-lg font-semibold text-fg">Project cucumber</h1>
          <p className="text-sm text-muted">Sign in to the control panel</p>
        </div>
        <form
          onSubmit={onSubmit}
          className="flex flex-col gap-4 rounded-2xl border border-border bg-surface/70 p-6 shadow-lg shadow-black/20 backdrop-blur-sm"
        >
          <Input
            label="Username"
            value={username}
            autoComplete="username"
            autoFocus
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          <Input
            label="Password"
            type="password"
            value={password}
            autoComplete="current-password"
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {error && (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" disabled={submitting} className="mt-1 w-full">
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </motion.div>
    </div>
  );
}
