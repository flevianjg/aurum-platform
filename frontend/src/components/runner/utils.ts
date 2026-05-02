/**
 * Formatters and helpers for runner UI.
 */

import { formatDistanceToNowStrict } from "date-fns";

import { cn } from "@/lib/utils/cn";

const SYMBOLS: Record<string, string> = {
  USD: "$",
  EUR: "€",
  GBP: "£",
  JPY: "¥",
  CHF: "CHF ",
  AUD: "A$",
  CAD: "C$",
};

export function currencySymbol(code: string | null | undefined): string {
  if (!code) return "$";
  return SYMBOLS[code.toUpperCase()] ?? `${code} `;
}

export function formatMoney(
  value: number | null | undefined,
  currency: string | null | undefined = "USD",
  digits = 2,
): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  return `${sign}${currencySymbol(currency)}${abs.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function formatPercent(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function pnlClass(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value) || value === 0) {
    return "text-muted-foreground";
  }
  return value > 0 ? "text-success" : "text-destructive";
}

export function pnlBgClass(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value) || value === 0) {
    return "bg-muted text-muted-foreground";
  }
  return value > 0
    ? "bg-success/15 text-success"
    : "bg-destructive/15 text-destructive";
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return formatDistanceToNowStrict(new Date(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

export function formatHoldDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return "—";
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const remM = m % 60;
  return remM > 0 ? `${h}h ${remM}m` : `${h}h`;
}

export type RegimeLevel = "low" | "med" | "medium" | "high" | string;

export function regimeBadgeClass(regime: RegimeLevel | undefined): string {
  if (!regime) return "bg-muted text-muted-foreground";
  const r = regime.toLowerCase();
  if (r === "low") return "bg-success/15 text-success border-success/30";
  if (r === "med" || r === "medium") return "bg-yellow-500/15 text-yellow-400 border-yellow-500/30";
  if (r === "high") return "bg-destructive/15 text-destructive border-destructive/30";
  return "bg-muted text-muted-foreground";
}

export function watchdogState(
  tick_age_seconds: number | null | undefined,
): { tone: "live" | "delayed" | "offline"; label: string } {
  if (tick_age_seconds == null) return { tone: "offline", label: "OFFLINE" };
  if (tick_age_seconds < 30) return { tone: "live", label: "LIVE" };
  if (tick_age_seconds < 60) return { tone: "delayed", label: "DELAYED" };
  return { tone: "offline", label: "UNRESPONSIVE" };
}

export const watchdogToneClass = {
  live: "bg-success/15 text-success border-success/30",
  delayed: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  offline: "bg-destructive/15 text-destructive border-destructive/30",
} as const;

export { cn };
