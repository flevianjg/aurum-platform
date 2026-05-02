"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { logoutAllSessions, passkeysApi } from "@/lib/api/passkeys";
import type { PasskeyOut } from "@/types/api";

const KEY = ["passkeys"] as const;

export function usePasskeys() {
  return useQuery({ queryKey: KEY, queryFn: passkeysApi.list });
}

export function useRenamePasskey() {
  const qc = useQueryClient();
  return useMutation<PasskeyOut, Error, { id: string; nickname: string }>({
    mutationFn: ({ id, nickname }) => passkeysApi.rename(id, nickname),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useRemovePasskey() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => passkeysApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useLogoutAll() {
  return useMutation<void, Error, void>({ mutationFn: () => logoutAllSessions() });
}
