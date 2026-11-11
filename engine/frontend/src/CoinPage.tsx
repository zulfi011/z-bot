import { useState } from "react";
import type { CoinView, Dashboard, Interval, PullbackView } from "./api";
import { PriceChart } from "./charts";
import { ago, amount, duration, label, n, pct, price, signedUsd, time, tone, usd } from "./format";
import { useControls } from "./controls";
import { BnbCard, LotsCard, PositionCard, TradeList } from "./panels";
import { EXIT, SOURCE, sourceOf } from "./sources";
import { Card, CoinToken, Empty, Info, ScrollList, Stat, Tabs, Tip } from "./ui";

const INTERVALS: { value: Interval; label: string }[] = [
  { value: "3m", label: "3m" }, { value: "15m", label: "15m" }, { value: "1h", label: "1h" },
  { value: "4h", label: "4h" }, { value: "1d", label: "1D" },
];

type StepState = "done" | "block" | "todo" | "now";
type Step = { state: StepState; label: string; detail?: string; progress?: number };
type WayStatus = { text: string; tone: "good" | "warn" | "bad" | "muted" };

const STEP_ICON: Record<StepState, string> = { done: "✓", block: "✕", todo: "○", now: "●" };
const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

/** One way in as a short list of steps that end in a buy: ✓ done, ✕ blocking, ○ not reached yet, ● happening now. */
function WayCard({ source, title, status, steps, info }:
  { source: keyof typeof SOURCE; title: string; status: WayStatus; steps: Step[]; info: string }) {
  const badge = SOURCE[source];
  return <section className={`way-card ${status.tone}`} aria-label={`${title}: ${status.text}`}>
    <header>
      <span className={`src-swatch ${badge.cls}`} title={badge.tip}>{badge.letter}</span>
      <b>{title}<Info text={info} /></b>
      <span className={`way-status ${status.tone}`}>{status.text}</span>
    </header>
    <ol className="way-steps">
      {steps.map(step => <li key={step.label} className={`way-step ${step.state}`}>
        <i aria-hidden="true">{STEP_ICON[step.state]}</i>
        <div><span>{step.label}</span>{step.detail && <small>{step.detail}</small>}
          {step.progress != null && <div className="way-progress"><i style={{ width: `${clamp01(step.progress) * 100}%` }} /></div>}</div>
      </li>)}
      <li className="way-step buy"><i aria-hidden="true">→</i><div><span>Buy</span></div></li>
    </ol>
  </section>;
}

/** Card status from its steps: anything blocking wins, then anything happening now. */
const statusOf = (steps: Step[], off = false): WayStatus => off ? { text: "Off", tone: "muted" }
  : steps.some(step => step.state === "block") ? { text: "Blocked", tone: "bad" }
    : steps.some(step => step.state === "now") ? { text: "Buying soon", tone: "good" }
      : { text: "Waiting", tone: "warn" };

const hh = (hour: number) => `${String(hour).padStart(2, "0")}:00`;
// "3 hours" reads better than "3h 0m" in a rule; anything uneven falls back to the usual duration.
const span = (minutes: number) => minutes % 60 === 0 ? `${minutes / 60} hour${minutes === 60 ? "" : "s"}` : duration(minutes);

function dipSteps(coin: CoinView): Step[] {
  const setup = coin.setup, strategy = coin.strategy;
  const candle = `${strategy.signal_timeframe.replace("m", "")}-min`;
  const steps: Step[] = [{
    state: setup.regime === "missing" ? "todo" : setup.trend_allows_entries ? "done" : "block",
    label: "Trend allows buying",
    detail: setup.regime === "missing" ? "needs 30 days of prices" : setup.trend_allows_entries ? `trend is ${setup.regime}` : "strong downtrend",
  }];
  if (strategy.requires_close_above_30d) {
    const above = setup.average_30d != null && coin.market.price != null;
    const stretch = above ? (n(coin.market.price) / n(setup.average_30d) - 1) * 100 : 0;
    const limit = strategy.maximum_above_30d_pct == null ? null : n(strategy.maximum_above_30d_pct);
    steps.push({
      state: !above ? "todo" : stretch > 0 && (limit == null || stretch <= limit) ? "done" : "block",
      label: limit == null ? "Above its 30-day average" : `Above its 30-day average, by ${limit}% at most`,
      detail: !above ? "needs 30 days of prices" : `${stretch >= 0 ? "+" : ""}${stretch.toFixed(1)}% vs ${price(setup.average_30d)}`,
    });
  }
  const distance = n(setup.distance_to_zone_pct);
  steps.push(setup.pending_episode_since ? { state: "done", label: "Price rises into the zone", detail: `touched at ${time(setup.pending_episode_since)}` }
    : setup.zone_state === "below" ? { state: "todo", label: "Price rises into the zone",
      detail: `${pct(distance, 2, false)} below ${price(setup.zone_lower)}–${price(setup.zone_upper)}`, progress: 1 - distance / 10 }
      : setup.zone_state === "above" ? { state: "todo", label: "Price rises into the zone",
        detail: `${pct(distance, 2, false)} above — must drop below ${price(setup.zone_lower)} first` }
        : setup.zone_state === "inside" ? { state: "todo", label: "Price rises into the zone", detail: "inside now, but came from above" }
          : { state: "todo", label: "Price rises into the zone", detail: "average still warming up" });
  const deadline = setup.pending_episode_since
    ? time(new Date(new Date(setup.pending_episode_since).getTime() + strategy.confirmation_wait_minutes * 60000).toISOString()) : null;
  steps.push({ state: setup.pending_episode_since ? "now" : "todo", label: `A green ${candle} candle confirms`,
    detail: deadline ? `waiting — before ${deadline}` : `within ${strategy.confirmation_wait_minutes} min of the touch` });
  return steps;
}

