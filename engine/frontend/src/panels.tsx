import { useEffect, useState } from "react";
import { coinLabel, type CoinMoney, type CoinView, type ControlRequest, type Dashboard, type LotSlot, type Num, type Position, type Trade } from "./api";
import { EXPLAIN, suggestedPot, useControls } from "./controls";
import { ago, amount, bnbAmount, duration, label, n, pct, price, signedUsd, time, tone, usd } from "./format";
import { sourceOf } from "./sources";
import { Card, CoinToken, Empty, Info, ScrollList, Stat, Tip, Toggle } from "./ui";

export function BnbCard({ data, compact = false }: { data: Dashboard; compact?: boolean }) {
  const bnb = data.bnb;
  const low = (bnb.round_trips_left ?? 0) < 4;
  return <Card className="bnb-card" title={<><CoinToken symbol="BNB" />BNB for fees</>}
    info="Binance charges 0.075% per buy or sell when you pay fees in BNB, instead of 0.10% in USDT. The BNB sits in your own Binance wallet; buy more there when it runs low.">
    <div className="stat-grid">
      <Stat label="BNB held" value={bnbAmount(bnb.balance)} sub={`${usd(bnb.value_usd)} at ${usd(bnb.price)}`}
        info="Your real BNB balance on Binance and what it is worth now." />
      <Stat label="Covers" value={bnb.round_trips_left == null ? "—" : `${bnb.round_trips_left} trades`} valueClass={low ? "warn" : ""}
        sub={`${usd(bnb.round_trip_fee_usd, 3)} per ${usd(bnb.lot_size_usd, 0)} lot buy+sell`}
        info="How many buy+sell pairs your BNB can pay for at your largest lot size. All coins share it." />
      {!compact && <>
        <Stat label="Fees paid in BNB" value={usd(bnb.bnb_fees_usd, 3)} sub={`${bnb.bnb_fills} fills`}
          info="What Binance has taken in BNB for this bot's trades, valued when it was charged." />
        <Stat label="Saved so far" value={usd(bnb.saved_usd, 3)} valueClass="up" sub="vs paying 0.10% in USDT"
          info="How much less you paid by using BNB instead of USDT on the same fills." />
      </>}
    </div>
    {!bnb.enabled && <p className="card-note warn">BNB fee discount is <b>off</b> in your Binance settings, so fees are 0.10%. Switch on "Use BNB to pay for fees" in Binance.</p>}
    {bnb.enabled && n(bnb.balance) <= 0 && <p className="card-note warn">No BNB in your wallet, so fees are charged in USDT at 0.10%. Buy a little BNB on Binance.</p>}
    {low && n(bnb.balance) > 0 && <p className="card-note warn">BNB is running low — top it up on Binance to keep the discount.</p>}
  </Card>;
}

/** The extra ways in a coin has switched on, for the one-line summary on the Main page. */
const entriesOn = (coin: CoinMoney) => Object.entries(coin.entries ?? {})
  .filter(([, entry]) => entry.supported && entry.enabled)
  .map(([name]) => name === "pullback" ? "pullback" : "adds").join(" · ");

