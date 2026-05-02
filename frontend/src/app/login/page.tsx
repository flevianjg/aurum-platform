"use client";
import { useState } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { PasskeyLogin } from "@/components/auth/passkey-login";
import { PasskeyRegister } from "@/components/auth/passkey-register";

type Mode = "login" | "register";

export default function LoginPage() {
  const [mode, setMode] = useState<Mode>("login");
  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-12">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-2 text-center">
          <CardTitle className="text-2xl tracking-tight">Aurum</CardTitle>
          <CardDescription>
            {mode === "login"
              ? "Sign in with the passkey on this device"
              : "Register a new passkey to sign in"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {mode === "login" ? <PasskeyLogin /> : <PasskeyRegister />}
          <div className="flex items-center justify-center gap-2 text-sm">
            <span className="text-muted-foreground">
              {mode === "login" ? "New device?" : "Already registered?"}
            </span>
            <Button
              variant="link"
              className="h-auto p-0"
              onClick={() => setMode(mode === "login" ? "register" : "login")}
            >
              {mode === "login" ? "Register a passkey" : "Back to sign in"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