function breakoutSteps(c: NonNullable<CoinView["consolidation"]>): Step[] {
  const width = n(c.zone_width_pct), limit = n(c.maximum_zone_pct);
  const steps: Step[] = [
    c.state === "warming_up" ? { state: "todo", label: "Price goes quiet", detail: "measuring the band" }
      : c.state === "too_wide" ? { state: "block", label: "Price goes quiet",
        detail: `${c.zone_hours}h range is ${pct(width, 2, false)} — needs ${pct(limit, 1, false)} or less`, progress: limit / Math.max(width, 0.0001) }
        : { state: "done", label: "Price goes quiet", detail: `${c.zone_hours}h in ${price(c.zone_bottom)}–${price(c.zone_top)}` },
    c.pending_break ? { state: "done", label: "Closes above the band", detail: `broke out at ${time(c.pending_break.broke_at)}` }
      : c.state === "breaking" ? { state: "now", label: "Closes above the band", detail: `above ${price(c.zone_top)} now` }
        : { state: "todo", label: "Closes above the band", detail: c.zone_top != null && c.state === "quiet" ? `top is ${price(c.zone_top)}` : undefined },
    c.pending_break ? { state: "now", label: `Still above after ${c.confirmation_wait_minutes} min`,
      detail: c.pending_break.confirm_at ? `checked at ${time(c.pending_break.confirm_at)}` : "checking" }
      : { state: "todo", label: `Still above after ${c.confirmation_wait_minutes} min` },
  ];
  // Without a confirmation wait the close above the band is the buy, so the last step is left out.
  return c.confirmation_wait_minutes > 0 ? steps : steps.slice(0, 2);
}

function pullbackSteps(p: PullbackView): Step[] {
  const dwell = span(p.dwell_minutes);
  return [
    p.state === "warming_up" ? { state: "todo", label: "In a clean uptrend", detail: "warming up the line" }
      : p.state === "no_uptrend" ? { state: "block", label: "In a clean uptrend", detail: "7-, 15- and 30-day averages not stacked upward" }
        : { state: "done", label: "In a clean uptrend" },
    p.state === "armed" ? { state: "done", label: `${dwell} under the ${p.ema_hours}h line`, detail: `${duration(p.below_minutes)} under` }
      : p.state === "dipping" ? { state: "todo", label: `${dwell} under the ${p.ema_hours}h line`,
        detail: `${duration(p.below_minutes)} so far, ${duration(p.minutes_to_arm)} to go`, progress: p.below_minutes / Math.max(p.dwell_minutes, 1) }
        : { state: "todo", label: `${dwell} under the ${p.ema_hours}h line`,
          detail: p.state === "above" ? `${pct(p.distance_to_line_pct, 2, false)} above the line now` : undefined, progress: p.state === "above" ? 0 : undefined },
    { state: p.state === "armed" ? "now" : "todo", label: "Closes back above the line",
      detail: p.state === "armed" ? `a close above ${price(p.line)} buys` : undefined },
  ];
}

