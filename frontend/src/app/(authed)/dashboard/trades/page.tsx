"use client";
import { Suspense, useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  ArrowUpDown,
  Loader2,
  RefreshCw,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

import { ApiError } from "@/lib/api/client";
import { useAurumClosedPositions, useAurumStatus } from "@/lib/hooks/use-aurum";
import {
  cn,
  formatHoldDuration,
  formatMoney,
  pnlClass,
  relativeTime,
} from "@/components/runner/utils";
import type { ClosedPositionRow } from "@/types/aurum";

const PAGE_SIZE = 50;
type SortKey = "ts" | "instrument" | "pnl" | "hold";
type SortDir = "asc" | "desc";

interface Filters {
  instruments: string[];
  side: "all" | "BUY" | "SELL";
  from: string | null;
  to: string | null;
  sort_by: SortKey;
  sort_dir: SortDir;
}

function readFilters(params: URLSearchParams): Filters {
  return {
    instruments: (params.get("instruments") ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    side: (params.get("side") as Filters["side"]) ?? "all",
    from: params.get("from"),
    to: params.get("to"),
    sort_by: (params.get("sort_by") as SortKey) ?? "ts",
    sort_dir: (params.get("sort_dir") as SortDir) ?? "desc",
  };
}

function writeFilters(filters: Filters): string {
  const params = new URLSearchParams();
  if (filters.instruments.length) params.set("instruments", filters.instruments.join(","));
  if (filters.side !== "all") params.set("side", filters.side);
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  if (filters.sort_by !== "ts") params.set("sort_by", filters.sort_by);
  if (filters.sort_dir !== "desc") params.set("sort_dir", filters.sort_dir);
  const s = params.toString();
  return s ? `?${s}` : "";
}

export default function TradesPage() {
  return (
    <Suspense fallback={<TradesLoading />}>
      <TradesPageInner />
    </Suspense>
  );
}

function TradesLoading() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-9 w-1/3" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function TradesPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = useMemo(() => readFilters(searchParams), [searchParams]);
  const status = useAurumStatus();
  const currency = status.data?.broker?.currency ?? "USD";

  const [pages, setPages] = useState<{ before: string | null }[]>([{ before: null }]);
  const [loadingMore, setLoadingMore] = useState(false);

  const updateFilters = useCallback(
    (next: Partial<Filters>) => {
      const merged = { ...filters, ...next };
      router.replace(`/dashboard/trades${writeFilters(merged)}`);
      setPages([{ before: null }]);
    },
    [filters, router],
  );

  const toggleSort = useCallback(
    (key: SortKey) => {
      if (filters.sort_by === key) {
        updateFilters({ sort_dir: filters.sort_dir === "asc" ? "desc" : "asc" });
      } else {
        updateFilters({ sort_by: key, sort_dir: "desc" });
      }
    },
    [filters.sort_by, filters.sort_dir, updateFilters],
  );

  return (
    <div className="space-y-6">
      <div>
        <Button asChild variant="ghost" size="sm" className="mb-2">
          <Link href="/dashboard">
            <ArrowLeft className="h-4 w-4" /> Back to dashboard
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold tracking-tight">Closed trades</h1>
        <p className="text-sm text-muted-foreground">
          Full history from the runner&apos;s journal · paginated
        </p>
      </div>

      <FilterBar filters={filters} onChange={updateFilters} />

      <div className="space-y-3">
        {pages.map((p, i) => (
          <TradesPageBlock
            key={i}
            before={p.before}
            filters={filters}
            currency={currency}
            sortKey={filters.sort_by}
            sortDir={filters.sort_dir}
            toggleSort={toggleSort}
            isFirst={i === 0}
            onNext={(nextBefore) => {
              if (i === pages.length - 1 && nextBefore) {
                setPages((prev) => [...prev, { before: nextBefore }]);
                setLoadingMore(true);
                setTimeout(() => setLoadingMore(false), 250);
              }
            }}
          />
        ))}
        {loadingMore && (
          <div className="flex justify-center py-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
          </div>
        )}
      </div>
    </div>
  );
}

function FilterBar({
  filters,
  onChange,
}: {
  filters: Filters;
  onChange: (next: Partial<Filters>) => void;
}) {
  const [instrumentDraft, setInstrumentDraft] = useState(
    filters.instruments.join(", "),
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Filters</CardTitle>
        <CardDescription>
          Filters persist in the URL — share or bookmark this view.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-4">
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="instruments">Instruments (comma-sep)</Label>
          <div className="flex gap-2">
            <Input
              id="instruments"
              placeholder="EUR_USD, USD_JPY"
              value={instrumentDraft}
              onChange={(e) => setInstrumentDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  onChange({
                    instruments: instrumentDraft
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  });
                }
              }}
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                onChange({
                  instruments: instrumentDraft
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
            >
              Apply
            </Button>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="side">Side</Label>
          <select
            id="side"
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={filters.side}
            onChange={(e) => onChange({ side: e.target.value as Filters["side"] })}
          >
            <option value="all">All</option>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="from">From</Label>
          <Input
            id="from"
            type="date"
            value={filters.from ?? ""}
            onChange={(e) => onChange({ from: e.target.value || null })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="to">To</Label>
          <Input
            id="to"
            type="date"
            value={filters.to ?? ""}
            onChange={(e) => onChange({ to: e.target.value || null })}
          />
        </div>
        {(filters.instruments.length > 0 ||
          filters.side !== "all" ||
          filters.from ||
          filters.to) && (
          <Button
            size="sm"
            variant="ghost"
            className="sm:col-span-4"
            onClick={() => {
              setInstrumentDraft("");
              onChange({
                instruments: [],
                side: "all",
                from: null,
                to: null,
              });
            }}
          >
            <RefreshCw className="h-3 w-3" /> Reset filters
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function applyClientFilters(
  rows: ClosedPositionRow[],
  filters: Filters,
): ClosedPositionRow[] {
  let out = rows;
  if (filters.instruments.length) {
    const set = new Set(filters.instruments.map((s) => s.toUpperCase()));
    out = out.filter((r) => r.instrument && set.has(r.instrument.toUpperCase()));
  }
  if (filters.side !== "all") {
    out = out.filter((r) => {
      const side = (r.payload.side || r.payload.direction || "").toString().toUpperCase();
      return side === filters.side;
    });
  }
  if (filters.from) {
    const fromMs = new Date(`${filters.from}T00:00:00Z`).getTime();
    out = out.filter((r) => new Date(r.ts).getTime() >= fromMs);
  }
  if (filters.to) {
    const toMs = new Date(`${filters.to}T23:59:59.999Z`).getTime();
    out = out.filter((r) => new Date(r.ts).getTime() <= toMs);
  }
  out = sortRows(out, filters.sort_by, filters.sort_dir);
  return out;
}

function sortRows(
  rows: ClosedPositionRow[],
  key: SortKey,
  dir: SortDir,
): ClosedPositionRow[] {
  const mul = dir === "asc" ? 1 : -1;
  const copy = [...rows];
  copy.sort((a, b) => {
    if (key === "ts") {
      return mul * (new Date(a.ts).getTime() - new Date(b.ts).getTime());
    }
    if (key === "instrument") {
      return mul * (a.instrument ?? "").localeCompare(b.instrument ?? "");
    }
    if (key === "pnl") {
      const av = (a.payload.pnl as number | undefined) ?? 0;
      const bv = (b.payload.pnl as number | undefined) ?? 0;
      return mul * (av - bv);
    }
    // hold
    const ah = holdSeconds(a);
    const bh = holdSeconds(b);
    return mul * ((ah ?? 0) - (bh ?? 0));
  });
  return copy;
}

function holdSeconds(it: ClosedPositionRow): number | null {
  const p = it.payload || {};
  if (typeof p.duration_seconds === "number") return p.duration_seconds;
  if (p.open_time && p.close_time) {
    return Math.round(
      (new Date(p.close_time).getTime() - new Date(p.open_time).getTime()) / 1000,
    );
  }
  return null;
}

function TradesPageBlock({
  before,
  filters,
  currency,
  sortKey,
  sortDir,
  toggleSort,
  isFirst,
  onNext,
}: {
  before: string | null;
  filters: Filters;
  currency: string;
  sortKey: SortKey;
  sortDir: SortDir;
  toggleSort: (key: SortKey) => void;
  isFirst: boolean;
  onNext: (nextBefore: string | null) => void;
}) {
  const query = useAurumClosedPositions({
    limit: PAGE_SIZE,
    before,
  });
  const items = query.data?.items ?? [];
  const filtered = applyClientFilters(items, filters);

  if (query.isLoading && isFirst) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }
  if (query.error instanceof ApiError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Failed to load trades</AlertTitle>
        <AlertDescription>{query.error.message}</AlertDescription>
      </Alert>
    );
  }
  if (filtered.length === 0 && isFirst) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          No trades match these filters.
        </CardContent>
      </Card>
    );
  }
  if (filtered.length === 0) {
    return null; // a non-first page that filtered to empty — silent
  }

  return (
    <Card>
      <CardContent className="p-0">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-wide text-muted-foreground">
            <tr className="border-b">
              <SortableHeader
                label="When"
                col="ts"
                sortKey={sortKey}
                sortDir={sortDir}
                onClick={toggleSort}
              />
              <SortableHeader
                label="Instrument"
                col="instrument"
                sortKey={sortKey}
                sortDir={sortDir}
                onClick={toggleSort}
              />
              <th className="px-3 py-2 text-left">Side</th>
              <SortableHeader
                label="PnL"
                col="pnl"
                sortKey={sortKey}
                sortDir={sortDir}
                onClick={toggleSort}
                align="right"
              />
              <SortableHeader
                label="Held"
                col="hold"
                sortKey={sortKey}
                sortDir={sortDir}
                onClick={toggleSort}
                align="right"
              />
            </tr>
          </thead>
          <tbody className="font-mono">
            {filtered.map((it, i) => {
              const side = (it.payload.side || it.payload.direction || "")
                .toString()
                .toUpperCase();
              const pnl = (it.payload.pnl as number | undefined) ?? null;
              return (
                <tr key={`${it.ts}-${i}`} className="border-b last:border-b-0">
                  <td className="px-3 py-2 text-muted-foreground" title={it.ts}>
                    {relativeTime(it.ts)}
                  </td>
                  <td className="px-3 py-2">{it.instrument ?? "—"}</td>
                  <td className="px-3 py-2">
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
                  <td className={cn("px-3 py-2 text-right", pnlClass(pnl))}>
                    {formatMoney(pnl, currency)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {formatHoldDuration(holdSeconds(it))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {query.data?.next_before && (
          <div className="flex justify-center border-t p-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onNext(query.data!.next_before)}
            >
              Load more
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SortableHeader({
  label,
  col,
  sortKey,
  sortDir,
  onClick,
  align = "left",
}: {
  label: string;
  col: SortKey;
  sortKey: SortKey;
  sortDir: SortDir;
  onClick: (k: SortKey) => void;
  align?: "left" | "right";
}) {
  const active = sortKey === col;
  const Arrow =
    !active ? ArrowUpDown : sortDir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th
      className={cn(
        "px-3 py-2 text-left",
        align === "right" && "text-right",
      )}
    >
      <button
        type="button"
        onClick={() => onClick(col)}
        className={cn(
          "inline-flex items-center gap-1 hover:text-foreground",
          active ? "text-foreground" : "",
        )}
      >
        {label}
        <Arrow className="h-3 w-3" />
      </button>
    </th>
  );
}
