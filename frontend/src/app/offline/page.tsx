"use client";
import Image from "next/image";
import { RefreshCw, WifiOff } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function OfflinePage() {
  function handleRetry() {
    if (typeof navigator !== "undefined" && navigator.onLine) {
      window.location.reload();
      return;
    }
    // Even if navigator.onLine is false, give the user a chance — the SW will
    // fetch and decide.
    window.location.reload();
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6 text-center">
        <div className="flex justify-center">
          <Image
            src="/anvisutra-logo.svg"
            alt="Aurum"
            width={72}
            height={72}
            priority
          />
        </div>
        <div className="space-y-2">
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-secondary">
            <WifiOff className="h-5 w-5" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight">You&apos;re offline</h1>
          <p className="text-sm text-muted-foreground">
            Some features won&apos;t work without a connection. Live broker data, sign-in, and
            account changes all require the network.
          </p>
        </div>
        <Button onClick={handleRetry} className="w-full">
          <RefreshCw className="h-4 w-4" />
          Retry
        </Button>
      </div>
    </main>
  );
}
