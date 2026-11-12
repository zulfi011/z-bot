import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { getJson, type CoinView, type Dashboard, type LeaderCoin, type LeaderPeriod, type Leaderboard as Board } from "./api";
import { n, pct, signedUsd, tone, usd } from "./format";
import { Card, CoinToken, ScrollList, Tabs } from "./ui";

const PERIODS: { value: LeaderPeriod; label: string }[] = [
  { value: "1d", label: "24h" }, { value: "7d", label: "7D" }, { value: "30d", label: "30D" }, { value: "all", label: "All" },
];
type Metric = "return" | "profit";
const MEDALS = ["gold", "silver", "bronze"];

const stored = <T extends string>(key: string, fallback: T, allowed: T[]): T => {
  try { const value = localStorage.getItem(key) as T | null; return value && allowed.includes(value) ? value : fallback; }
  catch { return fallback; }
};

/** Animates rows to their new place when the order changes (FLIP on offsetTop, so scrolling doesn't matter). */
function useReorderAnimation(order: string) {
  const rows = useRef(new Map<string, HTMLElement>());
  const last = useRef(new Map<string, number>());
  const previousOrder = useRef(order);
  useLayoutEffect(() => {
    const changed = previousOrder.current !== order;
    previousOrder.current = order;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    rows.current.forEach((element, key) => {
      const top = element.offsetTop;
      const before = last.current.get(key);
      last.current.set(key, top);
      if (!changed || reduce || before == null || Math.abs(before - top) < 1) return;
      element.animate([{ transform: `translateY(${before - top}px)` }, { transform: "translateY(0)" }],
        { duration: 450, easing: "cubic-bezier(.2,.8,.2,1)" });
    });
  });
  return (key: string) => (element: HTMLElement | null) => {
    if (element) rows.current.set(key, element); else rows.current.delete(key);
  };
}

function Sparkline({ points, up }: { points: number[]; up: boolean }) {
  if (points.length < 2 || points.every(value => Math.abs(value) < 0.005)) {
    return <svg className="spark" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden><line x1="0" x2="100" y1="16" y2="16" className="spark-zero" /></svg>;
  }
  const low = Math.min(0, ...points), high = Math.max(0, ...points), span = high - low || 1;
  const y = (value: number) => 30 - (value - low) / span * 28;
  const line = points.map((value, index) => `${index / (points.length - 1) * 100},${y(value)}`).join(" ");
  return <svg className={`spark ${up ? "up" : "down"}`} viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden>
    <line x1="0" x2="100" y1={y(0)} y2={y(0)} className="spark-zero" />
    <polygon points={`0,${y(0)} ${line} 100,${y(0)}`} className="spark-area" />
    <polyline points={line} className="spark-line" />
  </svg>;
}

function status(coin: CoinView): string {
  const setup = coin.setup, lots = coin.lots;
  if (!lots.max_lots && !coin.positions.length) return "Not set — give it money to trade";
  if (!coin.trading_enabled) return coin.positions.length ? "Off · open lots still managed" : "Off · no new trades";
  if (setup.pending_episode_since) return "Touch — waiting for a green candle";
  if (!setup.entry_window_open) return `Entries paused until ${String(coin.strategy.blocked_entry_hours_utc?.end ?? 0).padStart(2, "0")}:00 UTC`;
  if (!setup.trend_allows_entries && setup.regime !== "missing") return "Strong downtrend — skipping";
  if (lots.next_lot_usd == null) return lots.slot_free ? "Waiting for free USDT on Binance" : "All shared lots open";
  if (setup.zone_state === "below") return `${pct(setup.distance_to_zone_pct, 2, false)} below the entry zone`;
  if (setup.zone_state === "above") return `${pct(setup.distance_to_zone_pct, 2, false)} above the zone`;
  if (setup.zone_state === "inside") return "Inside the entry zone";
  return "Warming up";
}

