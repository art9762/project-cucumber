/**
 * Server-session auth context.
 *
 * The backend (built by the auth agent in parallel) exposes:
 *   GET  /auth/me      -> 200 { username, role }  |  401 if no session
 *   POST /auth/login   body { username, password } -> 200 { username, role }
 *   POST /auth/logout  -> 204 / 200, clears the HttpOnly cookie
 *
 * Auth is cookie-based; the api client sends credentials on every request, so
 * we never store a token. On mount we probe /auth/me; a 401 simply means
 * "not logged in" (null user), not an error to surface.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Navigate, useLocation } from "react-router-dom";

import { get, post, isUnauthorized } from "../api/client";
import type { AuthUser, LoginRequest } from "../api/types";

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refetch: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refetch = useCallback(async () => {
    try {
      const me = await get<AuthUser>("/auth/me");
      setUser(me);
    } catch (err) {
      if (isUnauthorized(err)) {
        setUser(null);
      } else {
        // Network / server error — treat as logged out but stop loading.
        setUser(null);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const login = useCallback(async (username: string, password: string) => {
    const body: LoginRequest = { username, password };
    const me = await post<AuthUser>("/auth/login", body);
    setUser(me);
  }, []);

  const logout = useCallback(async () => {
    try {
      await post<void>("/auth/logout");
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isLoading, login, logout, refetch }),
    [user, isLoading, login, logout, refetch],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === undefined) {
    throw new Error("useAuth must be used within an <AuthProvider>");
  }
  return ctx;
}

/** Gate authed routes; redirects to /login (preserving intended path). */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg text-muted">
        <span className="animate-pulse text-sm">Loading session…</span>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <>{children}</>;
}
