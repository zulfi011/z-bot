import { useCallback, useEffect, useState } from "react";
import { getJson, type Dashboard, type EquityHistory, type Period, type Reachability } from "./api";
import { LeaderboardCard } from "./Leaderboard";
import { EquityChart } from "./charts";
import { useControls } from "./controls";
import { ago, pct, signedUsd, tone, usd } from "./format";
import { BnbCard, LotCard, MoneyCard, RequestList, TradeList, TradingModeCard } from "./panels";
import { Card, Empty, Info, Tabs } from "./ui";

const PERIODS: { value: Period; label: string }[] = [
  { value: "1d", label: "1D" }, { value: "7d", label: "7D" }, { value: "1m", label: "1M" },
  { value: "3m", label: "3M" }, { value: "1y", label: "1Y" }, { value: "all", label: "All" },
];

function EquityCard() {
  const [period, setPeriod] = useState<Period>(() => (localStorage.getItem("sol-desk-period") as Period) || "7d");
  const [view, setView] = useState<"value" | "performance">("value");
  const [history, setHistory] = useState<EquityHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => getJson<EquityHistory>(`/api/v1/equity-history?period=${period}`)
    .then(result => { setHistory(result); setError(null); })
    .catch(reason => setError(reason instanceof Error ? reason.message : "Unavailable")), [period]);
  useEffect(() => { load(); const timer = window.setInterval(() => document.visibilityState === "visible" && load(), 60_000); return () => window.clearInterval(timer); }, [load]);
  useEffect(() => { try { localStorage.setItem("sol-desk-period", period); } catch { /* ignore */ } }, [period]);
  return <Card className="equity-card" title="Wallet over time"
    action={<Tabs label="Chart view" value={view} onChange={setView}
      options={[{ value: "value", label: "Wallet value" }, { value: "performance", label: "Trading only" }]} />}>
    <Tabs label="Time range" value={period} onChange={setPeriod} options={PERIODS} />
    {error ? <p className="form-error">{error}</p>
      : <EquityChart points={history?.points ?? []} view={view} start={history?.start} end={history?.end} />}
    {history?.summary && history.points.length >= 2 && <div className="mini-stats">
      <span>Trading P&amp;L in range <b className={tone(history.summary.strategy_pnl_change_usd)}>{signedUsd(history.summary.strategy_pnl_change_usd)}</b></span>
      <span>Highest <b>{usd(history.summary.high_value_usd)}</b></span><span>Lowest <b>{usd(history.summary.low_value_usd)}</b></span>
    </div>}
  </Card>;
}

type Health = "ok" | "warn" | "bad" | "off";

function HealthRow({ state, label, value }: { state: Health; label: string; value: string }) {
  return <li className={`health-row ${state}`}><i aria-hidden="true" /><span>{label}</span><b>{value}</b></li>;
}

/** Five plain status lines: is the bot getting prices, are its signals ready, can it reach Binance. */
function HealthCard({ data, attached }: { data: Dashboard; attached: boolean }) {
  const [reach, setReach] = useState<Reachability | null>(null);
  useEffect(() => {
    const load = () => getJson<Reachability>("/api/v1/binance/reachability").then(setReach).catch(() => setReach(null));
    load();
    const timer = window.setInterval(() => document.visibilityState === "visible" && load(), 300_000);
    return () => window.clearInterval(timer);
  }, []);
  const coins = data.coin_order.map(symbol => data.coins[symbol]).filter(Boolean);
  const stale = coins.filter(coin => coin.health.market_age_seconds == null || coin.health.market_age_seconds >= 180);
  const warming = coins.filter(coin => coin.health.signal_engine !== "ready");
  const names = (list: typeof coins) => list.map(coin => coin.label).join(", ");
  const mode = data.trading.mode;
  const reachable = reach?.state === "reachable";
  return <Card className="health-card" title="System health">
    <ul className="health-list">
      <HealthRow state={stale.length ? "warn" : "ok"} label="Prices"
        value={stale.length ? `Waiting for ${names(stale)}` : `Live for all ${coins.length} coins`} />
      <HealthRow state={warming.length ? "warn" : "ok"} label="Signals"
        value={warming.length ? `Warming up: ${names(warming)}` : "Ready"} />
      <HealthRow state={!attached ? "off" : data.binance.connected ? "ok" : "bad"} label="Binance account"
        value={!attached ? "Not attached" : data.binance.connected ? "Connected" : "Can't connect"} />
      <HealthRow state={!reach ? "off" : reachable ? "ok" : "bad"} label="Binance trading API"
        value={!reach ? "Checking…" : reachable ? "Reachable from here" : reach.state === "blocked" ? "Blocked in this region" : "Not reachable"} />
      <HealthRow state={mode === "live" ? "ok" : mode === "off" ? "bad" : "warn"} label="Trading"
        value={mode === "live" ? "Live" : mode === "off" ? "Stopped" : "Shadow (nothing sent)"} />
    </ul>
  </Card>;
}