export function MoneyCard({ data }: { data: Dashboard }) {
  const { open } = useControls();
  const money = data.money;
  const pot = money.pot;
  const view = (symbol: string) => data.coins[symbol];
  const lotLabel = usd(pot.lot_size_usd, n(pot.lot_size_usd) % 1 ? 2 : 0);
  const short = pot.next_lot_usd != null && n(pot.next_lot_usd) < n(pot.lot_size_usd);
  const suggestion = suggestedPot(n(money.budget_usd));
  const differs = suggestion.lots !== pot.lots || suggestion.lot !== n(pot.lot_size_usd);
  return <Card className="money-card" title="Shared pot"
    info="Every coin you switch on shares one set of lots. Whichever coin signals first takes the next free lot, so money never sits idle waiting for one coin. Everything stays in your Binance spot wallet."
    action={<Tip text={EXPLAIN.pot}><button className="primary small" onClick={() => open({ kind: "pot" })}>Edit pot</button></Tip>}>
    <div className="stat-grid four">
      <Stat label="Pot" value={`${pot.lots} × ${lotLabel}`} sub={`= ${usd(pot.total_usd)} · ${pot.coins_on} of ${money.coins.length} coins on`}
        info="Number of lots × money per lot. Change it with Edit pot." />
      <Stat label="Lots in use" value={`${pot.open_lots} / ${pot.lots}`} valueClass={pot.free_lots === 0 ? "warn" : undefined}
        sub={pot.free_lots ? `${pot.free_lots} free` : "all lots open"}
        info="Open lots across every coin. When all are open, new signals are skipped until one closes." />
      <Stat label="Next buy" value={pot.next_lot_usd == null ? "—" : usd(pot.next_lot_usd, short ? 2 : 0)} valueClass={short ? "warn" : undefined}
        sub={pot.next_lot_usd == null ? (pot.free_lots ? "no free USDT" : "waiting for a free lot") : short ? `of ${lotLabel} · pot is short` : "any coin's next signal"}
        info="What the next signal from any coin that is on would spend. After losses the last lot uses whatever USDT is left." />
      <Stat label="Your money" value={usd(money.budget_usd)} sub={data.shadow ? "shadow wallet" : data.binance.connected ? `${usd(money.usdt_free)} free + ${usd(money.in_trades_usd)} in lots` : "no Binance account attached"}
        info="Free USDT on Binance plus what the open lots cost." />
    </div>
    {differs && n(money.budget_usd) > 0 && <p className="card-note">Growth plan for {usd(money.budget_usd, 0)}: <b>{suggestion.lots} × {usd(suggestion.lot, 0)}</b>.
      {" "}<button className="link" onClick={() => open({ kind: "pot" })}>Change</button><Info text={EXPLAIN.growth} /></p>}
    <ScrollList visible={5}><div className="coin-rows">{money.coins.map(coin => <div key={coin.symbol} className={`coin-row ${coin.trading_enabled ? "" : "off"}`}>
      <div className="coin-id"><CoinToken symbol={coin.symbol} /><div><b>{coin.name}</b>
        <small>{coin.trading_enabled ? `on · shares the pot${entriesOn(coin) ? ` · ${entriesOn(coin)}` : ""}` : "off · no new trades"}</small></div></div>
      <div className="coin-now"><b className={tone(n(coin.realized_pnl_usd) + n(coin.unrealized_pnl_usd))}>{signedUsd(n(coin.realized_pnl_usd) + n(coin.unrealized_pnl_usd))}</b>
        <small>{coin.open_lots} lot{coin.open_lots === 1 ? "" : "s"} open{coin.open_lots ? ` · ${usd(coin.value_usd)}` : ""}</small></div>
      <div className="coin-actions">
        {view(coin.symbol) && <Tip text={coin.trading_enabled ? EXPLAIN.pause : EXPLAIN.resume}>
          <Toggle checked={coin.trading_enabled} label={`${coin.name} trading ${coin.trading_enabled ? "on" : "off"}`}
            onChange={enable => open({ kind: "trading", coin: view(coin.symbol)!, enable })} /></Tip>}
      </div>
    </div>)}</div></ScrollList>
    <p className="card-note">{EXPLAIN.money}</p>
  </Card>;
}

