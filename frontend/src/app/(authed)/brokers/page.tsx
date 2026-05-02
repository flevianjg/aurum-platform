"use client";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { Plus, RefreshCw, PlugZap } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  BrokerTypeBadge,
  StatusPill,
  TestStatusPill,
} from "@/components/broker/broker-status-pills";
import { useBrokers } from "@/lib/hooks/use-brokers";
import { ApiError } from "@/lib/api/client";

export default function BrokersPage() {
  const { data, isLoading, error, refetch, isFetching } = useBrokers();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Brokers</h1>
          <p className="text-sm text-muted-foreground">
            Connection management for OANDA and MT5 accounts
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Refresh"
          >
            <RefreshCw className={isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
          <Button asChild size="sm">
            <Link href="/brokers/new">
              <Plus className="h-4 w-4" />
              Add Broker
            </Link>
          </Button>
        </div>
      </div>

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}

      {error instanceof ApiError && (
        <Alert variant="destructive">
          <AlertTitle>Failed to load brokers</AlertTitle>
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      )}

      {data && data.length === 0 && (
        <Card>
          <CardHeader className="items-center text-center">
            <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-secondary">
              <PlugZap className="h-6 w-6" />
            </div>
            <CardTitle>No brokers connected yet</CardTitle>
            <CardDescription>
              Connect an OANDA or MT5 account to start fetching live data.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex justify-center">
            <Button asChild>
              <Link href="/brokers/new">
                <Plus className="h-4 w-4" /> Add your first broker
              </Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {data && data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {data.map((b) => (
            <Link key={b.id} href={`/brokers/${b.id}`} className="block">
              <Card className="transition-colors hover:border-primary/40">
                <CardHeader className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base">{b.account_label}</CardTitle>
                    <StatusPill active={b.is_active} />
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <BrokerTypeBadge type={b.broker_type} />
                    {b.account_currency && <span className="text-muted-foreground">{b.account_currency}</span>}
                  </div>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Account</span>
                    <span className="font-mono">{b.account_number ?? "—"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Server</span>
                    <span className="truncate">{b.server ?? "—"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Last tested</span>
                    <span>
                      {b.last_tested_at
                        ? formatDistanceToNow(new Date(b.last_tested_at), { addSuffix: true })
                        : "never"}
                    </span>
                  </div>
                  <div className="flex justify-between pt-1">
                    <span className="text-muted-foreground">Status</span>
                    <TestStatusPill status={b.last_test_status} />
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