export function MainPage({ data, onOpenCoin }: { data: Dashboard; onOpenCoin: (symbol: string) => void }) {
  const account = data.account;
  const stats = data.stats;
  const walletValue = account?.wallet_value_usd ?? data.binance.wallet_value_usdt ?? 0;
  const mode = data.trading.mode;
  // Outside live mode the bot trades pretend money: a starting amount the user sets, never a Binance balance.
  const shadow = mode !== "live";
  const pretend = data.shadow;
  const profit = shadow ? pretend?.pnl ?? 0 : account?.strategy_pnl_usd ?? 0;
  const { session, open, binance } = useControls();
  const attached = !!binance?.attached;
  const locked = !!session?.controls_enabled && !session.unlocked;
  return <div className="page">
    {locked && <div className="unlock-bar">
      <p><b>This device is locked.</b> Unlock it once to buy, close or change money.</p>
      <button className="primary small" onClick={() => open({ kind: "unlock" })}>Unlock this device</button>
    </div>}
    <section className="hero">
      {shadow
        ? <span className="eyebrow">Shadow wallet<Info text="Pretend money for shadow mode: the starting amount you set, plus what the shadow trades made. Nothing is spent on Binance." /></span>
        : <span className="eyebrow">Binance wallet<Info text="Free USDT + the coins the bot holds + your BNB, priced now. This is your real Binance spot wallet." /></span>}
      {shadow && !pretend
        ? <div className="hero-empty">
          <p>Shadow mode trades pretend money. Choose how much it starts with to see its results in dollars.</p>
          <button className="primary" onClick={() => open({ kind: "amount", field: "shadow_start_usd" })}>Set starting amount</button>
        </div>
        : <strong className="hero-value">{usd(shadow ? pretend?.wallet : walletValue)}</strong>}
      {shadow && pretend && <p className="hero-start">Started with <b>{usd(pretend.start)}</b>
        <button className="link" onClick={() => open({ kind: "amount", field: "shadow_start_usd" })}>Change</button></p>}
      <div className="hero-sub">
        <span className={`pill ${tone(profit)}`}>{signedUsd(profit)}</span>
        <span className="muted">trading profit<Info text="Profit from closed trades plus what open lots have made so far, after every Binance fee." /></span>
        <span className={`pill ${mode === "live" ? "up" : mode === "off" ? "down" : "warn"}`}>{mode === "live" ? "LIVE" : mode === "off" ? "STOPPED" : "SHADOW"}</span>
      </div>
      <div className="hero-foot">
        <span>Today <b className={tone(stats.today_pnl_usd)}>{signedUsd(stats.today_pnl_usd)}</b></span>
        {!(shadow && !pretend) && <span>Free USDT <b>{usd(data.money.usdt_free)}</b></span>}
        <span>Open lots <b>{data.positions.length}</b></span>
        <span>Win rate <b>{stats.win_rate_pct == null ? "—" : pct(stats.win_rate_pct, 0, false)}</b></span>
        <span>Won <b className="up">{stats.wins}</b> · Lost <b className="down">{stats.losses}</b></span>
        {!shadow && <span>Updated {ago(account?.timestamp)}</span>}
      </div>
    </section>

    <TradingModeCard data={data} />
    <MoneyCard data={data} />
    <LeaderboardCard data={data} onOpenCoin={onOpenCoin} />

    <Card className="open-lots" title={<>Open lots{data.positions.length ? <span className="count">{data.positions.length}</span> : null}</>}
      info="Every lot the bot holds right now. Close sells it and shows the result first. Open a coin's page for the full detail.">
      {data.positions.length
        ? <div className="lot-strip">{data.positions.map(position => <LotCard key={position.position_id} position={position} data={data} />)}</div>
        : <Empty title="No open lots">Each coin waits for its price to touch its average from below.</Empty>}
    </Card>

    {attached && <BnbCard data={data} />}
    <EquityCard />

    <Card className="trades-card" title="Recent trades">
      <TradeList trades={data.trades} showCoin />
    </Card>

    <Card className="requests-card" title="Your requests">
      <RequestList requests={data.requests} />
    </Card>

    <HealthCard data={data} attached={attached} />
  </div>;
}
