// Mirrors backend /aurum/* response shapes. Keep in sync with
// backend/app/schemas/aurum.py.

export interface BrokerSummary {
  equity?: number;
  peak_equity?: number;
  drawdown_pct?: number;
  open_pnl?: number;
  n_open_positions?: number;
  n_closed_total?: number;
  n_closed_today?: number;
  today_pnl_dollars?: number;
  today_costs_dollars?: number;
  total_pnl_dollars?: number;
  currency?: string;
}

export interface InstrumentEngineState {
  last_regime?: "low" | "med" | "high" | string;
  last_bar_utc?: string;
  last_fit_utc?: string;
  model_ready?: boolean;
  buffer_bars?: number;
  n_bars?: number;
  n_signals?: number;
  skipped?: {
    low_vol?: number;
    high_vol?: number;
    no_candidate?: number;
    below_threshold?: number;
  };
}

export interface ControlFlags {
  paused: boolean;
  stop_requested: boolean;
  last_pause_meta?: Record<string, unknown> | null;
}

export interface OpenPosition {
  position_id?: string;
  symbol?: string;
  instrument?: string;
  side?: "BUY" | "SELL" | string;
  direction?: "BUY" | "SELL" | string;
  volume?: number;
  open_price?: number;
  entry_price?: number;
  current_price?: number;
  unrealized_pnl?: number;
  open_time?: string;
  bars_held?: number;
  horizon?: number;
  sl?: number | null;
  tp?: number | null;
  // Allow runner-side additions to flow through without breaking the type.
  [key: string]: unknown;
}

export interface AurumStatus {
  snapshot_ts: string;
  snapshot_seq?: number;
  runner_pid?: number;
  runner_started_ts?: string;
  instruments?: string[];
  final?: boolean;
  broker?: BrokerSummary;
  engine?: Record<string, InstrumentEngineState>;
  open_positions?: OpenPosition[];
  control_flags?: ControlFlags;
  health?: Record<string, unknown>;
  tick_age_seconds: number | null;
  is_runner_responsive: boolean;
}

export interface EquityBar {
  ts: string;
  equity: number | null;
  peak_equity: number | null;
  drawdown_pct: number | null;
}

export interface ClosedPositionRow {
  ts: string;
  instrument: string | null;
  payload: Record<string, unknown> & {
    side?: string;
    direction?: string;
    pnl?: number;
    entry_price?: number;
    exit_price?: number;
    open_time?: string;
    close_time?: string;
    duration_seconds?: number;
    bars_held?: number;
  };
}

export interface ClosedPositionsPage {
  items: ClosedPositionRow[];
  next_before: string | null;
}

export interface DailyReport {
  date: string;
  n_trades: number;
  n_wins: number;
  n_losses: number;
  win_rate: number | null;
  total_pnl: number;
  avg_win: number | null;
  avg_loss: number | null;
  per_instrument: Record<string, { n_trades: number; total_pnl: number }>;
}

export interface ControlState {
  paused: boolean;
  stop_requested: boolean;
  pause_meta: Record<string, unknown> | null;
}

export interface ControlActionResponse {
  request_id: string;
  action: "pause" | "resume" | "stop";
  paused?: boolean;
  stop_requested?: boolean;
}
