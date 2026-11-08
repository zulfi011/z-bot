export type Num = string | number;
/** Who opened a lot: the dip, a Mode C break, the pullback entry, or you. */
export type EntrySource = "signal" | "breakout" | "pullback" | "pyramid" | "manual";
/** An extra way in is simply on or off - every way in shares the coin's lots. */
export type EntryModule = { supported: boolean; enabled: boolean; open_lots: number };
/** One of the coin's lots: either a lot that is open, or an empty slot the next signal can fill. */
export type LotSlot = {
  number: number; state: "open" | "free"; source: EntrySource | null;
  position_id?: string; entry_time?: string; entry_fill_price?: Num; allocation_usd?: Num;
  mode?: "trend" | "giveback"; armed?: boolean; trend_exit_pending?: boolean;
  stop_price?: Num | null; parent_position_id?: string | null;
  unrealized_usd?: Num | null; unrealized_pct?: Num | null;
  /** Which coin holds this slot of the shared pot, and whether it is the coin on screen. */
  symbol?: string | null; label?: string; mine?: boolean;
};
export type Interval = "1m" | "3m" | "5m" | "15m" | "1h" | "4h" | "1d";
export type Period = "1d" | "7d" | "1m" | "3m" | "6m" | "1y" | "all";

export type Account = {
  timestamp: string; usdt_free: Num; usdt_locked: Num; bnb_free: Num; bnb_value_usd: Num; allocated_usd: Num;
  open_position_value_usd: Num; open_position_cost_usd: Num; open_positions: number; realized_pnl_usd: Num;
  unrealized_pnl_usd: Num; strategy_pnl_usd: Num; wallet_value_usd: Num; total_value_usd: Num; fees_usd: Num;
  trading_mode: string;
};
export type Position = {
  position_id: string; symbol: string; coin: string; stop_pct: Num; trail_activation_pct: Num; trail_giveback_pct: Num; lot_number: number; entry_source: EntrySource; entry_time: string; entry_fill_price: Num;
  quantity: Num; allocation_usd: Num; entry_fee_usd: Num; entry_fee_asset: string; bars_held: number; trailing_active: boolean;
  peak_price: Num | null; current_price: Num | null; market_value_usd: Num | null; unrealized_pnl_usd: Num | null;
  unrealized_pct: Num | null; stop_price: Num; activation_price: Num; trail_price: Num | null;
  /** "trend" rides the moving-average line (Mode A); "giveback" hands back a share of the peak gain (Mode B). */
  exit_mode: "trend" | "giveback"; trend_exit_pending: boolean; trend_ema_minutes: number | null;
  parent_position_id?: string | null;
  distance_to_stop_pct: Num | null; distance_to_activation_pct: Num | null; activation_progress_pct: Num;
  close_estimate: CloseEstimate | null;
};
/** What closing a lot right now would return, after exit slippage and fee. */
export type CloseEstimate = {
  price: Num; exit_fill_price: Num; fee_usd: Num; fee_asset: string; slippage_usd: Num; cash_back_usd: Num;
  net_pnl_usd: Num; net_return_pct: Num;
};
export type Trade = {
  trade_id: string; symbol: string; position_id: string; entry_source: string; entry_time: string; exit_time: string; allocation_usd: Num;
  entry_fill_price: Num; exit_fill_price: Num; entry_fee_usd: Num; exit_fee_usd: Num; bnb_fees_usd: Num; slippage_usd: Num;
  exit_reason: string; exit_mode: "trend" | "giveback" | null;
  duration_minutes: number; net_return_pct: Num; net_pnl_usd: Num;
};
export type Order = {
  order_id: string; symbol: string; position_id: string; side: "buy" | "sell"; requested_at: string; raw_price: Num; fill_price: Num;
  quantity: Num; notional_usd: Num; fee_usd: Num; fee_asset: string; fee_bnb: Num; slippage_usd: Num;
};
export type SignalRow = {
  episode_id: string; touch_time: string; average_value: Num; episode_status: string; signal_id: string | null;
  status: string | null; reason: string | null; entry_time: string | null; details: Record<string, unknown>;
};
export type ControlRequest = {
  request_id: string; kind: string; symbol: string | null; amount_usd: Num | null; position_id: string | null; status: string;
  reason: string | null; requested_at: string; processed_at: string | null; details: Record<string, unknown>;
};
export type Alert = { alert_key: string; severity: string; status: string; title: string; message: string; last_seen_at: string; resolved_at: string | null };
export type LogEntry = { id: number; timestamp: string; level: string; component: string; event_type: string; details: Record<string, unknown> };
export type ChartPoint = {
  open_time: string; open: Num; high: Num; low: Num; close: Num; signal_average: Num | null;
  /** The Mode A trend line, on charts slow enough to need it and fast enough to draw it. */
  trend_line?: Num | null;
  /** The Mode C band, on buckets where the price really was consolidating. */
  zone_top?: Num | null; zone_bottom?: Num | null;
  /** The pullback entry's line, and whether a pullback was armed (a close above the line would buy). */
  pullback_line?: Num | null; pullback_armed?: boolean;
};
export type Marker = {
  position_id: string; lot_number: number; entry_source: EntrySource; entry_time: string; entry_fill_price: Num;
  exit_time: string | null; exit_fill_price: Num | null; exit_reason: string | null; realized_pnl_usd: Num | null; status: string;
  trailing_started_at: string | null; trailing_start_price: Num; trade_number: number;
  trend_exit_active?: boolean; parent_position_id?: string | null;
};
export type CoinMoney = {
  symbol: string; name: string; label: string; trading_enabled: boolean; configured: boolean; lot_size_usd: Num; lots: number;
  entries: Record<string, { enabled: boolean; supported: boolean }>;
  target_capital_usd: Num; open_lots: number; open_cost_usd: Num; open_value_usd: Num;
  capital_usd: Num; value_usd: Num; realized_pnl_usd: Num; unrealized_pnl_usd: Num;
};
/** The one pot every switched-on coin shares: lots x lot size, first come first served. */
export type Pot = {
  lots: number; lot_size_usd: Num; total_usd: Num; open_lots: number; free_lots: number;
  next_lot_usd: Num | null; coins_on: number;
};

