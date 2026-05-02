"use client";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { getMe } from "@/lib/api/me";
import { ApiError } from "@/lib/api/client";
import { useAuthStore } from "@/lib/store/auth-store";

export function useCurrentUser() {
  const setUser = useAuthStore((s) => s.setUser);
  const query = useQuery({
    queryKey: ["me"],
    queryFn: getMe,
    retry: (count, err) => {
      if (err instanceof ApiError && err.status === 401) return false;
      return count < 1;
    },
    staleTime: 60_000,
  });

  useEffect(() => {
    if (query.data) setUser(query.data);
  }, [query.data, setUser]);

  return query;
}
