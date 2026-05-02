"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { refresh } from "@/lib/api/auth";
import { getAccessToken } from "@/lib/auth/token-store";
import { Toaster } from "@/components/ui/toaster";

const REFRESH_INTERVAL_MS = 12 * 60 * 1000;

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 },
        },
      }),
  );

  // On first mount, attempt a silent refresh so a returning user lands authed.
  useEffect(() => {
    if (!getAccessToken()) {
      void refresh();
    }
    const id = setInterval(() => {
      if (getAccessToken()) void refresh();
    }, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster />
    </QueryClientProvider>
  );
}