export type Strategy = {
  strategy_id: string; name: string; symbol: string; signal_timeframe: string; signal_average_days: number;
  touch_zone_pct: number; confirmation_wait_minutes: number; blocked_entry_hours_utc: { start: number; end: number } | null;
  stop_pct: Num; trail_activation_pct: Num; trail_giveback_pct: Num; drawdown_review_pct: Num; requires_close_above_30d: boolean; maximum_above_30d_pct: Num | null;
  reference_capital_usd: Num; usdt_fee_bps: Num; bnb_fee_bps: Num; slippage_bps: Num; backtest: string;
  pullback: { ema_minutes: number; dwell_minutes: number; requires_uptrend: boolean } | null;
  pyramid: { step_pct: Num; maximum_adds: number; add_exit: "own" | "with_parent" } | null;
};
export type Stats = {
  trades: number; wins: number; losses: number; win_rate_pct: Num | null; profit_factor: Num | null; gross_win_usd: Num;
  gross_loss_usd: Num; average_win_pct: Num | null; average_loss_pct: Num | null; best_pct: Num | null; worst_pct: Num | null;
  average_hold_minutes: Num | null; trailing_exits: number; stop_exits: number; manual_exits: number; today_pnl_usd: Num;
  realized_usd: Num; fees_usd: Num; slippage_usd: Num;
};
/** `open_lots` is this coin's; `max_lots`, `free_lots` and `slots` are the shared pot's, across every coin. */
export type Lots = {
  next_lot_usd: Num | null; lot_number: number; slot_free: boolean; free_lots: number; free_usdt: Num;
  shortfall_usd: Num; open_lots: number; shared_open_lots: number; max_lots: number; lot_size_usd: Num;
  target_capital_usd: Num; slots: LotSlot[];
};
/** The pyramid add-on right now: its lots, and what each open lot needs before another is added. */
export type PyramidView = {
  step_pct: Num; maximum_adds: number; add_exit: "own" | "with_parent";
  blocked_entry_hours: number[] | null; enabled: boolean;
  adds_open: number; adds_total: number;
  parents: { position_id: string; lot_number: number; source: EntrySource; entry_fill_price: Num; adds: number;
    adds_left: number; next_add_price: Num | null; distance_to_add_pct: Num | null; above_line: boolean | null }[];
};
/** The pullback entry right now. */
export type PullbackView = {
  ema_minutes: number; ema_hours: number; dwell_minutes: number; requires_uptrend: boolean; uptrend: boolean;
  line: Num | null; line_at: string | null; below_since: string | null; below_minutes: number; minutes_to_arm: number;
  distance_to_line_pct: Num | null;
  state: "warming_up" | "no_uptrend" | "above" | "dipping" | "armed";
  last_signal: { signal_id: string; at: string; status: string; entry_time: string | null; below_minutes: number | null } | null;
  activation_at: string | null; checked_at: string | null;
};