export function TradingModeCard({ data }: { data: Dashboard }) {
  const { open } = useControls();
  const mode = data.trading.mode;
  const labels = { live: "Live — real orders", shadow: "Shadow — nothing sent", off: "Stopped" };
  return <Card className="mode-card" title="Trading switch"
    info="Live sends real orders to Binance. Shadow works out every order and records it without sending, so you can watch the strategy safely. Stopped buys nothing; open lots keep their stop orders on Binance and can still be sold.">
    <div className="stat-grid three">
      <Stat label="Mode now" value={labels[mode]} valueClass={mode === "live" ? "up" : mode === "off" ? "down" : "warn"}
        sub={data.binance.connected ? "Binance connected" : "No Binance account attached"} />
      <Stat label="Daily loss limit" value={n(data.trading.daily_loss_limit_usd) ? usd(data.trading.daily_loss_limit_usd) : "off"}
        sub={<>new lots pause for the day · <button className="link inline" onClick={() => open({ kind: "amount", field: "daily_loss_limit_usd" })}>Edit</button></>}
        info="When today's closed trades add up to this loss, no new lot opens until tomorrow (UTC)." />
      <Stat label="Most in trades" value={n(data.trading.maximum_open_value_usd) ? usd(data.trading.maximum_open_value_usd) : "no limit"}
        sub={<>across all coins · <button className="link inline" onClick={() => open({ kind: "amount", field: "maximum_open_value_usd" })}>Edit</button></>}
        info="A ceiling on the money the bot may have in open lots at once." />
    </div>
    <div className="button-row">
      {mode !== "live" && <Tip text={EXPLAIN.modeLive}><button className="primary" onClick={() => open({ kind: "trading-mode", mode: "live" })}>Go live</button></Tip>}
      {mode !== "shadow" && <Tip text={EXPLAIN.modeShadow}><button className="secondary" onClick={() => open({ kind: "trading-mode", mode: "shadow" })}>Shadow mode</button></Tip>}
      {mode !== "off" && <Tip text={EXPLAIN.modeOff}><button className="danger" onClick={() => open({ kind: "trading-mode", mode: "off" })}>Stop all trading</button></Tip>}
    </div>
  </Card>;
}

const SOURCE_NOTE: Record<string, string> = {
  signal: "the dip into the average", breakout: "a Mode C break out of a quiet band",
  pullback: "the pullback entry", pyramid: "an add to a lot that was already winning", manual: "you",
};

/** One lot of the coin: what is in it, how it is being held, and where it stands. */
function Slot({ slot, lotLabel, next, lotSize, nextNote }:
  { slot: LotSlot; lotLabel: string; next: Num | null; lotSize: number; nextNote: string }) {
  if (slot.state === "free") {
    const short = next != null && n(next) < lotSize;
    return next == null
      ? <div className="slot empty"><span>Lot {slot.number}</span><b>—</b><small>free slot</small></div>
      : <div className={`slot next ${short ? "short" : ""}`}><span>Lot {slot.number}</span>
        <b>{usd(next, short ? 2 : 0)}</b><small>{short ? `of ${lotLabel}` : nextNote}</small></div>;
  }
  const source = sourceOf(slot.source ?? "signal");
  const rides = slot.mode === "trend";
  return <div className={`slot filled ${slot.source} ${slot.mine === false ? "other" : ""}`}
    title={`Lot ${slot.number}: ${slot.label ?? ""} bought by ${SOURCE_NOTE[slot.source ?? "signal"]}`}>
    <span>{slot.label ?? `Lot ${slot.number}`} <i className={`src-swatch ${source.cls}`}>{source.letter}</i></span>
    <b>{usd(slot.allocation_usd, 0)}</b>
    <small className={tone(slot.unrealized_usd)}>{signedUsd(slot.unrealized_usd)}</small>
    <em className={`slot-mode ${rides ? "rides" : "trails"}`}>
      {slot.trend_exit_pending ? "selling" : !slot.armed ? "waiting" : rides ? "rides the line" : "trailing"}</em>
  </div>;
}