function RightNow({ coin }: { coin: CoinView }) {
  const setup = coin.setup, strategy = coin.strategy, name = coin.label;
  const days = strategy.signal_average_days;
  const block = strategy.blocked_entry_hours_utc;
  const lots = coin.lots;
  const freeLot = lots.next_lot_usd != null;
  const ways: { key: keyof typeof SOURCE; title: string; steps: Step[]; off?: boolean; info: string }[] = [
    { key: "signal", title: "Dip", steps: dipSteps(coin),
      info: `Buys when ${name} rises from below into a ±${strategy.touch_zone_pct}% zone around its ${days}-day average (the mean of the last ${days} daily closes, UTC), and a green candle confirms within ${strategy.confirmation_wait_minutes} minutes. Skipped in a strong downtrend (7-, 15- and 30-day averages stacked downward).` },
  ];
  if (coin.consolidation) ways.push({ key: "breakout", title: "Quiet-band breakout", steps: breakoutSteps(coin.consolidation),
    info: `For when ${name} never comes back to its average. When the last ${coin.consolidation.zone_hours} hours stay inside a band no wider than ${pct(coin.consolidation.maximum_zone_pct, 1, false)}, a close above the top starts a ${coin.consolidation.confirmation_wait_minutes}-minute wait; if it is still above when the wait ends, it buys. These lots use a tighter −${n(coin.consolidation.stop_pct)}% stop.` });
  if (coin.pullback) ways.push({ key: "pullback", title: "Pullback", steps: pullbackSteps(coin.pullback),
    off: coin.entries?.pullback?.enabled === false,
    info: `In a clean uptrend, when ${name} spends at least ${span(coin.pullback.dwell_minutes)} under its ${coin.pullback.ema_hours}-hour line, the first minute that closes back above it buys. The lot then rides the trend.` });
  const cards = ways.map(way => ({ ...way, status: statusOf(way.steps, way.off) }));

  const gates = [
    { ok: coin.trading_enabled, label: coin.trading_enabled ? "Switched on" : "Switched off" },
    // A switched-off coin gets no next lot from the server, so the money chip would mislead: show it only when on.
    ...(coin.trading_enabled ? [{ ok: freeLot, label: freeLot ? `Free lot · ${usd(lots.next_lot_usd, 0)}` : lots.slot_free ? "No money for a lot" : "All lots open" }] : []),
    { ok: setup.entry_window_open, label: !block ? "Open all day"
      : setup.entry_window_open ? `Open · pauses ${hh(block.start)} UTC` : `Paused · opens ${hh(block.end)} UTC` },
  ];
  const soon = cards.find(card => card.status.text === "Buying soon");
  const verdict: WayStatus = !coin.trading_enabled ? { text: `Not buying — ${name} is switched off`, tone: "bad" }
    : !freeLot ? { text: `Not buying — ${lots.slot_free ? "no money left for a lot" : "every lot is open"}`, tone: "bad" }
      : !setup.entry_window_open ? { text: `Paused until ${block ? hh(block.end) : ""} UTC`, tone: "warn" }
        : soon ? { text: `About to buy — ${soon.title.toLowerCase()} is confirming`, tone: "good" }
          : cards.every(card => card.status.text !== "Waiting") ? { text: "Waiting — every way in is blocked for now", tone: "warn" }
            : { text: "Watching — waiting for a setup", tone: "muted" };

  return <Card title="What the strategy sees now" className="right-now">
    <p className={`rn-verdict ${verdict.tone}`}>{verdict.text}</p>
    <ul className="rn-gates" aria-label="Needed for any buy">
      {gates.map(gate => <li key={gate.label} className={gate.ok ? "ok" : "no"}><i aria-hidden="true">{gate.ok ? "✓" : "✕"}</i>{gate.label}</li>)}
    </ul>
    <div className="rn-ways">
      {cards.map(card => <WayCard key={card.key} source={card.key} title={card.title} status={card.status} steps={card.steps} info={card.info} />)}
    </div>
  </Card>;
}