export function LeaderboardCard({ data, onOpenCoin }: { data: Dashboard; onOpenCoin: (symbol: string) => void }) {
  const [period, setPeriod] = useState<LeaderPeriod>(() => stored("desk-leader-period", "7d", ["1d", "7d", "30d", "all"]));
  const [metric, setMetric] = useState<Metric>(() => stored("desk-leader-metric", "return", ["return", "profit"]));
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => getJson<Board>(`/api/v1/leaderboard?period=${period}`)
    .then(result => { setBoard(result); setError(null); })
    .catch(reason => setError(reason instanceof Error ? reason.message : "Unavailable")), [period]);
  // Rankings are built from closed trades and minute prices, so once a minute is live enough - refetching on every
  // 15-second dashboard refresh only loaded the server.
  useEffect(() => { load(); const timer = window.setInterval(() => document.visibilityState === "visible" && load(), 60_000); return () => window.clearInterval(timer); }, [load]);
  useEffect(() => { try { localStorage.setItem("desk-leader-period", period); localStorage.setItem("desk-leader-metric", metric); } catch { /* ignore */ } }, [period, metric]);

  const value = (coin: LeaderCoin) => metric === "return" ? n(coin.return_pct) : n(coin.pnl_usd);
  const ranked = (board?.coins ?? []).slice().sort((a, b) => value(b) - value(a) || n(b.pnl_usd) - n(a.pnl_usd));
  const scale = Math.max(...ranked.map(coin => Math.abs(value(coin))), metric === "return" ? 0.5 : 1);
  const ref = useReorderAnimation(ranked.map(coin => coin.symbol).join());
  const total = ranked.reduce((sum, coin) => sum + n(coin.pnl_usd), 0);
  const periodLabel = PERIODS.find(item => item.value === period)?.label;

  return <Card className="leaderboard" title="Coin leaderboard"
    info="Which coins have made the bot the most money, best first. Tap a coin to see its details."
    action={<Tabs label="Rank by" value={metric} onChange={setMetric} options={[{ value: "return", label: "Return %" }, { value: "profit", label: "Profit $" }]} />}>
    <Tabs label="Period" value={period} onChange={setPeriod} options={PERIODS} />
    {error && <p className="form-error">{error}</p>}
    <ScrollList visible={3}><ol className="leader-list">{ranked.map((entry, index) => {
      const coin = data.coins[entry.symbol];
      if (!coin) return null;
      const amount = value(entry);
      const width = Math.min(100, Math.abs(amount) / scale * 100);
      const winRate = entry.trades ? entry.wins / entry.trades * 100 : null;
      return <li key={entry.symbol} ref={ref(entry.symbol)} className={`leader-row ${entry.trading_enabled ? "" : "paused"}`}>
        <button className="leader-hit" onClick={() => onOpenCoin(entry.symbol)} aria-label={`Rank ${index + 1}: ${coin.name}. Open its page`}>
          <span className={`leader-rank ${MEDALS[index] ?? ""}`}>{index + 1}</span>
          <span className="leader-coin"><CoinToken symbol={entry.symbol} />
            <span><b>{entry.label}{!entry.trading_enabled && <span className="tag paused">off</span>}</b></span></span>
          <span className="leader-result">
            <b className={tone(amount)}>{metric === "return" ? pct(entry.return_pct) : signedUsd(entry.pnl_usd)}</b>
            <small>{metric === "return" ? signedUsd(entry.pnl_usd) : pct(entry.return_pct)} · {periodLabel}</small>
          </span>
          <span className="leader-bar" aria-hidden><i className={amount >= 0 ? "up" : "down"} style={{ width: `${width}%` }} /></span>
          <Sparkline points={entry.series.map(point => n(point.pnl_usd))} up={n(entry.pnl_usd) >= 0} />
          <span className="leader-meta">
            <span>{coin.lots.open_lots ? `${coin.lots.open_lots} lot${coin.lots.open_lots === 1 ? "" : "s"} open` : "No lots open yet"}</span>
            <span>{entry.trades} trade{entry.trades === 1 ? "" : "s"}{winRate != null ? ` · ${winRate.toFixed(0)}% won` : ""}</span>
            <span className="leader-status">{status(coin)}</span>
          </span>
        </button>
      </li>;
    })}</ol></ScrollList>
    {board && <p className="card-note">All coins {periodLabel}: <b className={tone(total)}>{signedUsd(total)}</b> · ranked by {metric === "return" ? "return on the shared pot" : "dollar profit"}.</p>}
  </Card>;
}
