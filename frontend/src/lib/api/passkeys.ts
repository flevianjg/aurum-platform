import { api } from "@/lib/api/client";
import type { PasskeyOut } from "@/types/api";

export const passkeysApi = {
  list() {
    return api<PasskeyOut[]>("/me/passkeys");
  },
  rename(id: string, nickname: string) {
    return api<PasskeyOut>(`/me/passkeys/${id}`, {
      method: "PATCH",
      json: { nickname },
    });
  },
  remove(id: string) {
    return api<void>(`/me/passkeys/${id}`, { method: "DELETE" });
  },
};

export function logoutAllSessions() {
  return api<void>("/auth/logout-all", { method: "POST" });
}