/** Every way in, what it is set to, and the lots it is using. The core is always on; the rest can be switched. */
function WaysIn({ coin }: { coin: CoinView }) {
  const { open } = useControls();
  const name = coin.label;
  const lots = coin.lots;
  const entries = coin.entries ?? {};
  const modules = (["pullback", "pyramid"] as const).filter(key => entries[key]?.supported);
  if (!modules.length) return null;
  const chip = (key: "pullback" | "pyramid") =>
    entries[key]?.enabled ? <span className="tag applied">On</span> : <span className="tag">Off</span>;
  const used = (key: "pullback" | "pyramid") => {
    const module = entries[key]!;
    if (!module.enabled) return "no new lots";
    return `${module.open_lots} of the pot's ${lots.max_lots} lot${lots.max_lots === 1 ? "" : "s"} open`;
  };
  const pyramid = coin.pyramid;
  const nextAdd = pyramid?.parents.find(parent => parent.adds_left > 0 && parent.next_add_price != null);
  return <Card title="Ways in" className="ways-in"
    info={`Which ways in are switched on for ${name}. They all draw on the same lots, first come first served — the core (the dip and the quiet-band breakout) is always on.`}>
    <ul className="ways">
      <li>
        <div><b><span className="src-swatch src-dip">D</span><span className="src-swatch src-breakout">Q</span> Core · dip + quiet-band breakout</b>
          <small>{lots.open_lots}/{lots.max_lots} lot{lots.max_lots === 1 ? "" : "s"} open · always on</small></div>
        <span className="tag applied">Always on</span>
      </li>
      {modules.map(key => <li key={key}>
        <div><b><span className={`src-swatch ${sourceOf(key).cls}`}>{sourceOf(key).letter}</span>{" "}
          {key === "pullback" ? "Pullback" : "Add-ons"}</b>
          <small>{used(key)}
            {key === "pyramid" && nextAdd && entries.pyramid?.enabled
              ? ` · next add at ${price(nextAdd.next_add_price)} (${pct(nextAdd.distance_to_add_pct, 2, false)} away)`
              : ""}
            {key === "pullback" && coin.pullback && entries.pullback?.enabled
              ? ` · ${coin.pullback.state === "armed" ? "armed now" : coin.pullback.state === "dipping"
                ? `${duration(coin.pullback.below_minutes)} under the line` : "waiting for a pullback"}`
              : ""}</small></div>
        <div className="right">{chip(key)}
          <button className="ghost small" onClick={() => open({ kind: "entry-module", coin, module: key })}>Change</button></div>
      </li>)}
    </ul>
    {coin.pyramid && entries.pyramid?.enabled && (coin.pyramid.parents.length
      ? <p className="card-note">Adds so far: {coin.pyramid.adds_total} ({coin.pyramid.adds_open} open). A lot gets
        another lot every +{n(coin.pyramid.step_pct)}% above its buy price, up to {coin.pyramid.maximum_adds}, while price
        holds above the {n(coin.exit_plan.ema_minutes) / 60}-hour line. {coin.pyramid.add_exit === "with_parent"
          ? "Each add is sold the moment the lot it was added to is sold."
          : "Each add is then held against that line on its own."}</p>
      : <p className="card-note">Nothing to add to yet — an add needs an open {name} lot that is climbing.</p>)}
  </Card>;
}

