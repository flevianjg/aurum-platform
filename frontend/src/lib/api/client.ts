/**
 * Authenticated fetch wrapper.
 *
 * Behavior:
 * - Reads access token from the in-memory token-store and attaches it as
 *   Authorization: Bearer ... on every call.
 * - Always sends `credentials: "include"` so the HttpOnly refresh cookie is
 *   carried with the request.
 * - On 401, attempts a single transparent refresh via /auth/refresh and
 *   retries the original request once. If the refresh also fails, throws an
 *   ApiError so the caller can redirect to /login.
 * - Surfaces backend's structured error body { error, message, status,
 *   request_id } as ApiError fields.
 *
 * The base URL comes from NEXT_PUBLIC_API_BASE_URL. In production it's empty
 * (same origin) so paths like "/auth/passkey/login/begin" resolve naturally.
 */

import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth/token-store";
import type { ApiErrorBody, TokenResponse } from "@/types/api";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string;
  retryAfterSeconds?: number;

  constructor(
    message: string,
    init: { status: number; code: string; requestId?: string; retryAfterSeconds?: number },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.requestId = init.requestId;
    this.retryAfterSeconds = init.retryAfterSeconds;
  }
}

interface RequestInitWithJson extends Omit<RequestInit, "body"> {
  json?: unknown;
}

let refreshInFlight: Promise<boolean> | null = null;

async function refreshOnce(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const resp = await fetch(`${BASE_URL}/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      if (!resp.ok) return false;
      const data = (await resp.json()) as TokenResponse;
      setAccessToken(data.access_token, data.expires_at);
      return true;
    } catch {
      return false;
    } finally {
      // small debounce to coalesce rapid concurrent refreshes
      setTimeout(() => {
        refreshInFlight = null;
      }, 50);
    }
  })();
  return refreshInFlight;
}

async function parseError(resp: Response): Promise<ApiError> {
  let body: Partial<ApiErrorBody> = {};
  try {
    body = (await resp.json()) as ApiErrorBody;
  } catch {
    // not JSON
  }
  const retryAfterRaw = resp.headers.get("retry-after");
  return new ApiError(body.message ?? `HTTP ${resp.status}`, {
    status: resp.status,
    code: body.error ?? "http_error",
    requestId: body.request_id,
    retryAfterSeconds: retryAfterRaw ? Number(retryAfterRaw) : undefined,
  });
}

async function doFetch(path: string, init: RequestInitWithJson, withRetry: boolean): Promise<Response> {
  const headers = new Headers(init.headers ?? {});
  if (init.json !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = getAccessToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const resp = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers,
    body: init.json !== undefined ? JSON.stringify(init.json) : (init as RequestInit).body,
    credentials: "include",
  });

  if (resp.status !== 401 || !withRetry) return resp;

  const refreshed = await refreshOnce();
  if (!refreshed) {
    clearAccessToken();
    return resp;
  }
  return doFetch(path, init, false);
}

export async function api<T>(path: string, init: RequestInitWithJson = {}): Promise<T> {
  const resp = await doFetch(path, init, /* withRetry */ true);
  if (!resp.ok) throw await parseError(resp);
  if (resp.status === 204) return undefined as T;
  const ct = resp.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) return (await resp.json()) as T;
  return (await resp.text()) as unknown as T;
}

/** No-token, no-retry variant for first-time auth handshake (begin endpoints). */
export async function apiUnauthed<T>(path: string, init: RequestInitWithJson = {}): Promise<T> {
  const resp = await doFetch(path, init, /* withRetry */ false);
  if (!resp.ok) throw await parseError(resp);
  return (await resp.json()) as T;
}
