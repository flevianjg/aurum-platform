"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { getAccessToken, subscribe } from "@/lib/auth/token-store";

/**
 * Root page — bounce to /dashboard if a refresh succeeded (token in memory),
 * otherwise to /login. The Providers component triggers a silent refresh on
 * mount; we wait one tick and then route.
 */
export default function RootPage() {
  const router = useRouter();
  useEffect(() => {
    const decide = () => {
      router.replace(getAccessToken() ? "/dashboard" : "/login");
    };
    // Give the silent-refresh in providers.tsx a moment to land.
    const timer = setTimeout(decide, 250);
    const unsubscribe = subscribe((token) => {
      if (token) {
        clearTimeout(timer);
        router.replace("/dashboard");
      }
    });
    return () => {
      clearTimeout(timer);
      unsubscribe();
    };
  }, [router]);
  return null;
}