/** Everything one coin page shows. */
export type CoinView = {
  symbol: string; label: string; name: string; trading_enabled: boolean; configured: boolean;
  pending_trading_change: { request_id: string; kind: "coin_pause" | "coin_resume"; requested_at: string; details: Record<string, unknown> } | null;
  strategy: Strategy;
  health: { market_age_seconds: number | null; signal_engine: string };
  market: { price: Num | null; open_time: string | null; change_24h_pct: Num | null };
  setup: {
    signal_average: Num | null; zone_lower: Num | null; zone_upper: Num | null; zone_state: "below" | "inside" | "above" | null;
    distance_to_zone_pct: Num | null; average_7d: Num | null; average_15d: Num | null; average_30d: Num | null;
    regime: string; trend_allows_entries: boolean; entry_window_open: boolean; entry_window_changes_at: string | null;
    pending_episode_since: string | null; signal_engine: string; activation_at: string | null;
  };
  /** Mode C: the quiet band being watched, and any break waiting out its confirmation. */
  consolidation: {
    chart_minutes: number; zone_bars: number; zone_hours: number; maximum_zone_pct: Num;
    confirmation_wait_minutes: number; stop_pct: Num; trail_activation_pct: Num; trail_giveback_pct: Num;
    quiet: boolean; zone_top: Num | null; zone_bottom: Num | null; zone_width_pct: Num | null;
    zone_since: string | null; width_needed_pct: Num | null; distance_to_break_pct: Num | null;
    state: "quiet" | "breaking" | "too_wide" | "warming_up";
    pending_break: { signal_id: string; broke_at: string; confirm_at: string | null; zone_top: Num | null } | null;
    checked_at: string | null; breakouts_seen: number | null;
  } | null;
  /** How a lot bought right now would take profit, and the line it would be held against. */
  exit_plan: {
    has_trend_exit: boolean; ema_minutes: number | null; requires_uptrend: boolean;
    next_lot_mode: "trend" | "giveback"; trend_line: Num | null;
    giveback_pct: Num; activation_pct: Num; stop_pct: Num;
  };
  pullback: PullbackView | null;
  pyramid: PyramidView | null;
  entries: Record<string, EntryModule>;
  lots: Lots;
  money: CoinMoney;
  stats: Stats;
  signal_counts: { touches: number; confirmed: number; skipped_time_window: number; rejected_trend: number; not_confirmed: number; not_from_below: number;
    breakouts: number; breakouts_confirmed: number; pullbacks: number; pullbacks_confirmed: number; pullbacks_skipped: number };
  positions: Position[]; signals: SignalRow[]; trades: Trade[]; orders: Order[];
  chart: ChartPoint[]; markers: Marker[];
};

export type Dashboard = {
  generated_at: string;
  coin_order: string[];
  coins: Record<string, CoinView>;
  health: { status: string; market_age_seconds: number | null; coins_updated: Record<string, string | null> };
  account: Account | null;
  binance: { connected: boolean; message?: string; usdt_free: Num; wallet_value_usdt?: Num; checks: BinanceCheck[] };
  trading: { mode: "off" | "shadow" | "live"; daily_loss_limit_usd: Num | null; maximum_open_value_usd: Num | null };
  money: {
    usdt_free: Num; budget_usd: Num; left_to_allocate_usd: Num; allocated_usd: Num; in_trades_usd: Num;
    pot: Pot;
    limits: { minimum_lot_usd: Num; maximum_lot_usd: Num; maximum_lots: number };
    coins: CoinMoney[];
  };
  bnb: {
    enabled: boolean; price: Num | null; balance: Num; value_usd: Num; lot_size_usd: Num; round_trip_fee_usd: Num;
    round_trip_fee_bnb: Num | null; round_trips_left: number | null; spent_bnb: Num; bnb_fees_usd: Num;
    usdt_fees_usd: Num; bnb_fills: number; usdt_fills: number; saved_usd: Num; updated_at: string | null;
  };
  stats: Stats;
  positions: Position[]; trades: Trade[]; requests: ControlRequest[];
  chart_interval: Interval; alerts: Alert[]; logs: LogEntry[];
};

export type BinanceCheck = { level: "ok" | "info" | "warning" | "danger"; title: string; detail: string };
export type BinanceCoin = {
  symbol: string; asset: string; name: string; free: Num; locked: Num; price: Num; value_usdt: Num;
  fees: { maker_pct: number; taker_pct: number; bnb_discount_pct: number } | null;
};
export type BinanceAccount = {
  connected: boolean; checked_at: string; state?: string; message?: string; binance_code?: number;
  account_type?: string; can_trade?: boolean;
  usdt?: { free: Num; locked: Num };
  bnb?: { free: Num; locked: Num; price: Num; value_usdt: Num };
  coins?: BinanceCoin[]; other_assets?: { asset: string; free: Num; value_usdt: Num }[];
  total_value_usdt?: Num; bnb_fee_discount?: boolean; checks?: BinanceCheck[];
};

