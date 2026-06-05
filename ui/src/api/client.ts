/**
 * Typed fetch wrapper for the analysis API.
 *
 * - Prefixes every path with VITE_API_BASE (default http://localhost:8113).
 * - Always sends `credentials: 'include'` so the HttpOnly session cookie
 *   travels with the request (server-session auth model).
 * - Sets JSON headers and parses JSON responses.
 * - Throws a typed `ApiError` on non-2xx; HTTP 401 is detectable via
 *   `err.status === 401` (and the `isUnauthorized` helper) so the auth layer
 *   can treat it as "not logged in".
 */

const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/+$/, "") ??
  "http://localhost:8113";

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

/** True when an unknown error is an ApiError caused by an expired/absent session. */
export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}

export interface FetchOptions {
  /** HTTP method. Defaults to GET. */
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** JSON-serialisable request body. */
  body?: unknown;
  /** Query params; undefined/null values are skipped. */
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Optional AbortSignal (TanStack Query passes one in). */
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: FetchOptions["query"]): string {
  const url = new URL(
    path.startsWith("/") ? `${API_BASE}${path}` : `${API_BASE}/${path}`,
  );
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export async function apiFetch<T>(
  path: string,
  opts: FetchOptions = {},
): Promise<T> {
  const { method = "GET", body, query, signal } = opts;

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      credentials: "include",
      signal,
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  } catch (cause) {
    // Network-level failure (server down, CORS, DNS, aborted).
    throw new ApiError(0, `Network request failed: ${String(cause)}`);
  }

  if (!response.ok) {
    let parsed: unknown;
    let message = `${response.status} ${response.statusText}`;
    try {
      parsed = await response.json();
      const detail = (parsed as { detail?: unknown } | null)?.detail;
      if (typeof detail === "string") message = detail;
    } catch {
      // Body was not JSON — keep the status-line message.
    }
    throw new ApiError(response.status, message, parsed);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

/** GET helper. */
export function get<T>(
  path: string,
  query?: FetchOptions["query"],
  signal?: AbortSignal,
): Promise<T> {
  return apiFetch<T>(path, { method: "GET", query, signal });
}

/** POST helper. */
export function post<T>(
  path: string,
  body?: unknown,
  query?: FetchOptions["query"],
  signal?: AbortSignal,
): Promise<T> {
  return apiFetch<T>(path, { method: "POST", body, query, signal });
}

export { API_BASE };
