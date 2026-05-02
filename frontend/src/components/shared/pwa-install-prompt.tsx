"use client";
import { useEffect, useState } from "react";
import { Download, X } from "lucide-react";

import { Button } from "@/components/ui/button";

const DISMISS_KEY = "aurum.pwaInstall.dismissedUntil";
const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

interface BeforeInstallPromptEvent extends Event {
  readonly platforms: ReadonlyArray<string>;
  prompt(): Promise<void>;
  readonly userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  if (window.matchMedia("(display-mode: standalone)").matches) return true;
  // iOS Safari
  return Boolean((window.navigator as unknown as { standalone?: boolean }).standalone);
}

function dismissedRecently(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const raw = window.localStorage.getItem(DISMISS_KEY);
    if (!raw) return false;
    return Number(raw) > Date.now();
  } catch {
    return false;
  }
}

export function PwaInstallPrompt() {
  const [event, setEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    if (isStandalone() || dismissedRecently()) return;

    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      setEvent(e as BeforeInstallPromptEvent);
      setHidden(false);
    };
    const onInstalled = () => {
      setEvent(null);
      setHidden(true);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (hidden || !event) return null;

  async function handleInstall() {
    if (!event) return;
    await event.prompt();
    const choice = await event.userChoice;
    if (choice.outcome === "dismissed") rememberDismissal();
    setEvent(null);
    setHidden(true);
  }

  function handleDismiss() {
    rememberDismissal();
    setHidden(true);
  }

  return (
    <div
      role="region"
      aria-label="Install Aurum"
      className="hidden items-center gap-2 rounded-md border bg-card px-2 py-1 text-xs sm:flex"
    >
      <span className="text-muted-foreground">Install Aurum</span>
      <Button size="sm" variant="default" className="h-7 px-2" onClick={handleInstall}>
        <Download className="h-3 w-3" /> Install
      </Button>
      <Button
        size="icon"
        variant="ghost"
        className="h-6 w-6"
        onClick={handleDismiss}
        aria-label="Dismiss install prompt"
      >
        <X className="h-3 w-3" />
      </Button>
    </div>
  );
}

function rememberDismissal() {
  try {
    window.localStorage.setItem(DISMISS_KEY, String(Date.now() + SEVEN_DAYS_MS));
  } catch {
    /* ignore */
  }
}
