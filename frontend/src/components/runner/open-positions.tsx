"use client";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

import { cn, formatMoney, pnlClass, relativeTime } from "./utils";
import type { OpenPosition } from "@/types/aurum";

interface Props {
  positions: OpenPosition[] | undefined;
  isLoading: boolean;
  isError: boolean;
  currency?: string;
}

function symbolOf(p: OpenPosition): string {
  return p.instrument || p.symbol || "—";
}

function sideOf(p: OpenPosition): string {
  const s = (p.side || p.direction || "").toString().toUpperCase();
  return s === "BUY" || s === "SELL" ? s : "—";
}

function entryOf(p: OpenPosition): number | null {
  return (p.entry_price ?? p.open_price ?? null) as number | null;
}

export function OpenPositionsPanel({
  positions,
  isLoading,
  isError,
  currency = "USD",
}: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Open positions</CardTitle>
        <CardDescription>
          Live from runner snapshot · refreshes every 5s
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="space-y-2">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        )}
        {isError && (
          <Alert variant="destructive">
            <AlertTitle>Couldn&apos;t fetch open positions</AlertTitle>
            <AlertDescription>The runner may be offline.</AlertDescription>
          </Alert>
        )}
        {!isLoading && !isError && (!positions || positions.length === 0) && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No open positions
          </p>
        )}
        {!isLoading && !isError && positions && positions.length > 0 && (
          <>
            {/* Mobile: card list */}
            <div className="space-y-2 md:hidden">
              {positions.map((p, i) => (
                <PositionCard
                  key={p.position_id || `${symbolOf(p)}-${i}`}
                  position={p}
                  currency={currency}
                />
              ))}
            </div>
            {/* Desktop: table */}
            <div className="hidden md:block">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-wide text-muted-foreground">
                  <tr className="border-b">
                    <th className="py-2 text-left">Instrument</th>
                    <th className="py-2 text-left">Side</th>
                    <th className="py-2 text-right">Entry → Current</th>
                    <th className="py-2 text-right">Unrealized</th>
                    <th className="py-2 text-right">Held</th>
                    <th className="py-2 text-right">SL / TP</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  {positions.map((p, i) => (
                    <PositionRow
                      key={p.position_id || `${symbolOf(p)}-${i}`}
                      position={p}
                      currency={currency}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function PositionCard({
  position,
  currency,
}: {
  position: OpenPosition;
  currency: string;
}) {
  const side = sideOf(position);
  const entry = entryOf(position);
  const current = position.current_price ?? null;
  const upl = position.unrealized_pnl ?? null;
  const heldText =
    position.bars_held != null && position.horizon != null
      ? `${position.bars_held}/${position.horizon}`
      : position.open_time
        ? relativeTime(position.open_time)
        : "—";

  return (
    <div className="rounded-md border p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="font-medium">{symbolOf(position)}</div>
        <Badge variant={side === "BUY" ? "success" : side === "SELL" ? "destructive" : "outline"}>
          {side}
        </Badge>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
        <div>
          <div className="text-muted-foreground">Entry → Current</div>
          <div className="font-mono">
            {entry != null ? entry.toFixed(5) : "—"} →{" "}
            {current != null ? current.toFixed(5) : "—"}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground">Unrealized</div>
          <div className={cn("font-mono", pnlClass(upl))}>
            {formatMoney(upl, currency)}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground">Held</div>
          <div className="font-mono">{heldText}</div>
        </div>
        <div>
          <div className="text-muted-foreground">SL / TP</div>
          <div className="font-mono text-[11px]">
            {position.sl ?? "—"} / {position.tp ?? "—"}
          </div>
        </div>
      </div>
    </div>
  );
}

function PositionRow({
  position,
  currency,
}: {
  position: OpenPosition;
  currency: string;
}) {
  const side = sideOf(position);
  const entry = entryOf(position);
  const current = position.current_price ?? null;
  const upl = position.unrealized_pnl ?? null;
  return (
    <tr className="border-b last:border-b-0">
      <td className="py-2 font-medium">{symbolOf(position)}</td>
      <td className="py-2">
        <Badge variant={side === "BUY" ? "success" : side === "SELL" ? "destructive" : "outline"}>
          {side}
        </Badge>
      </td>
      <td className="py-2 text-right">
        {entry != null ? entry.toFixed(5) : "—"} →{" "}
        {current != null ? current.toFixed(5) : "—"}
      </td>
      <td className={cn("py-2 text-right", pnlClass(upl))}>
        {formatMoney(upl, currency)}
      </td>
      <td className="py-2 text-right">
        {position.bars_held != null && position.horizon != null
          ? `${position.bars_held}/${position.horizon}`
          : position.open_time
            ? relativeTime(position.open_time)
            : "—"}
      </td>
      <td className="py-2 text-right text-xs">
        {position.sl ?? "—"} / {position.tp ?? "—"}
      </td>
    </tr>
  );
}
