"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Fingerprint, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { loginWithPasskey } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { browserSupportsPasskeys } from "@/lib/auth/webauthn";

export function PasskeyLogin() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const supported = browserSupportsPasskeys();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await loginWithPasskey(email.trim() || undefined);
      router.replace("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        // Cancelled / NotAllowedError from navigator.credentials
        setError(err.name === "NotAllowedError" ? "Authentication cancelled" : err.message);
      } else {
        setError("Authentication failed");
      }
    } finally {
      setBusy(false);
    }
  }

  if (!supported) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Passkeys not supported</AlertTitle>
        <AlertDescription>
          This browser does not support WebAuthn. Please use a recent version of Safari, Chrome, Edge, or Firefox.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="email">Email (optional)</Label>
        <Input
          id="email"
          type="email"
          placeholder="leave blank to use any registered passkey on this device"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username webauthn"
        />
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Button type="submit" className="w-full" disabled={busy} size="lg">
        {busy ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Fingerprint className="h-4 w-4" />
        )}
        Sign in with passkey
      </Button>
    </form>
  );
}
