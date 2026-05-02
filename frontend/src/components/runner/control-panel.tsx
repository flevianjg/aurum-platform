"use client";
import { useState } from "react";
import {
  Loader2,
  OctagonAlert,
  PauseCircle,
  PlayCircle,
  PowerOff,
  WifiOff,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

import { ApiError } from "@/lib/api/client";
import {
  usePauseAurum,
  useResumeAurum,
  useStopAurum,
} from "@/lib/hooks/use-aurum";
import type { ControlFlags } from "@/types/aurum";

import { relativeTime } from "./utils";

interface Props {
  flags: ControlFlags | undefined;
  isRunnerResponsive?: boolean;
  snapshotTs?: string | null;
}

function handleError(err: unknown, fallback = "Action failed") {
  if (err instanceof ApiError) {
    toast.error(`${fallback} (${err.status})`, {
      description: err.requestId ? `request_id: ${err.requestId}` : err.message,
    });
    return;
  }
  toast.error(fallback);
}

export function RunnerControlPanel({
  flags,
  isRunnerResponsive,
  snapshotTs,
}: Props) {
  const pause = usePauseAurum();
  const resume = useResumeAurum();
  const stop = useStopAurum();

  const isPaused = Boolean(flags?.paused);
  const isStopRequested = Boolean(flags?.stop_requested);
  // last_stop_meta isn't on our ControlFlags type but the backend snapshot
  // routinely carries it — read defensively.
  const lastStopMeta = (flags as Record<string, unknown> | undefined)?.last_stop_meta as
    | { ts?: string; requested_by_user_id?: string }
    | undefined;

  const pauseReason = isPaused
    ? "Already paused"
    : isStopRequested
      ? "Runner stopped — restart to enable"
      : undefined;
  const resumeReason = !isPaused
    ? "Runner is not paused"
    : isStopRequested
      ? "Runner stopped — restart to enable"
      : undefined;
  const stopReason = isStopRequested ? "Already stopping" : undefined;

  return (
    <div className="space-y-3">
      <ContextStatusBlock
        isStopRequested={isStopRequested}
        isRunnerResponsive={isRunnerResponsive}
        snapshotTs={snapshotTs}
        lastStopMeta={lastStopMeta}
      />
      <div className="flex flex-wrap items-center gap-2">
        <PauseDialog
          disabled={isPaused || isStopRequested || pause.isPending}
          disabledReason={pauseReason}
          pending={pause.isPending}
          onConfirm={async () => {
            try {
              const r = await pause.mutateAsync();
              toast.success("Runner paused", { description: `request_id: ${r.request_id}` });
            } catch (e) {
              handleError(e, "Pause failed");
            }
          }}
        />
        <ResumeDialog
          disabled={!isPaused || isStopRequested || resume.isPending}
          disabledReason={resumeReason}
          pending={resume.isPending}
          onConfirm={async () => {
            try {
              const r = await resume.mutateAsync();
              toast.success("Runner resumed", { description: `request_id: ${r.request_id}` });
            } catch (e) {
              handleError(e, "Resume failed");
            }
          }}
        />
        <StopDialog
          disabled={isStopRequested || stop.isPending}
          disabledReason={stopReason}
          pending={stop.isPending}
          onConfirm={async () => {
            try {
              const r = await stop.mutateAsync();
              toast.success("Stop requested", {
                description: `Runner will close all positions and exit. request_id: ${r.request_id}`,
              });
            } catch (e) {
              handleError(e, "Stop failed");
            }
          }}
        />
      </div>
    </div>
  );
}

function ContextStatusBlock({
  isStopRequested,
  isRunnerResponsive,
  snapshotTs,
  lastStopMeta,
}: {
  isStopRequested: boolean;
  isRunnerResponsive: boolean | undefined;
  snapshotTs: string | null | undefined;
  lastStopMeta:
    | { ts?: string; requested_by_user_id?: string }
    | undefined;
}) {
  if (isStopRequested) {
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
        <div className="flex items-start gap-2 text-destructive">
          <PowerOff className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="space-y-1">
            <div className="font-medium">Runner is stopped</div>
            <p className="text-destructive/90">
              Controls are disabled. Restart the runner from your terminal to resume. The
              snapshot will refresh automatically once it&apos;s back.
            </p>
            {lastStopMeta?.ts && (
              <p className="text-xs text-destructive/70">
                Last stop: {relativeTime(lastStopMeta.ts)}
                {lastStopMeta.requested_by_user_id ? (
                  <> by {lastStopMeta.requested_by_user_id}</>
                ) : null}
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }
  if (isRunnerResponsive === false) {
    return (
      <div className="rounded-md border border-yellow-500/40 bg-yellow-500/10 p-3 text-sm">
        <div className="flex items-start gap-2 text-yellow-400">
          <WifiOff className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="space-y-1">
            <div className="font-medium">Runner is offline</div>
            <p className="text-yellow-400/90">
              Pause/Resume requests will queue as flag files and be applied when the runner
              reconnects.
            </p>
            {snapshotTs && (
              <p className="text-xs text-yellow-400/70">
                Last update {relativeTime(snapshotTs)}.
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }
  return null;
}

function PauseDialog({
  disabled,
  disabledReason,
  pending,
  onConfirm,
}: {
  disabled: boolean;
  disabledReason?: string;
  pending: boolean;
  onConfirm: () => Promise<void>;
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled}
          title={disabled ? disabledReason : undefined}
          aria-disabled={disabled}
        >
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PauseCircle className="h-4 w-4" />}
          Pause
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Pause the runner?</AlertDialogTitle>
          <AlertDialogDescription>
            Existing positions stay open and continue to be marked. The runner stops opening new
            trades until you resume. This is a soft pause — no flag is set on positions, no
            shutdown.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={() => void onConfirm()}>Pause runner</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function ResumeDialog({
  disabled,
  disabledReason,
  pending,
  onConfirm,
}: {
  disabled: boolean;
  disabledReason?: string;
  pending: boolean;
  onConfirm: () => Promise<void>;
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled}
          title={disabled ? disabledReason : undefined}
          aria-disabled={disabled}
        >
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
          Resume
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Resume the runner?</AlertDialogTitle>
          <AlertDialogDescription>
            New positions can be opened again on the next bar.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={() => void onConfirm()}>Resume</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function StopDialog({
  disabled,
  disabledReason,
  pending,
  onConfirm,
}: {
  disabled: boolean;
  disabledReason?: string;
  pending: boolean;
  onConfirm: () => Promise<void>;
}) {
  const [confirmText, setConfirmText] = useState("");
  const matches = confirmText.trim().toUpperCase() === "STOP";
  return (
    <AlertDialog onOpenChange={(open) => !open && setConfirmText("")}>
      <AlertDialogTrigger asChild>
        <Button
          variant="destructive"
          size="sm"
          disabled={disabled}
          title={disabled ? disabledReason : undefined}
          aria-disabled={disabled}
        >
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <OctagonAlert className="h-4 w-4" />}
          Stop
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Stop the runner.</AlertDialogTitle>
          <AlertDialogDescription>
            All open positions will close at market. The runner will exit and need to be restarted
            from the terminal. This action is latched — re-enabling requires manual intervention on
            the host. Type <span className="font-mono text-foreground">STOP</span> below to confirm.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-2">
          <Label htmlFor="stop-confirm">Confirmation</Label>
          <Input
            id="stop-confirm"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            autoFocus
            placeholder="STOP"
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
            Stop runner
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
