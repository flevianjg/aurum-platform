/**
 * WebAuthn client helpers — thin wrapper over @simplewebauthn/browser.
 *
 * The backend returns the WebAuthn options under `publicKey`. We pass that
 * through to startAuthentication / startRegistration so the browser can talk
 * to the user's authenticator (Touch ID, Windows Hello, security key, etc).
 *
 * Types are intentionally loose at this boundary — the backend validates
 * the assertion / attestation cryptographically, and v11 of the SDK does
 * not re-export these JSON types from the browser entrypoint.
 */

import {
  startAuthentication,
  startRegistration,
} from "@simplewebauthn/browser";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyJson = Record<string, any>;

export async function performRegistration(publicKey: AnyJson): Promise<AnyJson> {
  // The SDK accepts the JSON-encoded creation options shape directly.
  return startRegistration({ optionsJSON: publicKey as never }) as unknown as AnyJson;
}

export async function performAuthentication(publicKey: AnyJson): Promise<AnyJson> {
  return startAuthentication({ optionsJSON: publicKey as never }) as unknown as AnyJson;
}

export function browserSupportsPasskeys(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.PublicKeyCredential !== "undefined"
  );
}
