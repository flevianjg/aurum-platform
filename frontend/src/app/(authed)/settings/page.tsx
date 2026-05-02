"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { formatDistanceToNow } from "date-fns";
import { Check, KeyRound, Loader2, LogOut, Pencil, Plus, Trash2 } from "lucide-react";

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
import { Separator } from "@/components/ui/separator";
import { toast } from "@/components/ui/toaster";
import { useAuthStore } from "@/lib/store/auth-store";
import {
  useLogoutAll,
  usePasskeys,
  useRemovePasskey,
  useRenamePasskey,
} from "@/lib/hooks/use-passkeys";
import { registerPasskey } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { formatDateTime } from "@/lib/utils/format";
import type { PasskeyOut } from "@/types/api";

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Profile, devices, and sessions</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Profile</CardTitle>
          <CardDescription>Editing lands later — Phase 5 invitation flow.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <Row label="Display name" value={user?.display_name ?? "—"} />
          <Row label="Email" value={user?.email ?? "—"} />
          <Row label="Role" value={user?.role ?? "—"} />
        </CardContent>
      </Card>

      <PasskeysCard />
      <SessionsCard />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function PasskeysCard() {
  const user = useAuthStore((s) => s.user);
  const { data, isLoading, error, refetch } = usePasskeys();
  const [adding, setAdding] = useState(false);

  async function handleAdd() {
    if (!user?.email) {
      toast.error("Cannot register a passkey without your email loaded");
      return;
    }
    setAdding(true);
    try {
      await registerPasskey(user.email, "New device");
      toast.success("Passkey registered", { description: "Sign in with it next time." });
      void refetch();
    } catch (err) {
      handleError(err, "Registration cancelled or failed");
    } finally {
      setAdding(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
        <div className="space-y-1.5">
          <CardTitle className="text-base">Passkeys</CardTitle>
          <CardDescription>Devices that can sign in to this account.</CardDescription>
        </div>
        <Button size="sm" onClick={handleAdd} disabled={adding}>
          {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          Add a passkey
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <Skeleton className="h-20 w-full" />}
        {error instanceof ApiError && (
          <Alert variant="destructive">
            <AlertTitle>Failed to load passkeys</AlertTitle>
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        )}
        {data && data.length === 0 && (
          <p className="text-sm text-muted-foreground">No passkeys registered yet.</p>
        )}
        {data && data.length > 0 && (
          <div className="space-y-2">
            {data.map((p) => (
              <PasskeyRow key={p.id} passkey={p} canRemove={data.length > 1} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PasskeyRow({
  passkey,
  canRemove,
}: {
  passkey: PasskeyOut;
  canRemove: boolean;
}) {
  const rename = useRenamePasskey();
  const remove = useRemovePasskey();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(passkey.nickname ?? "");

  async function handleRename() {
    const value = draft.trim();
    if (!value) {
      toast.error("Nickname cannot be empty");
      return;
    }
    try {
      await rename.mutateAsync({ id: passkey.id, nickname: value });
      toast.success("Renamed");
      setEditing(false);
    } catch (err) {
      handleError(err);
    }
  }

  async function handleRemove() {
    try {
      await remove.mutateAsync(passkey.id);
      toast.success("Passkey removed");
    } catch (err) {
      handleError(err);
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <KeyRound className="mt-0.5 h-4 w-4 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          {editing ? (
            <div className="flex items-center gap-2">
              <Input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                className="h-8"
                maxLength={64}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleRename();
                  if (e.key === "Escape") {
                    setEditing(false);
                    setDraft(passkey.nickname ?? "");
                  }
                }}
              />
              <Button size="icon" className="h-8 w-8" onClick={handleRename} disabled={rename.isPending}>
                {rename.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
              </Button>
            </div>
          ) : (
            <>
              <div className="truncate font-medium">{passkey.nickname || "Unnamed device"}</div>
              <div className="text-xs text-muted-foreground">
                Added {formatDateTime(passkey.created_at)}
                {passkey.last_used_at &&
                  ` · last used ${formatDistanceToNow(new Date(passkey.last_used_at), { addSuffix: true })}`}
              </div>
            </>
          )}
        </div>
      </div>
      {!editing && (
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
            <Pencil className="h-4 w-4" /> Rename
          </Button>
          <RemoveButton disabled={!canRemove} onConfirm={handleRemove} pending={remove.isPending} />
        </div>
      )}
    </div>
  );
}

function RemoveButton({
  disabled,
  onConfirm,
  pending,
}: {
  disabled: boolean;
  onConfirm: () => void;
  pending: boolean;
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          size="sm"
          variant="ghost"
          className="text-destructive"
          disabled={disabled || pending}
          title={disabled ? "Cannot remove your only passkey" : undefined}
        >
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
          Remove
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove this passkey?</AlertDialogTitle>
          <AlertDialogDescription>
            You won&apos;t be able to use this device to sign in anymore. Make sure another passkey is
            registered before removing this one.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            Remove passkey
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function SessionsCard() {
  const router = useRouter();
  const logoutAll = useLogoutAll();

  async function handleSignOutAll() {
    try {
      await logoutAll.mutateAsync();
      toast.success("Signed out from all devices");
      router.replace("/login");
    } catch (err) {
      handleError(err);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Sessions</CardTitle>
        <CardDescription>
          Revokes every refresh token for this account, including this device. You&apos;ll be signed out.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Separator className="mb-4" />
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive" disabled={logoutAll.isPending}>
              {logoutAll.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogOut className="h-4 w-4" />}
              Sign out from all devices
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Sign out everywhere?</AlertDialogTitle>
              <AlertDialogDescription>
                This revokes every active session for this account. You&apos;ll need to sign in again
                with your passkey on each device.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                onClick={handleSignOutAll}
              >
                Sign out everywhere
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  );
}

function handleError(err: unknown, fallback = "Request failed") {
  if (err instanceof ApiError) {
    if (err.status === 409) {
      toast.error("Cannot remove last passkey", { description: err.message });
      return;
    }
    if (err.status === 429) {
      toast.error("Rate limited", {
        description: err.retryAfterSeconds ? `Retry in ${err.retryAfterSeconds}s` : "Try again shortly.",
      });
      return;
    }
    toast.error(`Request failed (${err.status})`, {
      description: err.requestId ? `request_id: ${err.requestId}` : err.message,
    });
    return;
  }
  if (err instanceof Error) {
    toast.error(fallback, { description: err.name === "NotAllowedError" ? "Cancelled" : err.message });
    return;
  }
  toast.error(fallback);
}
