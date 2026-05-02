import { api, apiUnauthed } from "@/lib/api/client";
import { setAccessToken, clearAccessToken } from "@/lib/auth/token-store";
import {
  performAuthentication,
  performRegistration,
} from "@/lib/auth/webauthn";
import type {
  PasskeyChallengeResponse,
  PasskeyRegisterFinishResponse,
  TokenResponse,
} from "@/types/api";

export async function registerPasskey(email: string, nickname?: string): Promise<PasskeyRegisterFinishResponse> {
  const begin = await apiUnauthed<PasskeyChallengeResponse>(
    "/auth/passkey/register/begin",
    { method: "POST", json: { email, nickname } },
  );
  const credential = await performRegistration(begin.publicKey);
  return apiUnauthed<PasskeyRegisterFinishResponse>(
    "/auth/passkey/register/finish",
    {
      method: "POST",
      json: { challenge_id: begin.challenge_id, credential, nickname },
    },
  );
}

export async function loginWithPasskey(email?: string): Promise<TokenResponse> {
  const begin = await apiUnauthed<PasskeyChallengeResponse>(
    "/auth/passkey/login/begin",
    { method: "POST", json: email ? { email } : {} },
  );
  const assertion = await performAuthentication(begin.publicKey);
  const tokens = await apiUnauthed<TokenResponse>("/auth/passkey/login/finish", {
    method: "POST",
    json: { challenge_id: begin.challenge_id, credential: assertion },
  });
  setAccessToken(tokens.access_token, tokens.expires_at);
  return tokens;
}

export async function logout(): Promise<void> {
  try {
    await api<{ revoked: boolean }>("/auth/logout", { method: "POST" });
  } finally {
    clearAccessToken();
  }
}

export async function refresh(): Promise<TokenResponse | null> {
  try {
    const tokens = await apiUnauthed<TokenResponse>("/auth/refresh", { method: "POST" });
    setAccessToken(tokens.access_token, tokens.expires_at);
    return tokens;
  } catch {
    clearAccessToken();
    return null;
  }
}
