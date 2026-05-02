"use client";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAurumStatus } from "@/lib/hooks/use-aurum";

import { relativeTime, watchdogState } from "./utils";

const DISMISS_KEY = "aurum.watchdog.dismissedUntil";
const SUPPRESS_MS = 5 * 60 * 1000;

function dismissedUntil(): number {
  if (typeof window === "undefined") return 0;
  try {
    return Number(window.localStorage.getItem(DISMISS_KEY)) || 0;
  } catch {
    return 0;
  }
}

function rememberDismiss() {
  try {
    window.localStorage.setItem(DISMISS_KEY, String(Date.now() + SUPPRESS_MS));
  } catch {
    /* ignore */
  }
}

export function WatchdogBanner() {
  const [tick, setTick] = useState(0);
  // Re-evaluate the dismissal window every 30s so the banner can come back.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  const { data, error } = useAurumStatus();
  // Expose `tick` to the memo dependency array so suppression decays.
  const isDismissed = useMemo(
    () => dismissedUntil() > Date.now(),
    [tick],
  );

  if (isDismissed) return null;

  // 404 (snapshot missing) is also offline.
  const tone =
    error
      ? "offline"
      : watchdogState(data?.tick_age_seconds).tone;

  if (tone !== "offline") return null;

  return (
    <div className="border-b border-destructive/30 bg-destructive/10">
      <div className="container flex items-center gap-3 py-2 text-sm text-destructive">
        <AlertTriangle className="h-4 w-4" />
        <div className="flex-1">
          <span className="font-medium">Runner is offline.</span>{" "}
          {data?.snapshot_ts ? (
            <>Last update {relativeTime(data.snapshot_ts)}. </>
          ) : null}
          Restart needed on the host.
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          aria-label="Dismiss"
          onClick={() => {
            rememberDismiss();
            setTick((t) => t + 1);
          }}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
