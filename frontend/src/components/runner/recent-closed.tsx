"use client";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

import {
  cn,
  formatHoldDuration,
  formatMoney,
  pnlClass,
  relativeTime,
} from "./utils";
import type { ClosedPositionRow } from "@/types/aurum";

interface Props {
  items: ClosedPositionRow[] | undefined;
  isLoading: boolean;
  currency?: string;
}

function holdSecondsOf(item: ClosedPositionRow): number | null {
  const p = item.payload || {};
  if (typeof p.duration_seconds === "number") return p.duration_seconds;
  if (p.open_time && p.close_time) {
    const d = new Date(p.close_time).getTime() - new Date(p.open_time).getTime();
    return Math.max(0, Math.round(d / 1000));
  }
  return null;
}

export function RecentClosed({ items, isLoading, currency = "USD" }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Recent trades</CardTitle>
        <CardDescription>Last 10 closed positions</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        )}
        {!isLoading && (!items || items.length === 0) && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No closed trades yet
          </p>
        )}
        {!isLoading && items && items.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted-foreground">
              <tr className="border-b">
                <th className="py-2 text-left">When</th>
                <th className="py-2 text-left">Instrument</th>
                <th className="py-2 text-left">Side</th>
                <th className="py-2 text-right">PnL</th>
                <th className="py-2 text-right">Held</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {items.map((it, i) => {
                const side = (it.payload.side || it.payload.direction || "").toString().toUpperCase();
                const pnl = (it.payload.pnl as number | undefined) ?? null;
                const held = holdSecondsOf(it);
                return (
                  <tr key={`${it.ts}-${i}`} className="border-b last:border-b-0">
                    <td className="py-2 text-muted-foreground">{relativeTime(it.ts)}</td>
                    <td className="py-2">{it.instrument ?? "—"}</td>
                    <td className="py-2">
                      <Badge
                        variant={
                          side === "BUY"
                            ? "success"
                            : side === "SELL"
                              ? "destructive"
                              : "outline"
                        }
                      >
                        {side || "—"}
                      </Badge>
                    </td>
                    <td className={cn("py-2 text-right", pnlClass(pnl))}>
                      {formatMoney(pnl, currency)}
                    </td>
                    <td className="py-2 text-right">{formatHoldDuration(held)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </CardContent>
      <CardFooter>
        <Button asChild variant="outline" size="sm" className="ml-auto">
          <Link href="/dashboard/trades">
            View all <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
      </CardFooter>
    </Card>
  );
}