export function LotsCard({ data, coin }: { data: Dashboard; coin: CoinView }) {
  const { open } = useControls();
  const lots = coin.lots;
  const name = coin.label;
  const lotSize = n(lots.lot_size_usd);
  const lotLabel = usd(lots.lot_size_usd, lotSize % 1 ? 2 : 0);
  const slots = lots.slots ?? [];
  const nextIndex = slots.findIndex(slot => slot.state === "free");
  return <Card className="lots-card" title={<>Shared pot · {lots.max_lots} × {lotLabel}</>}
    info={`The lots every coin that is on shares, first come first served. Each buy spends ${lotLabel} of your Binance USDT. Lots ${name} holds are highlighted; the faded ones belong to other coins.`}>
    <div className="slots">{slots.map((slot, index) =>
      <Slot key={slot.number} slot={slot} lotLabel={lotLabel} lotSize={lotSize} nextNote="next signal"
        next={index === nextIndex ? lots.next_lot_usd : null} />)}</div>
    <div className="slot-legend">
      {(["signal", "breakout", "pullback", "pyramid"] as const).map(key => {
        const source = sourceOf(key);
        const held = slots.filter(slot => slot.source === key).length;
        // A way in this coin's strategy does not have is left out entirely - unless a lot from it is still
        // open, in which case the swatch has to stay so the lot above can be read.
        if (!held && coin.entries?.[key]?.supported === false) return null;
        return <span key={key} className={held ? "on" : undefined}>
          <i className={`src-swatch ${source.cls}`}>{source.letter}</i>{source.name}{held ? ` · ${held}` : ""}</span>;
      })}
      <span className="spacer" />
      <span><em className="slot-mode rides">rides the line</em> Mode A</span>
      <span><em className="slot-mode trails">trailing</em> Mode B</span>
    </div>
    {!coin.trading_enabled && <p className="card-note warn"><b>{name} is switched off.</b> Its signals are skipped, so the pot's lots go to the other coins. Open {name} lots keep their stop orders on Binance.</p>}
    <p className="card-note">
      {lots.next_lot_usd != null
        ? n(lots.next_lot_usd) < lotSize
          ? <>The next {name} signal buys <b>{usd(lots.next_lot_usd)}</b> — all the pot has left of its {lotLabel} lot.</>
          : <>The next {name} signal buys <b>{lotLabel}</b>. Binance has {usd(lots.free_usdt)} free USDT.</>
        : !lots.slot_free ? <>All {lots.max_lots} shared lots are open ({lots.open_lots} of them {name}) — new signals are skipped until one closes.</>
          : !coin.trading_enabled ? <>{name} is off, so its signals do not buy.</>
            : <>No USDT is free on Binance, so signals are skipped until a trade closes.</>}
      {data.trading.mode !== "live" && <> Trading is in <b>{data.trading.mode}</b> mode.</>}
    </p>
    <div className="button-row">
      <Tip text={EXPLAIN.buyNow}><button className="secondary" disabled={lots.next_lot_usd == null || !coin.trading_enabled} onClick={() => open({ kind: "buy-now", coin })}>Buy now</button></Tip>
      <Tip text={EXPLAIN.pot}><button className="ghost" onClick={() => open({ kind: "pot" })}>Edit pot</button></Tip>
      <Tip text={coin.trading_enabled ? EXPLAIN.pause : EXPLAIN.resume}><button className="ghost"
        onClick={() => open({ kind: "trading", coin, enable: !coin.trading_enabled })}>{coin.trading_enabled ? `Switch ${name} off` : `Switch ${name} on`}</button></Tip>
    </div>
  </Card>;
}

export function PositionCard({ position, data, expanded = true, showCoin = false }:
  { position: Position; data: Dashboard; expanded?: boolean; showCoin?: boolean }) {
  const { open } = useControls();
  const closing = data.requests.some(request => request.kind === "close_position" && request.position_id === position.position_id && request.status === "pending");
  const coin = position.coin;
  const keep = 100 - n(position.trail_giveback_pct);
  return <article className="position">
    <header>
      <div>{showCoin && <span className="coin-badge"><CoinToken symbol={position.symbol} />{coin}</span>}
        <span className="lot-badge">Lot {position.lot_number}</span>
        <span className={`tag source ${sourceOf(position.entry_source).cls}`} title={`Bought by ${sourceOf(position.entry_source).long}`}>
          {position.entry_source === "manual" ? "bought by you" : sourceOf(position.entry_source).name}</span>
        <small>{usd(position.allocation_usd)} · opened {time(position.entry_time, true)} · {duration(position.bars_held)}</small></div>
      <div className="position-pnl"><b className={tone(position.unrealized_pnl_usd)}>{signedUsd(position.unrealized_pnl_usd)}</b>
        <small className={tone(position.unrealized_pct)}>{pct(position.unrealized_pct)}</small></div>
    </header>
    <div className="price-path">
      <span className="down">{position.trailing_active && position.exit_mode === "trend"
        ? <>Floor {price(position.stop_price)}</> : <>Stop {price(position.stop_price)}</>}</span>
      <span>Bought {price(position.entry_fill_price)}</span>
      <span>Now {price(position.current_price)}</span>
      <span className="up">{!position.trailing_active ? `Trail starts ${price(position.activation_price)}`
        : position.exit_mode === "trend" ? "Riding the trend" : `Trail ${price(position.trail_price)}`}</span>
    </div>
    {position.trailing_active && position.exit_mode === "trend"
      ? <p className={`position-state ${position.trend_exit_pending ? "warn" : "up"}`}>
        <span className="mode-chip mode-a">Mode A</span>
        {position.trend_exit_pending
          ? ` Selling next minute — ${coin} closed below the ${n(position.trend_ema_minutes) / 60}-hour trend line.`
          : ` Riding the trend — peak ${price(position.peak_price)}. It keeps running while ${coin} closes above the ${n(position.trend_ema_minutes) / 60}-hour trend line, and its stop has moved up to ${price(position.stop_price)} — break even after fees, so this lot can no longer finish negative.`}
        <Info text={`This lot was bought while the market was in a clean uptrend (7-day above 15-day above 30-day average), so it ignores the ${n(position.trail_giveback_pct)}% give-back rule. It sells at the next minute's open after the first minute that closes below the ${n(position.trend_ema_minutes) / 60}-hour average line, which lets a big move run instead of capping it at about +1%.`} /></p>
      : position.trailing_active
      ? <p className="position-state up"><span className="mode-chip mode-b">Mode B</span> Trailing active — peak {price(position.peak_price)}. It sells if {coin} falls to {price(position.trail_price)} (keeps {keep}% of the peak profit).<Info text={`After ${coin} rises ${n(position.trail_activation_pct)}% above your buy price, a trailing stop follows the highest price. It sells if the price gives back ${n(position.trail_giveback_pct)}% of the best profit reached, locking in the rest.`} /></p>
      : <div className="progress-wrap">
        <div className="progress-label"><span>Progress to trailing start</span><b>{pct(position.activation_progress_pct, 0, false)}</b>
          <Info text={`How far ${coin} has moved from your buy price toward +${n(position.trail_activation_pct)}%, where the trailing stop switches on. Until then only the −${n(position.stop_pct)}% stop can close the lot.`} /></div>
        <div className="progress"><i style={{ width: `${Math.min(100, n(position.activation_progress_pct))}%` }} /></div>
        <small>{pct(position.distance_to_stop_pct, 2, false)} above the stop · {pct(position.distance_to_activation_pct, 2, false)} to trailing start</small>
      </div>}
    <div className="position-foot">
      <small>{expanded ? <>{amount(position.quantity)} {coin} · fee {usd(position.entry_fee_usd, 3)} in {position.entry_fee_asset}</>
        : position.close_estimate ? <>Close now ≈ <b className={tone(position.close_estimate.net_pnl_usd)}>{signedUsd(position.close_estimate.net_pnl_usd)}</b> after costs</> : null}</small>
      {closing ? <span className="tag pending">Closing this minute</span>
        : <Tip text={EXPLAIN.close}><button className="danger small" onClick={() => open({ kind: "close", position })}>Close</button></Tip>}
    </div>
  </article>;
}

export function TradeList({ trades, limit, showCoin = false }: { trades: Trade[]; limit?: number; showCoin?: boolean }) {
  if (!trades.length) return <Empty title="No completed trades yet">Trades appear here when the stop or trailing stop sells a lot.</Empty>;
  return <ScrollList visible={5}><ul className="rows trade-rows">{trades.slice(0, limit).map(trade => {
    const source = sourceOf(trade.entry_source);
    const rides = trade.exit_mode === "trend";
    return <li key={trade.trade_id}>
      <div className="trade-story">
        <b>{showCoin && <span className="coin-inline">{coinLabel(trade.symbol)}</span>}
          <i className={`src-swatch ${source.cls}`}>{source.letter}</i>{" "}
          {trade.entry_source === "manual" ? "You bought" : `${source.name} bought`} at {price(trade.entry_fill_price)}
          {" "}<span className="arrow">→</span> {label(trade.exit_reason)} at {price(trade.exit_fill_price)}</b>
        <small>
          {trade.exit_mode && <em className={`slot-mode ${rides ? "rides" : "trails"}`}>{rides ? "Mode A" : "Mode B"}</em>}
          {time(trade.exit_time, true)} · held {duration(trade.duration_minutes)} · fees {usd(n(trade.entry_fee_usd) + n(trade.exit_fee_usd), 2)}
        </small>
      </div>
      <div className="right"><b className={tone(trade.net_pnl_usd)}>{signedUsd(trade.net_pnl_usd)}</b>
        <small className={tone(trade.net_return_pct)}>{pct(trade.net_return_pct)} on {usd(trade.allocation_usd, 0)}</small></div>
    </li>;
  })}</ul></ScrollList>;
}

export function RequestList({ requests }: { requests: ControlRequest[] }) {
  const { open } = useControls();
  const visible = requests.filter(request => request.kind !== "initial_deposit" || requests.length < 3);
  if (!visible.length) return <Empty title="No requests yet">Deposits, withdrawals, BNB purchases and your buy/close requests are listed here.</Empty>;
  return <ScrollList visible={5}><ul className="rows">{visible.map(request => <li key={request.request_id}>
    <div><b>{request.symbol && <span className="coin-inline">{coinLabel(request.symbol)}</span>}{label(request.kind)}{request.amount_usd != null ? ` · ${usd(request.amount_usd)}` : ""}</b>
      <small>{ago(request.requested_at)}{request.reason ? ` · ${request.reason}` : ""}</small></div>
    <div className="right">
      <span className={`tag ${request.status}`}>{request.status === "applied" ? "done" : request.status === "pending" ? "waiting" : request.reason === "Cancelled by you" ? "cancelled" : "rejected"}</span>
      {request.status === "pending" && request.kind !== "initial_deposit" &&
        <button className="link" onClick={() => open({ kind: "cancel", requestId: request.request_id, what: label(request.kind) })}>cancel</button>}
    </div>
  </li>)}</ul></ScrollList>;
}

const DISMISSED = "sol-desk-dismissed-alerts";

function readDismissed(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(DISMISSED) ?? "{}"); } catch { return {}; }
}

