"use client";
import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { formatDistanceToNow } from "date-fns";
import {
  ArrowLeft,
  CheckCircle2,
  Loader2,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  Trash2,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "@/components/ui/toaster";
import {
  BrokerTypeBadge,
  StatusPill,
  TestStatusPill,
} from "@/components/broker/broker-status-pills";
import {
  useBroker,
  useDeactivateBroker,
  useDeleteBroker,
  useReactivateBroker,
  useTestStoredBroker,
} from "@/lib/hooks/use-brokers";
import { ApiError } from "@/lib/api/client";
import { formatCurrency, formatDateTime } from "@/lib/utils/format";

export default function BrokerDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = typeof params?.id === "string" ? params.id : Array.isArray(params?.id) ? params.id[0] : undefined;

  const { data, isLoading, error, refetch, isFetching } = useBroker(id);
  const testStored = useTestStoredBroker(id);
  const deactivate = useDeactivateBroker(id);
  const reactivate = useReactivateBroker(id);
  const remove = useDeleteBroker(id);

  if (!id) return null;

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-32" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  if (error instanceof ApiError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{error.status === 404 ? "Broker not found" : "Failed to load broker"}</AlertTitle>
        <AlertDescription>{error.message}</AlertDescription>
      </Alert>
    );
  }
  if (!data) return null;

  const live = data.live_account_info;
  const currency = data.account_currency ?? live?.currency ?? "USD";

  return (
    <div className="space-y-6">
      <div>
        <Button asChild variant="ghost" size="sm" className="mb-2">
          <Link href="/brokers">
            <ArrowLeft className="h-4 w-4" /> Back to brokers
          </Link>
        </Button>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{data.account_label}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
              <BrokerTypeBadge type={data.broker_type} />
              {data.account_currency && <span className="text-muted-foreground">{data.account_currency}</span>}
              <StatusPill active={data.is_active} />
              <TestStatusPill status={data.last_test_status} />
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Live stats */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard label="Balance" value={live ? formatCurrency(live.balance, live.currency) : "—"} />
        <StatCard label="Equity" value={live ? formatCurrency(live.equity, live.currency) : "—"} />
        <StatCard label="Margin" value={live ? formatCurrency(live.margin, live.currency) : "—"} />
        <StatCard label="Free margin" value={live ? formatCurrency(live.free_margin, live.currency) : "—"} />
        <StatCard
          label="Margin level"
          value={live?.margin_level != null ? `${live.margin_level.toFixed(2)}%` : "—"}
        />
        <StatCard label="Server" value={live?.server ?? data.server ?? "—"} mono={false} />
      </div>

      {!live && (
        <Alert variant={data.last_test_error ? "destructive" : "default"}>
          {data.last_test_error ? <XCircle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
          <AlertTitle>{data.last_test_error ? "Live data unavailable" : "No live data yet"}</AlertTitle>
          <AlertDescription>
            {data.last_test_error ?? "Run a test to populate live data."}
          </AlertDescription>
        </Alert>
      )}

      {/* Connection info */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Connection</CardTitle>
          <CardDescription>Stored details (credentials never displayed).</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
          <Row label="Account number" value={data.account_number ?? "—"} mono />
          <Row label="Server" value={data.server ?? "—"} />
          <Row label="Currency" value={currency} />
          <Row label="Created" value={formatDateTime(data.created_at)} />
          <Row
            label="Last tested"
            value={
              data.last_tested_at
                ? `${formatDistanceToNow(new Date(data.last_tested_at), { addSuffix: true })} (${formatDateTime(data.last_tested_at)})`
                : "never"
            }
          />
        </CardContent>
      </Card>

      {/* Actions */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Actions</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            onClick={async () => {
              try {
                const r = await testStored.mutateAsync();
                toast[r.success ? "success" : "error"](
                  r.success ? "Connection OK" : "Test failed",
                  { description: r.error_message ?? r.account_number ?? undefined },
                );
              } catch (err) {
                if (err instanceof ApiError) toast.error(err.message);
              }
            }}
            disabled={testStored.isPending}
          >
            {testStored.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Test connection
          </Button>

          {data.is_active ? (
            <ConfirmDialog
              triggerLabel="Deactivate"
              triggerIcon={<PauseCircle className="h-4 w-4" />}
              triggerVariant="outline"
              title="Deactivate this broker?"
              description="The account stays in the system but won't be used for live data fetches."
              confirmLabel="Deactivate"
              onConfirm={async () => {
                await deactivate.mutateAsync();
                toast.success("Broker deactivated");
              }}
              pending={deactivate.isPending}
            />
          ) : (
            <Button
              variant="outline"
              onClick={async () => {
                await reactivate.mutateAsync();
                toast.success("Broker reactivated");
              }}
              disabled={reactivate.isPending}
            >
              {reactivate.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
              Reactivate
            </Button>
          )}

          <DeleteDialog
            label={data.account_label}
            pending={remove.isPending}
            onConfirm={async () => {
              await remove.mutateAsync();
              toast.success("Broker deleted");
              router.replace("/brokers");
            }}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className={mono ? "mt-1 font-mono text-xl" : "mt-1 text-xl"}>{value}</div>
      </CardContent>
    </Card>
  );
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? "font-mono" : undefined}>{value}</span>
    </div>
  );
}

function ConfirmDialog({
  triggerLabel,
  triggerIcon,
  triggerVariant = "outline",
  title,
  description,
  confirmLabel,
  onConfirm,
  pending,
}: {
  triggerLabel: string;
  triggerIcon: React.ReactNode;
  triggerVariant?: "outline" | "secondary" | "destructive";
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => Promise<void> | void;
  pending: boolean;
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant={triggerVariant} disabled={pending}>
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : triggerIcon}
          {triggerLabel}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={() => void onConfirm()}>{confirmLabel}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function DeleteDialog({
  label,
  onConfirm,
  pending,
}: {
  label: string;
  onConfirm: () => Promise<void> | void;
  pending: boolean;
}) {
  const [confirmText, setConfirmText] = useState("");
  const matches = confirmText.trim() === label;
  return (
    <AlertDialog onOpenChange={() => setConfirmText("")}>
      <AlertDialogTrigger asChild>
        <Button variant="destructive" disabled={pending}>
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
          Delete
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Permanently delete this broker?</AlertDialogTitle>
          <AlertDialogDescription>
            This removes the broker and all of its connection-test history. Audit log entries are
            preserved. To confirm, type the broker label{" "}
            <span className="font-mono text-foreground">{label}</span> below.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-2">
          <Label htmlFor="confirm-text">Account label</Label>
          <Input
            id="confirm-text"
            autoFocus
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={!matches}
            onClick={() => {
              if (matches) void onConfirm();
            }}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            Delete forever
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
