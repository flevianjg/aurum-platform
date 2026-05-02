import { api } from "@/lib/api/client";
import type {
  AurumStatus,
  ClosedPositionsPage,
  ControlActionResponse,
  ControlState,
  DailyReport,
  EquityBar,
  InstrumentEngineState,
  OpenPosition,
} from "@/types/aurum";

export interface ClosedPositionsQuery {
  limit?: number;
  before?: string | null;
}

export const aurumApi = {
  status() {
    return api<AurumStatus>("/aurum/status");
  },
  equity(days = 7) {
    return api<EquityBar[]>(`/aurum/equity?days=${days}`);
  },
  openPositions() {
    return api<OpenPosition[]>("/aurum/positions/open");
  },
  closedPositions({ limit = 50, before }: ClosedPositionsQuery = {}) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (before) params.set("before", before);
    return api<ClosedPositionsPage>(`/aurum/positions/closed?${params.toString()}`);
  },
  regime() {
    return api<Record<string, InstrumentEngineState>>("/aurum/regime");
  },
  dailyReport(date?: string) {
    const q = date ? `?date=${encodeURIComponent(date)}` : "";
    return api<DailyReport>(`/aurum/report/daily${q}`);
  },
  control() {
    return api<ControlState>("/aurum/control");
  },
  pause() {
    return api<ControlActionResponse>("/aurum/pause", { method: "POST" });
  },
  resume() {
    return api<ControlActionResponse>("/aurum/resume", { method: "POST" });
  },
  stop() {
    return api<ControlActionResponse>("/aurum/stop", {
      method: "POST",
      headers: { "X-Confirm-Stop": "yes" },
    });
  },
};
