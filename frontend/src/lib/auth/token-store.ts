/**
 * In-memory access-token holder.
 *
 * Access tokens never touch localStorage / sessionStorage / cookies — anything
 * outside the JS heap is XSS-stealable. The HttpOnly Secure SameSite=Strict
 * refresh cookie (set by the backend) is the only cross-tab persistence.
 */

type Listener = (token: string | null) => void;

let accessToken: string | null = null;
let expiresAtMs: number | null = null;
const listeners = new Set<Listener>();

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null, expiresAtIso?: string | null): void {
  accessToken = token;
  expiresAtMs = expiresAtIso ? new Date(expiresAtIso).getTime() : null;
  for (const fn of listeners) fn(token);
}

export function clearAccessToken(): void {
  setAccessToken(null, null);
}

export function getExpiresAtMs(): number | null {
  return expiresAtMs;
}

export function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
