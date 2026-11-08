import { useCallback, useEffect, useState } from "react";
import { getJson, type Dashboard, type EquityHistory, type Period, type Reachability } from "./api";
import { LeaderboardCard } from "./Leaderboard";
import { EquityChart } from "./charts";
import { useControls } from "./controls";
import { ago, n, pct, signedUsd, tone, usd } from "./format";
import { BnbCard, MoneyCard, PositionCard, RequestList, TradeList, TradingModeCard } from "./panels";
import { Card, Empty, Info, ScrollList, Stat, Tabs } from "./ui";

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
  return <Card title="Wallet over time"
    info="'Wallet value' is your whole Binance spot wallet, so money you add or take out moves it. 'Trading only' shows the bot's profit and loss on its own, starting from zero."
    action={<Tabs label="Chart view" value={view} onChange={setView}
      options={[{ value: "value", label: "Wallet value" }, { value: "performance", label: "Trading only" }]} />}>
    <Tabs label="Time range" value={period} onChange={setPeriod} options={PERIODS} />
    {error ? <p className="form-error">{error}</p>
      : <EquityChart points={history?.points ?? []} view={view} start={history?.start} end={history?.end} />}
    {history?.summary && <div className="mini-stats">
      <span>Trading P&amp;L in range <b className={tone(history.summary.strategy_pnl_change_usd)}>{signedUsd(history.summary.strategy_pnl_change_usd)}</b></span>
      <span>Highest <b>{usd(history.summary.high_value_usd)}</b></span><span>Lowest <b>{usd(history.summary.low_value_usd)}</b></span>
    </div>}
  </Card>;
}

function BinanceReach() {
  const [reach, setReach] = useState<Reachability | null>(null);
  useEffect(() => {
    const load = () => getJson<Reachability>("/api/v1/binance/reachability").then(setReach).catch(() => setReach(null));
    load();
    const timer = window.setInterval(() => document.visibilityState === "visible" && load(), 300_000);
    return () => window.clearInterval(timer);
  }, []);
  if (!reach) return <span className="warn">Binance trading API: checking…</span>;
  const ok = reach.state === "reachable";
  return <span className={ok ? "ok" : "bad"} title={reach.message}>
    Binance trading API {ok ? "reachable" : reach.state === "blocked" ? "blocked here (451)" : reach.state}
    {reach.public_ip ? ` · IP ${reach.public_ip}` : ""}</span>;
}

export function MainPage({ data, onOpenCoin }: { data: Dashboard; onOpenCoin: (symbol: string) => void }) {
  const account = data.account;
  const stats = data.stats;
  const coins = data.coin_order.map(symbol => data.coins[symbol]).filter(Boolean);
  const walletValue = account?.wallet_value_usd ?? data.binance.wallet_value_usdt ?? 0;
  const mode = data.trading.mode;
  const { session, open } = useControls();
  const locked = !!session?.controls_enabled && !session.unlocked;
  return <div className="page">
    {locked && <div className="unlock-bar">
      <p><b>This device is locked.</b> Unlock it once to buy, close or change money.</p>
      <button className="primary small" onClick={() => open({ kind: "unlock" })}>Unlock this device</button>
    </div>}
    <section className="hero">
      <span className="eyebrow">Binance wallet<Info text="Free USDT + the coins the bot holds + your BNB, priced now. This is your real Binance spot wallet." /></span>
      <strong className="hero-value">{usd(walletValue)}</strong>
      <div className="hero-sub">
        <span className={`pill ${tone(account?.strategy_pnl_usd)}`}>{signedUsd(account?.strategy_pnl_usd ?? 0)}</span>
        <span className="muted">trading profit<Info text="Profit from closed trades plus what open lots have made so far, after every Binance fee." /></span>
        <span className={`pill ${mode === "live" ? "up" : mode === "off" ? "down" : "warn"}`}>{mode === "live" ? "LIVE" : mode === "off" ? "STOPPED" : "SHADOW"}</span>
      </div>
      <div className="hero-foot">
        <span>Today <b className={tone(stats.today_pnl_usd)}>{signedUsd(stats.today_pnl_usd)}</b></span>
        <span>Free USDT <b>{usd(data.money.usdt_free)}</b></span>
        <span>Open lots <b>{data.positions.length}</b></span>
        <span>Win rate <b>{stats.win_rate_pct == null ? "—" : pct(stats.win_rate_pct, 0, false)}</b></span>
        <span>Won <b className="up">{stats.wins}</b> · Lost <b className="down">{stats.losses}</b></span>
        <span>Updated {ago(account?.timestamp)}</span>
      </div>
    </section>

    <TradingModeCard data={data} />
    <LeaderboardCard data={data} onOpenCoin={onOpenCoin} />
    <MoneyCard data={data} />

    <Card title="Open lots" info="Every lot the bot holds right now, with its stop and trailing levels. Close sells it on Binance and shows the result first.">
      {data.positions.length
        ? <div className="positions">{data.positions.map(position => <PositionCard key={position.position_id} position={position} data={data} expanded={false} showCoin />)}</div>
        : <Empty title="No open lots">Each coin waits for its price to touch its average from below.</Empty>}
    </Card>

    <BnbCard data={data} />
    <EquityCard />

    <Card title="Recent trades" info="Closed trades on every coin, newest first, after all fees.">
      <TradeList trades={data.trades} showCoin />
    </Card>

    <Card title="Your requests" info="Buy, close and pause actions you asked for, and what happened to them.">
      <RequestList requests={data.requests} />
    </Card>

    <Card className="health-card" title="System health" info="These checks confirm the bot is receiving prices for every coin and that Binance accepts its requests.">
      <div className="health">
        {coins.map(coin => <span key={coin.symbol} className={coin.health.market_age_seconds != null && coin.health.market_age_seconds < 180 ? "ok" : "bad"}>
          {coin.label} prices {coin.health.market_age_seconds == null ? "waiting" : `${Math.round(coin.health.market_age_seconds)}s old`}</span>)}
        {coins.map(coin => <span key={`${coin.symbol}-signals`} className={coin.health.signal_engine === "ready" ? "ok" : "warn"}>
          {coin.label} signals {coin.health.signal_engine === "ready" ? "ready" : "warming up"}</span>)}
        <span className={data.binance.connected ? "ok" : "bad"}>Binance {data.binance.connected ? "connected" : "not connected"}</span>
        <span className={mode === "live" ? "ok" : "warn"}>Mode {mode}</span>
        <BinanceReach />
      </div>
      <ScrollList visible={5}><div className="strategy-notes">
        {coins.map(coin => <p key={coin.symbol} className="card-note"><b>{coin.label}</b> · <code>{coin.strategy.strategy_id}</code> · {coin.strategy.backtest}</p>)}
      </div></ScrollList>
    </Card>
  </div>;
}