function ExitMode({ coin }: { coin: CoinView }) {
  const plan = coin.exit_plan;
  // Worth showing whenever there is something to say: two exit modes, or two ways in.
  if (!plan.has_trend_exit && !coin.consolidation) return null;
  const hours = plan.ema_minutes ? n(plan.ema_minutes) / 60 : null;
  const name = coin.label;
  const riding = plan.next_lot_mode === "trend";
  const openModes = coin.positions.reduce(
    (count, position) => ({ ...count, [position.exit_mode]: (count[position.exit_mode] ?? 0) + 1 }),
    {} as Record<string, number>);
  const bySource = coin.positions.reduce((count, position) =>
    ({ ...count, [position.entry_source]: (count[position.entry_source] ?? 0) + 1 }), {} as Record<string, number>);
  return <Card title="How a win would be taken" className="exit-mode"
    info={hours
      ? `Both ways in — the dip and the quiet-band breakout — end the same way. Every lot keeps its stop and starts trailing once it is up. What happens after that depends on the trend at the moment of buying: in a clean uptrend the lot is held against the ${hours}-hour average line (trend ride), otherwise it hands back a share of its best profit (trailing stop). The mode is fixed when the lot opens and never changes, so two lots open at once can be in different modes.`
      : `Every ${name} lot takes profit the same way: once it is up ${n(plan.activation_pct)}%, a trailing stop follows the peak and sells after giving back ${n(plan.giveback_pct)}% of it. A trend-riding exit was tested on ${name} and left out — on paper it added money, but a walk-forward test showed the gain could not have been found in advance, and ${name} wins small and often, which is what this exit is for.`}>
    <div className={`mode-now ${hours ? (riding ? "mode-a" : "mode-b") : "mode-b"}`}>
      <span className={`mode-chip ${hours && riding ? "mode-a" : "mode-b"}`}>{hours && riding ? EXIT.trend.name : EXIT.giveback.name}</span>
      <div>
        <b>{riding && hours ? `Ride the trend line` : `Give back ${n(plan.giveback_pct)}% of the gain`}</b>
        <small>{!hours
          ? `Every ${name} lot keeps ${100 - n(plan.giveback_pct)}% of its best profit — both the dip and the quiet-band breakout, every time. ${name} wins small and often, so nothing is held for a bigger move.`
          : riding
            ? `The market is in a clean uptrend, so the next ${name} lot would be held until a minute closes below the ${hours}-hour line — letting a big move run instead of capping it near +1%.`
            : `The 7-, 15- and 30-day averages are not stacked upward, so the next ${name} lot would use the ordinary trailing stop and keep ${100 - n(plan.giveback_pct)}% of its best profit.`}</small>
      </div>
    </div>
    <dl className="mode-facts">
      {hours && <div><dt>Trend line now<Info text={`The ${hours}-hour exponential average of ${name}'s 1-minute closes. A trend-ride lot is sold at the next minute's open once a minute closes below this line.`} /></dt>
        <dd>{plan.trend_line == null ? "—" : price(plan.trend_line)}</dd></div>}
      {hours && <div><dt>Price vs line</dt>
        <dd className={plan.trend_line == null || coin.market.price == null ? "" : n(coin.market.price) >= n(plan.trend_line) ? "up" : "down"}>
          {plan.trend_line == null || coin.market.price == null ? "—"
            : pct((n(coin.market.price) / n(plan.trend_line) - 1) * 100, 2)}</dd></div>}
      {!hours && <div><dt>Keeps<Info text={`The share of the best profit a lot holds on to when the trailing stop sells it.`} /></dt>
        <dd>{100 - n(plan.giveback_pct)}% of the peak gain</dd></div>}
      <div><dt>Open lots</dt>
        <dd>{!coin.positions.length ? "none" : hours
          ? `${openModes.trend ?? 0} riding · ${openModes.giveback ?? 0} giving back`
          : `${coin.positions.length} open`}</dd></div>
      {coin.consolidation && <div><dt>Bought by<Info text={`Which way in each open lot came through: the dip into the average, a quiet-band break out of a quiet band${coin.pullback ? ", or the pullback entry" : ""}.`} /></dt>
        <dd>{coin.positions.length
          ? (Object.keys(SOURCE) as (keyof typeof SOURCE)[]).filter(key => bySource[key] || (key !== "manual" && (key !== "pullback" || coin.pullback)
              && (key !== "pyramid" || coin.pyramid)))
            .map(key => `${bySource[key] ?? 0} ${SOURCE[key].name.toLowerCase()}`).join(" · ")
          : "none"}</dd></div>}
    </dl>
  </Card>;
}