export function AlertBanner({ data }: { data: Dashboard }) {
  const [dismissed, setDismissed] = useState<Record<string, string>>(readDismissed);
  const active = data.alerts.filter(alert => alert.status === "active");
  // An alert stays hidden until it resolves; if it comes back later it shows again.
  useEffect(() => {
    const live = new Set(active.map(alert => alert.alert_key));
    const kept = Object.fromEntries(Object.entries(dismissed).filter(([key]) => live.has(key)));
    if (Object.keys(kept).length !== Object.keys(dismissed).length) {
      setDismissed(kept);
      try { localStorage.setItem(DISMISSED, JSON.stringify(kept)); } catch { /* ignore */ }
    }
  }, [active, dismissed]);
  const visible = active.filter(alert => !dismissed[alert.alert_key]);
  if (!visible.length) return null;
  const dismiss = (key: string) => {
    const next = { ...dismissed, [key]: new Date().toISOString() };
    setDismissed(next);
    try { localStorage.setItem(DISMISSED, JSON.stringify(next)); } catch { /* ignore */ }
  };
  return <div className="banners" role="status">{visible.slice(0, 3).map(alert =>
    <div key={alert.alert_key} className={`banner ${alert.severity === "critical" ? "critical" : "warning"}`}>
      {/* The time matters: a check that ran a minute ago must not read as a claim about right now. */}
      <p><b>{alert.title}.</b> {alert.message} <span className="muted">Last seen {ago(alert.last_seen_at)}.</span></p>
      <button className="banner-close" aria-label={`Hide: ${alert.title}`} title="Hide this message (it comes back if the problem returns)"
        onClick={() => dismiss(alert.alert_key)}>✕</button>
    </div>)}</div>;
}
