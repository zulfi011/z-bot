import type { Num } from "./api";

export const n = (value: Num | null | undefined) => Number(value ?? 0);

export const usd = (value: Num | null | undefined, digits = 2) =>
  value == null ? "—" : `$${n(value).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;

/** A coin price with enough decimals to be useful: $77,393 · $2,515.40 · $101.40 · $0.3412 · $0.000012. */
export const price = (value: Num | null | undefined) => {
  if (value == null) return "—";
  const amount = Math.abs(n(value));
  const digits = amount >= 1000 ? 0 : amount >= 1 ? 2 : amount >= 0.01 ? 4 : 6;
  return usd(value, digits);
};

/** A coin quantity: 294.1 TRX · 0.9840 SOL · 0.001295 BTC. */
export const amount = (value: Num | null | undefined) => {
  if (value == null) return "—";
  const size = Math.abs(n(value));
  return n(value).toLocaleString("en-US", { maximumFractionDigits: size >= 100 ? 1 : size >= 1 ? 4 : 6,
                                            minimumFractionDigits: size >= 100 ? 1 : size >= 1 ? 4 : 6 });
};

/** A value that shows as 0.00 is neither a gain nor a loss: no minus sign, no red or green. */
const roundsToZero = (value: Num, digits = 2) => Math.abs(n(value)) < 0.5 / 10 ** digits;

export const signedUsd = (value: Num | null | undefined, digits = 2) => {
  if (value == null) return "—";
  const amount = roundsToZero(value, digits) ? 0 : n(value);
  return `${amount >= 0 ? "+" : "−"}$${Math.abs(amount).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
};

export const pct = (value: Num | null | undefined, digits = 2, signed = true) => {
  if (value == null) return "—";
  const amount = roundsToZero(value, digits) ? 0 : n(value);
  return `${signed && amount > 0 ? "+" : amount < 0 ? "−" : ""}${Math.abs(amount).toFixed(digits)}%`;
};

export const bnbAmount = (value: Num | null | undefined) => (value == null ? "—" : `${n(value).toFixed(5)} BNB`);

export const tone = (value: Num | null | undefined) => (value == null || roundsToZero(value) ? "" : n(value) > 0 ? "up" : "down");

export const time = (value: string | null | undefined, withDate = false) => {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC", hour: "2-digit", minute: "2-digit", hour12: false,
    ...(withDate ? { day: "2-digit", month: "short" } : {}),
  }).format(new Date(value)) + " UTC";
};

export const ago = (value: string | null | undefined) => {
  if (!value) return "—";
  const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 90) return `${Math.round(seconds)}s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} days ago`;
};

export const duration = (minutes: Num | null | undefined) => {
  if (minutes == null) return "—";
  const total = Math.round(n(minutes));
  if (total < 60) return `${total}m`;
  const hours = Math.floor(total / 60);
  return hours < 48 ? `${hours}h ${total % 60}m` : `${Math.floor(hours / 24)}d ${hours % 24}h`;
};

export const until = (value: string | null | undefined) => {
  if (!value) return "—";
  const minutes = Math.max(0, Math.round((new Date(value).getTime() - Date.now()) / 60000));
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
};

const REASONS: Record<string, string> = {
  trailing_stop: "Trailing stop", protective_stop: "Stop-loss", ambiguous_stop: "Stop-loss", manual_close: "Closed by you",
  time: "Time limit", confirmed: "Bought", pending_confirmation: "Waiting for green candle",
  skipped_time_window: "Skipped · 06–12 UTC", rejected_market_regime: "Skipped · downtrend",
  cancelled_at_episode_exit: "No green candle", expired_wait_limit: "No green candle in 30 min",
  observed_not_from_below: "Came from above", ignored_no_free_lot: "Skipped · no free lot",
  ignored_missing_candle: "Skipped · no price", ignored_coin_paused: "Skipped · coin off", rejected_below_30d_average: "Skipped · below 30-day avg",
  coin_pause: "Pause trading", coin_resume: "Resume trading", ignored_retired_strategy: "Skipped · old strategy", allocation: "Coin money",
  deposit: "Add funds", initial_deposit: "Starting capital", withdrawal: "Withdraw", bnb_purchase: "Buy BNB",
  manual_buy: "Buy now", close_position: "Close position", parent_exit: "Sold with its lot",
  break_even: "Break even", trend_exit: "Trend line",
};

export const label = (value: string | null | undefined) => (value ? REASONS[value] ?? value.replaceAll("_", " ") : "—");
