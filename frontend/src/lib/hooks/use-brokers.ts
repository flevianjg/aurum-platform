"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { brokerApi, type BrokerConnectRequest, type BrokerTestRequest } from "@/lib/api/broker";
import type { BrokerAccount, BrokerAccountDetail, BrokerTestResult } from "@/types/api";

const KEYS = {
  all: ["brokers"] as const,
  detail: (id: string) => ["broker", id] as const,
};

export function useBrokers() {
  return useQuery({
    queryKey: KEYS.all,
    queryFn: brokerApi.list,
  });
}

export function useBroker(id: string | undefined) {
  return useQuery({
    queryKey: id ? KEYS.detail(id) : ["broker", "_none"],
    queryFn: () => brokerApi.read(id!),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

export function useTestBroker() {
  return useMutation<BrokerTestResult, Error, BrokerTestRequest>({
    mutationFn: brokerApi.test,
  });
}

export function useCreateBroker() {
  const qc = useQueryClient();
  return useMutation<BrokerAccount, Error, BrokerConnectRequest>({
    mutationFn: brokerApi.connect,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
    },
  });
}

export function useTestStoredBroker(id: string | undefined) {
  const qc = useQueryClient();
  return useMutation<BrokerTestResult, Error, void>({
    mutationFn: () => brokerApi.testStored(id!),
    onSuccess: () => {
      if (id) {
        qc.invalidateQueries({ queryKey: KEYS.detail(id) });
        qc.invalidateQueries({ queryKey: KEYS.all });
      }
    },
  });
}

export function useDeactivateBroker(id: string | undefined) {
  const qc = useQueryClient();
  return useMutation<BrokerAccount, Error, void>({
    mutationFn: () => brokerApi.deactivate(id!),
    onSuccess: () => {
      if (id) {
        qc.invalidateQueries({ queryKey: KEYS.detail(id) });
        qc.invalidateQueries({ queryKey: KEYS.all });
      }
    },
  });
}

export function useReactivateBroker(id: string | undefined) {
  const qc = useQueryClient();
  return useMutation<BrokerAccount, Error, void>({
    mutationFn: () => brokerApi.reactivate(id!),
    onSuccess: () => {
      if (id) {
        qc.invalidateQueries({ queryKey: KEYS.detail(id) });
        qc.invalidateQueries({ queryKey: KEYS.all });
      }
    },
  });
}

export function useDeleteBroker(id: string | undefined) {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => brokerApi.remove(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      if (id) qc.removeQueries({ queryKey: KEYS.detail(id) });
    },
  });
}
