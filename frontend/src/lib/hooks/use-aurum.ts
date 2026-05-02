"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { aurumApi, type ClosedPositionsQuery } from "@/lib/api/aurum";
import type { ControlActionResponse } from "@/types/aurum";

const KEYS = {
  status: ["aurum-status"] as const,
  equity: (days: number) => ["aurum-equity", days] as const,
  open: ["aurum-open-positions"] as const,
  closed: (opts: ClosedPositionsQuery) => ["aurum-closed-positions", opts] as const,
  regime: ["aurum-regime"] as const,
  daily: (date?: string) => ["aurum-daily-report", date ?? "today"] as const,
  control: ["aurum-control"] as const,
};

const REFETCH = {
  status: 5_000,
  equity: 60_000,
  open: 5_000,
  closed: 60_000,
  regime: 30_000,
  daily: 300_000,
  control: 10_000,
} as const;

export function useAurumStatus() {
  return useQuery({
    queryKey: KEYS.status,
    queryFn: aurumApi.status,
    refetchInterval: REFETCH.status,
    // Returning a 404 (snapshot missing) is a legitimate state — render
    // the offline UI rather than retrying aggressively.
    retry: false,
  });
}

export function useAurumEquity(days = 7) {
  return useQuery({
    queryKey: KEYS.equity(days),
    queryFn: () => aurumApi.equity(days),
    refetchInterval: REFETCH.equity,
  });
}

export function useAurumOpenPositions() {
  return useQuery({
    queryKey: KEYS.open,
    queryFn: aurumApi.openPositions,
    refetchInterval: REFETCH.open,
  });
}

export function useAurumClosedPositions(opts: ClosedPositionsQuery = {}) {
  return useQuery({
    queryKey: KEYS.closed(opts),
    queryFn: () => aurumApi.closedPositions(opts),
    refetchInterval: REFETCH.closed,
  });
}

export function useAurumRegime() {
  return useQuery({
    queryKey: KEYS.regime,
    queryFn: aurumApi.regime,
    refetchInterval: REFETCH.regime,
  });
}

export function useAurumDailyReport(date?: string) {
  return useQuery({
    queryKey: KEYS.daily(date),
    queryFn: () => aurumApi.dailyReport(date),
    refetchInterval: REFETCH.daily,
  });
}

export function useAurumControl() {
  return useQuery({
    queryKey: KEYS.control,
    queryFn: aurumApi.control,
    refetchInterval: REFETCH.control,
  });
}

function invalidateControlAndStatus(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: KEYS.status });
  qc.invalidateQueries({ queryKey: KEYS.control });
}

export function usePauseAurum() {
  const qc = useQueryClient();
  return useMutation<ControlActionResponse, Error, void>({
    mutationFn: () => aurumApi.pause(),
    onSuccess: () => invalidateControlAndStatus(qc),
  });
}

export function useResumeAurum() {
  const qc = useQueryClient();
  return useMutation<ControlActionResponse, Error, void>({
    mutationFn: () => aurumApi.resume(),
    onSuccess: () => invalidateControlAndStatus(qc),
  });
}

export function useStopAurum() {
  const qc = useQueryClient();
  return useMutation<ControlActionResponse, Error, void>({
    mutationFn: () => aurumApi.stop(),
    onSuccess: () => invalidateControlAndStatus(qc),
  });
}
