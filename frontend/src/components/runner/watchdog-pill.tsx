"use client";
import { Activity, AlertTriangle, Wifi } from "lucide-react";

import { cn, watchdogState, watchdogToneClass } from "./utils";

interface WatchdogPillProps {
  tick_age_seconds: number | null | undefined;
  className?: string;
}

export function WatchdogPill({ tick_age_seconds, className }: WatchdogPillProps) {
  const { tone, label } = watchdogState(tick_age_seconds);
  const Icon = tone === "live" ? Wifi : tone === "delayed" ? Activity : AlertTriangle;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        watchdogToneClass[tone],
        className,
      )}
      title={
        tick_age_seconds != null
          ? `Last update ${tick_age_seconds.toFixed(0)}s ago`
          : "No snapshot received"
      }
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}
