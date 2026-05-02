"use client";
import { ArrowDown, ArrowUp, OctagonAlert, PauseCircle } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

import { WatchdogPill } from "./watchdog-pill";
import {
  cn,
  formatMoney,
  formatPercent,
  pnlBgClass,
  pnlClass,
} from "./utils";
import type { AurumStatus } from "@/types/aurum";

interface Props {
  status: AurumStatus | undefined;
  isLoading: boolean;
}

export function StatusHeader({ status, isLoading }: Props) {
  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <Skeleton className="h-10 w-48" />
          <Skeleton className="h-5 w-32" />
        </div>
        <div className="flex flex-wrap gap-2">
          <Skeleton className="h-6 w-24" />
          <Skeleton className="h-6 w-24" />
          <Skeleton className="h-6 w-24" />
        </div>
      </div>
    );
  }

  const broker = status?.broker;
  const equity = broker?.equity ?? null;
  const today_pnl = broker?.today_pnl_dollars ?? null;
  const drawdown_pct = broker?.drawdown_pct ?? null;
  const currency = broker?.currency ?? "USD";
  const flags = status?.control_flags;

  const today_pct =
    today_pnl != null && equity != null && equity - today_pnl !== 0
      ? (today_pnl / (equity - today_pnl)) * 100
      : null;

  const PnlArrow = today_pnl != null && today_pnl < 0 ? ArrowDown : ArrowUp;

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="space-y-1">
        <div
          className={cn(
            "font-mono text-3xl font-semibold tracking-tight sm:text-4xl",
            equity == null ? "text-muted-foreground" : undefined,
          )}
          title={status?.snapshot_ts ? `Snapshot ${status.snapshot_ts}` : undefined}
        >
          {formatMoney(equity, currency)}
        </div>
        {today_pnl != null && (
          <div
            className={cn(
              "flex items-center gap-1 text-sm font-medium",
              pnlClass(today_pnl),
            )}
          >
            <PnlArrow className="h-4 w-4" />
            <span className="font-mono">{formatMoney(today_pnl, currency)}</span>
            {today_pct != null && (
              <span className="font-mono opacity-80">
                ({formatPercent(today_pct)})
              </span>
            )}
            <span className="text-muted-foreground">today</span>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-medium",
            pnlBgClass(today_pnl),
          )}
        >
          P&amp;L {formatMoney(today_pnl, currency)}
        </span>
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-medium",
            (drawdown_pct ?? 0) > 0
              ? "bg-destructive/15 text-destructive"
              : "bg-muted text-muted-foreground",
          )}
        >
          DD {formatPercent(drawdown_pct ?? 0)}
        </span>
        <WatchdogPill tick_age_seconds={status?.tick_age_seconds} />
        {flags?.paused && (
          <Badge className="gap-1 bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/20">
            <PauseCircle className="h-3 w-3" />
            PAUSED
          </Badge>
        )}
        {flags?.stop_requested && (
          <Badge variant="destructive" className="gap-1">
            <OctagonAlert className="h-3 w-3" />
            STOPPED
          </Badge>
        )}
      </div>
    </div>
  );
}
