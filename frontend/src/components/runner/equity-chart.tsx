"use client";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

import { formatMoney } from "./utils";
import type { EquityBar } from "@/types/aurum";

interface Props {
  data: EquityBar[] | undefined;
  isLoading: boolean;
  isError: boolean;
  currency?: string;
}

interface ChartPoint {
  ts: number;
  equity: number;
}

function toPoints(bars: EquityBar[] | undefined): ChartPoint[] {
  if (!bars) return [];
  return bars
    .filter((b) => b.equity != null)
    .map((b) => ({ ts: new Date(b.ts).getTime(), equity: b.equity as number }));
}

function startOfTodayMs(): number {
  const d = new Date();
  d.setUTCHours(0, 0, 0, 0);
  return d.getTime();
}

function tickFormat(value: number): string {
  const d = new Date(value);
  const now = Date.now();
  const isToday = value >= startOfTodayMs();
  if (isToday) {
    return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
  }
  if (now - value < 7 * 24 * 60 * 60 * 1000) {
    return d.toLocaleDateString("en-US", { weekday: "short" });
  }
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function EquityChart({ data, isLoading, isError, currency = "USD" }: Props) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Equity (last 7 days)</CardTitle>
          <CardDescription>1-minute bars</CardDescription>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Failed to load equity</AlertTitle>
        <AlertDescription>The runner may be offline.</AlertDescription>
      </Alert>
    );
  }

  const points = toPoints(data);
  const empty = points.length === 0;
  const todayMs = startOfTodayMs();
  const lastMs = empty ? Date.now() : points[points.length - 1].ts;

  return (
    <Card>
      <CardHeader className="space-y-1">
        <CardTitle className="text-base">Equity (last 7 days)</CardTitle>
        <CardDescription>1-minute bars · {points.length} points</CardDescription>
      </CardHeader>
      <CardContent>
        {empty ? (
          <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
            No equity data yet — runner hasn&apos;t reported.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={points} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <ReferenceArea
                x1={Math.max(todayMs, points[0].ts)}
                x2={lastMs}
                strokeOpacity={0}
                fill="hsl(var(--primary))"
                fillOpacity={0.06}
              />
              <XAxis
                dataKey="ts"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickFormatter={tickFormat}
                stroke="hsl(var(--muted-foreground))"
                fontSize={11}
                minTickGap={36}
              />
              <YAxis
                dataKey="equity"
                domain={["auto", "auto"]}
                stroke="hsl(var(--muted-foreground))"
                fontSize={11}
                width={70}
                tickFormatter={(v) => formatMoney(v, currency, 0)}
              />
              <Tooltip
                contentStyle={{
                  background: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelFormatter={(v) => new Date(v as number).toLocaleString()}
                formatter={(value: number) => [formatMoney(value, currency), "Equity"]}
              />
              <Line
                type="monotone"
                dataKey="equity"
                stroke="hsl(var(--primary))"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
