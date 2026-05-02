"use client";
import { useState } from "react";
import { KeyRound, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { registerPasskey } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { browserSupportsPasskeys } from "@/lib/auth/webauthn";

export function PasskeyRegister() {
  const [email, setEmail] = useState("");
  const [nickname, setNickname] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  if (!browserSupportsPasskeys()) {
    return null; // PasskeyLogin handles the unsupported case
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    setBusy(true);
    try {
      await registerPasskey(email.trim(), nickname.trim() || undefined);
      setSuccess(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.name === "NotAllowedError" ? "Registration cancelled" : err.message);
      } else {
        setError("Registration failed");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="reg-email">Email</Label>
        <Input
          id="reg-email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          autoComplete="username"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="reg-nickname">Device name (optional)</Label>
        <Input
          id="reg-nickname"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          placeholder="iPhone, Yubikey, etc."
        />
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {success && (
        <Alert variant="success">
          <AlertTitle>Passkey registered</AlertTitle>
          <AlertDescription>You can now sign in.</AlertDescription>
        </Alert>
      )}
      <Button type="submit" variant="outline" className="w-full" disabled={busy}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
        Register a new passkey
      </Button>
    </form>
  );
}
