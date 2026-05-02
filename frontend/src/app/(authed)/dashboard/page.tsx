"use client";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/client";
import { useAuthStore } from "@/lib/store/auth-store";
import {
  useAurumClosedPositions,
  useAurumControl,
  useAurumEquity,
  useAurumOpenPositions,
  useAurumRegime,
  useAurumStatus,
} from "@/lib/hooks/use-aurum";
import { StatusHeader } from "@/components/runner/status-header";
import { EquityChart } from "@/components/runner/equity-chart";
import { OpenPositionsPanel } from "@/components/runner/open-positions";
import { RecentClosed } from "@/components/runner/recent-closed";
import { RegimeGrid } from "@/components/runner/regime-grid";
import { RunnerControlPanel } from "@/components/runner/control-panel";

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const isOwner = user?.role === "OWNER";

  const status = useAurumStatus();
  const equity = useAurumEquity(7);
  const open = useAurumOpenPositions();
  const closed = useAurumClosedPositions({ limit: 10 });
  const regime = useAurumRegime();
  const control = useAurumControl();

  // Prefer the snapshot's control_flags (refreshed every 5s); fall back to
  // the dedicated /aurum/control endpoint when the snapshot is unavailable.
  const flags = status.data?.control_flags ?? (control.data
    ? {
        paused: control.data.paused,
        stop_requested: control.data.stop_requested,
        last_pause_meta: (control.data.pause_meta ?? null) as Record<string, unknown> | null,
      }
    : undefined);

  const currency = status.data?.broker?.currency ?? "USD";

  // Snapshot 404 = runner has never written one yet; surface it gently.
  const snapshotMissing =
    status.error instanceof ApiError && status.error.status === 404;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex-1 space-y-2">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Hello, {user?.display_name ?? "..."}
          </p>
          <StatusHeader status={status.data} isLoading={status.isLoading} />
        </div>
        {isOwner && (
          <div className="sm:ml-auto sm:flex-none">
            <RunnerControlPanel
              flags={flags}
              isRunnerResponsive={status.data?.is_runner_responsive}
              snapshotTs={status.data?.snapshot_ts ?? null}
            />
          </div>
        )}
      </div>

      {snapshotMissing && (
        <Alert>
          <AlertTitle>No snapshot yet</AlertTitle>
          <AlertDescription>
            The runner hasn&apos;t written its first snapshot. Once it&apos;s up, this dashboard
            will populate. Past equity history (if any) is still loaded below.
          </AlertDescription>
        </Alert>
      )}

      {flags?.stop_requested && (
        <Alert variant="destructive">
          <AlertTitle>STOP requested</AlertTitle>
          <AlertDescription>
            Runner will close all positions and exit. Restart from the host terminal to resume.
          </AlertDescription>
        </Alert>
      )}

      <EquityChart
        data={equity.data}
        isLoading={equity.isLoading}
        isError={equity.isError}
        currency={currency}
      />

      <OpenPositionsPanel
        positions={open.data}
        isLoading={open.isLoading}
        isError={open.isError}
        currency={currency}
      />

      <RecentClosed
        items={closed.data?.items}
        isLoading={closed.isLoading}
        currency={currency}
      />

      <RegimeGrid data={regime.data} isLoading={regime.isLoading} />
    </div>
  );
}