export type ProfitPeriod = "24h" | "7d" | "15d" | "30d" | "90d" | "mtd" | "all" | "custom";
export type ProfitSummary = {
  trades: number; wins: number; losses: number; win_rate_pct: Num | null; gross_pnl_usd: Num; fees_usd: Num;
  fees_in_bnb_usd: Num; fees_in_usdt_usd: Num; net_pnl_usd: Num; won_usd: Num; lost_usd: Num;
  profit_factor: Num | null; average_win_usd: Num | null; average_loss_usd: Num | null; best_usd: Num | null;
  worst_usd: Num | null; traded_value_usd: Num; return_on_traded_pct: Num | null; average_hold_minutes: Num | null;
  bnb_spent?: Num; unrealized_pnl_usd?: Num; open_lots?: number; open_value_usd?: Num;
};
export type ProfitCoin = ProfitSummary & { symbol: string; label: string; open_lots: number; unrealized_pnl_usd: Num };
export type Profit = {
  period: ProfitPeriod; start: string; end: string; summary: ProfitSummary; coins: ProfitCoin[];
  daily: { date: string; net_pnl_usd: Num; trades: number; cumulative_usd: Num }[];
};

export type Reachability = {
  state: "reachable" | "blocked" | "limited" | "error" | "unreachable"; message: string; checked_at: string;
  status_code?: number; public_ip?: string;
};

export type LeaderPeriod = "1d" | "7d" | "30d" | "all";
export type LeaderCoin = {
  symbol: string; label: string; name: string; trading_enabled: boolean; capital_usd: Num; pnl_usd: Num; return_pct: Num;
  trades: number; wins: number; realized_usd: Num; unrealized_usd: Num; open_lots: number; rank: number;
  series: { t: string; pnl_usd: Num }[];
};
export type Leaderboard = { period: LeaderPeriod; start: string; generated_at: string; bucket: string; coins: LeaderCoin[] };

export type EquityPoint = {
  timestamp: string; wallet_value_usd: Num; usdt_free: Num; positions_usd: Num; bnb_value_usd: Num;
  strategy_pnl_usd: Num; realized_pnl_usd: Num;
};
export type EquityHistory = {
  period: Period; bucket: string; start: string; end: string; points: EquityPoint[];
  summary: { strategy_pnl_change_usd: Num; high_value_usd: Num; low_value_usd: Num } | null;
};

export const COIN_ORDER = ["SOLUSDT", "ETHUSDT", "BTCUSDT", "AAVEUSDT", "TRXUSDT"];
export const coinLabel = (symbol: string | null | undefined) => (symbol ?? "").replace(/USDT$/, "");

/** The server refused a control action because this device is not unlocked (or its session ended). */
export class LockedError extends Error {}

// Older builds kept the raw control key in the browser; sessions replace that, so drop any copy left behind.
try { localStorage.removeItem("sol-desk-control-key"); } catch { /* storage unavailable */ }

export type DeviceSession = { unlocked: boolean; controls_enabled: boolean; expires_at: string | null };

export const sessionStatus = () => getJson<DeviceSession>("/api/v1/session");

/** Trade the control key for this device's session cookie. The key is not kept anywhere in the browser. */
export async function unlockDevice(key: string): Promise<DeviceSession> {
  const response = await fetch("/api/v1/session", {
    method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : `Unlock failed (${response.status})`);
  return { ...result, controls_enabled: true } as DeviceSession;
}

export async function lockDevice(): Promise<void> {
  await fetch("/api/v1/session", { method: "DELETE", credentials: "same-origin" });
}

/** Read a page that needs an unlocked device (real account data). */
export async function getJsonUnlocked<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store", credentials: "same-origin" });
  if (response.status === 403) throw new LockedError("This device is locked.");
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json() as Promise<T>;
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json() as Promise<T>;
}

export async function control(path: string, method = "POST", body?: unknown): Promise<Record<string, unknown>> {
  const response = await fetch(path, {
    method, credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json().catch(() => ({}));
  if (response.status === 403) throw new LockedError("This device is locked.");
  if (!response.ok) {
    const detail = (result as { detail?: unknown }).detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail) ? "Check the amount and try again" : `Request failed (${response.status})`);
  }
  return result as Record<string, unknown>;
}
