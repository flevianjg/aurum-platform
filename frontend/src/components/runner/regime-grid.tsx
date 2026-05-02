"use client";
import { Check, Minus } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { cn, regimeBadgeClass, relativeTime } from "./utils";
import type { InstrumentEngineState } from "@/types/aurum";

interface Props {
  data: Record<string, InstrumentEngineState> | undefined;
  isLoading: boolean;
}

export function RegimeGrid({ data, isLoading }: Props) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Per-instrument runner state</CardTitle>
          <CardDescription>Regime · model readiness · last bar</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const entries = data ? Object.entries(data) : [];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Per-instrument runner state</CardTitle>
        <CardDescription>Regime · model readiness · last bar</CardDescription>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No instruments reported yet
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {entries.map(([instrument, state]) => (
              <InstrumentCard
                key={instrument}
                instrument={instrument}
                state={state}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function InstrumentCard({
  instrument,
  state,
}: {
  instrument: string;
  state: InstrumentEngineState;
}) {
  const totalSkipped = Object.values(state.skipped ?? {}).reduce(
    (acc: number, n) => acc + (typeof n === "number" ? n : 0),
    0,
  );
  return (
    <div className="rounded-md border p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="font-medium">{instrument}</div>
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-xs font-medium",
            regimeBadgeClass(state.last_regime as string | undefined),
          )}
        >
          {state.last_regime ?? "—"}
        </span>
      </div>
      <div className="mt-2 space-y-1 text-xs">
        <div className="flex items-center gap-1 text-muted-foreground">
          {state.model_ready ? (
            <Check className="h-3 w-3 text-success" />
          ) : (
            <Minus className="h-3 w-3 text-destructive" />
          )}
          <span>Model {state.model_ready ? "ready" : "not ready"}</span>
        </div>
        <div className="text-muted-foreground">
          Last bar: <span className="text-foreground">{relativeTime(state.last_bar_utc)}</span>
        </div>
        {totalSkipped > 0 && (
          <div className="text-muted-foreground">
            Skipped today: <span className="text-foreground">{totalSkipped}</span>
          </div>
        )}
      </div>
    </div>
  );
}