function Activity({ coin }: { coin: CoinView }) {
  const [tab, setTab] = useState<"signals" | "trades" | "orders">("signals");
  const counts = coin.signal_counts;
  const name = coin.label;
  return <Card title="Activity" info="Signals are every touch of the zone and what the strategy decided. Trades are closed lots. Orders are every simulated buy and sell with its fee.">
    <Tabs label="Activity" value={tab} onChange={setTab}
      options={[{ value: "signals", label: "Signals" }, { value: "trades", label: "Trades" }, { value: "orders", label: "Orders" }]} />
    {tab === "signals" && (coin.signals.length ? <>
      <div className="mini-stats"><span>Touches <b>{counts.touches}</b></span><span>Bought <b>{counts.confirmed}</b></span>
        <span>06–12 skips <b>{counts.skipped_time_window}</b></span><span>Trend skips <b>{counts.rejected_trend}</b></span>
        {coin.consolidation && <span>Breakouts <b>{counts.breakouts}</b></span>}
        {coin.pullback && <span>Pullbacks <b>{counts.pullbacks}</b> · bought <b>{counts.pullbacks_confirmed}</b></span>}</div>
      <ScrollList visible={5}><ul className="rows">{coin.signals.map(signal => {
        const status = signal.status ?? signal.episode_status;
        const kind = signal.details?.kind as string | undefined;
        const source = sourceOf(kind === "pullback" ? "pullback" : kind === "consolidation" ? "breakout" : "signal");
        const what = kind === "pullback"
          ? `Pullback · ${duration(Number(signal.details.below_minutes ?? 0))} under the line · back above ${time(signal.touch_time, true)}`
          : kind === "consolidation"
            ? `Breakout ${time(signal.touch_time, true)} · band top ${price(signal.average_value)}`
            : `Touch ${time(signal.touch_time, true)} · avg ${price(signal.average_value)}`;
        return <li key={signal.episode_id}>
          <div><b><span className={`src-swatch ${source.cls}`}>{source.letter}</span> {label(status)}</b><small>{what}</small></div>
          <div className="right"><span className={`tag ${status === "confirmed" ? "applied" : status === "pending_confirmation" ? "pending" : "muted"}`}>
            {status === "confirmed" ? `entry ${time(signal.entry_time)}` : status === "pending_confirmation" ? "live" : "no buy"}</span></div>
        </li>;
      })}</ul></ScrollList></> : <Empty title="No touches yet">Each time {name} touches the {coin.strategy.signal_average_days}-day zone it's listed here with the decision.</Empty>)}
    {tab === "trades" && <TradeList trades={coin.trades} />}
    {tab === "orders" && (coin.orders.length ? <ScrollList visible={5}><ul className="rows">{coin.orders.map(order => <li key={order.order_id}>
      <div><b className={order.side === "buy" ? "up" : "down"}>{order.side === "buy" ? "Buy" : "Sell"} {amount(order.quantity)} {name}</b>
        <small>{time(order.requested_at, true)} at {price(order.fill_price)}</small></div>
      <div className="right"><b>{usd(order.notional_usd)}</b><small>fee {usd(order.fee_usd, 3)} {order.fee_asset}{order.fee_asset === "BNB" ? ` (${n(order.fee_bnb).toFixed(6)})` : ""}</small></div>
    </li>)}</ul></ScrollList> : <Empty title="No orders yet" />)}
  </Card>;
}

function Rule({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><dt>{label}</dt><dd>{children}</dd></div>;
}

function Rules({ coin }: { coin: CoinView }) {
  const s = coin.strategy;
  const name = coin.label;
  const block = s.blocked_entry_hours_utc;
  const c = coin.consolidation;
  const pb = coin.pullback;
  const hours = coin.exit_plan.has_trend_exit ? n(coin.exit_plan.ema_minutes) / 60 : null;
  // The ways in are numbered in the order they are listed: dip, quiet-band breakout, pullback, add-ons.
  const count = 1 + (c ? 1 : 0) + (pb ? 1 : 0) + (coin.pyramid ? 1 : 0);
  const COUNTS = ["", "One", "Two", "Three", "Four"];
  const ways = count > 1 ? `${COUNTS[count]} ways in` : "How it buys";

  return <Card title="Strategy rules" className="rules-card"
    info="The fixed rules the bot follows for this coin. They were chosen from backtests; changing them would restart the evaluation.">

    <h4 className="rule-group">{ways}</h4>
    <dl className="rules">
      <Rule label={c ? "1 · The dip" : "Entry"}>
        {name} falls to its {s.signal_average_days}-day average, touching ±{s.touch_zone_pct}% of it{" "}
        <b>from below</b>, then a green {s.signal_timeframe} candle within {s.confirmation_wait_minutes} minutes.
      </Rule>
      {c && <Rule label="2 · Quiet-band breakout">
        {name} spends {c.zone_hours} hours inside a band no wider than {pct(c.maximum_zone_pct, 1, false)}, then
        closes above the top of it.{" "}
        {c.confirmation_wait_minutes > 0
          ? `After a ${c.confirmation_wait_minutes}-minute wait, if it is still above the top, the next minute buys.`
          : "The next minute buys — no waiting."}
      </Rule>}
      {pb && <Rule label="3 · The pullback">
        In an uptrend, {name} spends at least {span(pb.dwell_minutes)} below its {pb.ema_hours}-hour average line,
        then a minute closes back <b>above</b> it. The next minute buys, from the same lots as the other two ways in.
      </Rule>}
      <Rule label={c ? "The dip never buys when" : "Never buys when"}>
        The 7-, 15- and 30-day averages are stacked downward{s.requires_close_above_30d ? `, or the confirming candle closes at or below the 30-day average${s.maximum_above_30d_pct != null ? ` or more than ${n(s.maximum_above_30d_pct)}% above it` : ""}` : ""}
        {block ? `, or the clock is between ${hh(block.start)} and ${hh(block.end)} UTC` : ""}.
      </Rule>
      {c && <Rule label={block ? "The breakout never buys when" : "The breakout's filters"}>
        {block
          ? <>The clock is between {hh(block.start)} and {hh(block.end)} UTC — its only timing rule.{" "}</>
          : <>None on timing: {name} has no blocked hours, so a break is taken whenever one happens.{" "}</>}
        It does <b>not</b> wait for an uptrend{s.requires_close_above_30d ? ", and it does not use the dip rule's 30-day filter" : ""}:
        demanding one screens out exactly the breaks that start a new trend, and cost money on every coin it
        was tested on.
      </Rule>}
      {coin.pyramid && <Rule label={`${count} \u00b7 Add-ons`}>
        While a {name} lot is winning, another lot is added every +{n(coin.pyramid.step_pct)}% above its buy price
        (up to {coin.pyramid.maximum_adds}), as long as price is above the {hours}-hour line. {coin.pyramid.add_exit === "with_parent"
          ? <>An add has no exit of its own: it carries the <b>same protective stop</b> as the lot it was added to, and
            is sold in the same minute that lot is sold.</>
          : <>Every add is then held against that line in its own right, so it can outlive the lot it was added to.</>}{" "}
        Switched on or off in <b>Ways in</b>.
      </Rule>}
      {pb && <Rule label="The pullback never buys when">
        The 7-, 15- and 30-day averages are not stacked upward{block ? `, or the clock is between ${hh(block.start)} and ${hh(block.end)} UTC` : ""},
        or every lot is already open.
      </Rule>}
    </dl>

    <h4 className="rule-group">How it sells</h4>
    <dl className="rules">
      <Rule label="Stop">
        Sell if {name} falls {n(s.stop_pct)}% below the buy price{c ? `, or ${n(c.stop_pct)}% for a breakout lot` : ""}{pb ? " (a pullback lot uses the dip's stop)" : ""}.
        {" "}The stop sits on Binance, so it works even if this app is off.
      </Rule>
      {hours ? <>
        <Rule label="Trend ride · in an uptrend">
          Once up +{n(s.trail_activation_pct)}%, hold while {name} keeps closing above the {hours}-hour trend
          line. The first minute that closes below it sells at the next minute's open. Wins can run far past +1%.
          {pb ? " Every pullback lot rides the trend, since it is only ever bought in an uptrend." : ""}
        </Rule>
        <Rule label="Trailing stop · any other time">
          Once up +{n(s.trail_activation_pct)}%, a trailing stop follows the peak and sells after giving back{" "}
          {n(s.trail_giveback_pct)}% of the best profit — usually around +1%.
        </Rule>
      </> : <Rule label="Profit">
        At +{n(s.trail_activation_pct)}% a trailing stop starts; it sells after a {n(s.trail_giveback_pct)}% giveback
        of the peak profit.{c && (n(c.trail_activation_pct) !== n(s.trail_activation_pct)
          || n(c.trail_giveback_pct) !== n(s.trail_giveback_pct))
          ? <> A breakout lot uses its own numbers: the trail starts at +{n(c.trail_activation_pct)}% and gives
            back {n(c.trail_giveback_pct)}%.</>
          : ""}
      </Rule>}
      <Rule label="No time limit">Only the stop{hours ? ", the trend line" : ""} or the trail close a lot.</Rule>
    </dl>

    <h4 className="rule-group">Money</h4>
    <dl className="rules">
      <Rule label="Size">{coin.lots.max_lots} lot{coin.lots.max_lots === 1 ? "" : "s"} of {usd(coin.lots.lot_size_usd)}
        {" "}in one shared pot: every coin that is on and every way in draws on it, first come first served.
        {" "}Set on the Main page. When the wallet holds less than a full lot, a buy uses what is left.</Rule>
      <Rule label="Costs">{n(s.usdt_fee_bps) / 100}% per side in USDT, or {n(s.bnb_fee_bps) / 100}% with BNB, plus {n(s.slippage_bps) / 100}% slippage.</Rule>
    </dl>

    <details className="rule-backtest"><summary>What the backtest showed</summary><p>{s.backtest}</p></details>
  </Card>;
}

export function CoinPage({ data, coin, interval, onInterval, chartMode, onChartMode }:
  { data: Dashboard; coin: CoinView; interval: Interval; onInterval: (value: Interval) => void; chartMode: "line" | "candles"; onChartMode: (value: "line" | "candles") => void }) {
  const stats = coin.stats;
  const setup = coin.setup;
  const name = coin.label;
  const days = coin.strategy.signal_average_days;
  const { open, binance } = useControls();
  return <div className="page">
    <section className={`hero ${name.toLowerCase()}`}>
      <div className="hero-top">
        <span className="eyebrow"><CoinToken symbol={coin.symbol} />{name} / USDT · {ago(coin.market.open_time && new Date(new Date(coin.market.open_time).getTime() + 60_000).toISOString())}</span>
        {!coin.trading_enabled && <Tip text={`${name} is switched off. No new ${name} lots open until you switch it on${coin.positions.length ? "; open lots still close by their stop or trailing stop" : ""}.`}>
          <button className="primary small" onClick={() => open({ kind: "trading", coin, enable: true })}>Switch on</button></Tip>}
      </div>
      <strong className="hero-value">{price(coin.market.price)}</strong>
      <div className="hero-sub"><span className={`pill ${tone(coin.market.change_24h_pct)}`}>{pct(coin.market.change_24h_pct)} 24h</span>
        <span className={`pill ${tone(n(coin.money.realized_pnl_usd) + n(coin.money.unrealized_pnl_usd))}`}>{signedUsd(n(coin.money.realized_pnl_usd) + n(coin.money.unrealized_pnl_usd))} {name} P&amp;L</span></div>
      <div className="hero-foot">
        <span>{days}D avg <b>{price(setup.signal_average)}</b><Info text={`Mean of the last ${days} completed daily closes of ${name}. It updates once a day at 00:00 UTC.`} /></span>
        <span>Zone <b>{price(setup.zone_lower)} – {price(setup.zone_upper)}</b></span>
      </div>
    </section>

    <RightNow coin={coin} />

    <Card title={`${name} price chart`} action={<Tabs label="Chart style" value={chartMode} onChange={onChartMode}
      options={[{ value: "line", label: "Line" }, { value: "candles", label: "Candles" }]} />}
      info={`The shaded band is the entry zone around the average. Each trade is coloured by the entry that bought it: a solid line when it opened, a short line where the trailing stop started, and a dashed line when it closed, with a green or red dot at the sale.${
        coin.exit_plan.has_trend_exit ? ` The orange line is the ${n(coin.exit_plan.ema_minutes) / 60}-hour trend line: lots marked "rides" are held against it, and it is only drawn on the 3m, 15m and 1h charts.` : ""}${
        coin.consolidation ? ` The green boxes are stretches where ${name} was quiet enough for a breakout — a close above a box's top is what the breakout buys.` : ""}${
        coin.pullback ? ` The violet line is the ${coin.pullback.ema_hours}-hour pullback line and the violet shading marks where a pullback was armed: in an uptrend and under the line for ${span(coin.pullback.dwell_minutes)} or more — a close back above the line there buys a pullback lot. It is drawn on charts up to 4h.` : ""} Each buy carries a badge saying who bought it: D the dip, Q the quiet-band breakout${coin.pullback ? ", P the pullback" : ""}, B Buy now — with the trade's number.`}>
      <Tabs label="Candle size" value={interval} onChange={onInterval} options={INTERVALS} />
      <PriceChart coin={name} points={coin.chart} markers={coin.markers} zonePct={coin.strategy.touch_zone_pct}
        averageDays={days} mode={chartMode}
        trendHours={coin.exit_plan.has_trend_exit ? n(coin.exit_plan.ema_minutes) / 60 : null}
        zoneHours={coin.consolidation?.zone_hours ?? null}
        pullbackHours={coin.pullback?.ema_hours ?? null} pullbackDwell={coin.pullback?.dwell_minutes ?? null} />
    </Card>

    <WaysIn coin={coin} />
    <ExitMode coin={coin} />

    <Card title={`Open ${name} lots (${coin.positions.length})`} info="Every open lot with its live stop, trailing-stop start and profit. Close sells a lot at the next minute.">
      {coin.positions.length
        ? <ScrollList visible={2}><div className="positions">{coin.positions.map(position =>
            <PositionCard key={position.position_id} position={position} data={data} />)}</div></ScrollList>
        : <Empty title="No open lots">The next confirmed {name} signal will buy lot {coin.lots.lot_number}.</Empty>}
    </Card>

    <LotsCard data={data} coin={coin} />
    {binance?.attached && <BnbCard data={data} compact />}
    <Activity coin={coin} />

    <Card title={`${name} performance`} info={`Results of closed ${name} trades, after all costs.`}>
      <div className="stat-grid four">
        <Stat label="Trades" value={stats.trades} sub={`${stats.trailing_exits} trail · ${stats.stop_exits} stop`} />
        <Stat label="Win rate" value={stats.win_rate_pct == null ? "—" : pct(stats.win_rate_pct, 0, false)} sub={`${stats.wins}/${stats.wins + stats.losses}`} />
        <Stat label="Won" value={usd(stats.gross_win_usd)} valueClass="up" sub={`${stats.wins} winning trades`} />
        <Stat label="Lost" value={usd(stats.gross_loss_usd)} valueClass="down" sub={`${stats.losses} losing trades`} />
      </div>
      <div className="mini-stats"><span>Avg hold <b>{duration(stats.average_hold_minutes)}</b></span>
        <span>Best <b className="up">{pct(stats.best_pct)}</b></span><span>Worst <b className="down">{pct(stats.worst_pct)}</b></span></div>
      <p className="card-note">{name} costs so far: {usd(stats.fees_usd)} fees · {usd(stats.slippage_usd)} slippage · realized {signedUsd(stats.realized_usd)}</p>
    </Card>

    <Rules coin={coin} />
  </div>;
}
