import { useState } from "react";
import type { CoinView, Dashboard, Interval } from "./api";
import { PriceChart } from "./charts";
import { ago, amount, duration, label, n, pct, price, signedUsd, time, tone, until, usd } from "./format";
import { useControls } from "./controls";
import { BnbCard, LotsCard, PositionCard, TradeList } from "./panels";
import { SOURCE, sourceOf } from "./sources";
import { Card, CoinToken, Empty, Info, ScrollList, Stat, Tabs } from "./ui";

const INTERVALS: { value: Interval; label: string }[] = [
  { value: "3m", label: "3m" }, { value: "15m", label: "15m" }, { value: "1h", label: "1h" },
  { value: "4h", label: "4h" }, { value: "1d", label: "1D" },
];

function Check({ ok, title, text, info }: { ok: boolean | null; title: string; text: string; info: string }) {
  return <li className={ok == null ? "wait" : ok ? "ok" : "no"}>
    <i aria-hidden>{ok == null ? "…" : ok ? "✓" : "✕"}</i>
    <div><b>{title}<Info text={info} /></b><span>{text}</span></div>
  </li>;
}

const hh = (hour: number) => `${String(hour).padStart(2, "0")}:00`;
// "3 hours" reads better than "3h 0m" in a rule; anything uneven falls back to the usual duration.
const span = (minutes: number) => minutes % 60 === 0 ? `${minutes / 60} hour${minutes === 60 ? "" : "s"}` : duration(minutes);

function RightNow({ coin }: { coin: CoinView }) {
  const setup = coin.setup;
  const strategy = coin.strategy;
  const days = strategy.signal_average_days;
  const name = coin.label;
  const candle = `${strategy.signal_timeframe.replace("m", "")}-minute`;
  const zoneText = setup.zone_state === "below"
    ? `${name} is ${pct(setup.distance_to_zone_pct, 2, false)} below the zone. A rise into it (${price(setup.zone_lower)}–${price(setup.zone_upper)}) is the setup.`
    : setup.zone_state === "inside"
      ? `${name} is inside the zone now. If it came from below, the strategy waits for a green ${candle} candle.`
      : setup.zone_state === "above"
        ? `${name} is ${pct(setup.distance_to_zone_pct, 2, false)} above the zone. It must drop below ${price(setup.zone_lower)} first, then come back up.`
        : "Waiting for enough price history to compute the average.";
  const block = strategy.blocked_entry_hours_utc;
  const next = coin.lots;
  // How far the price is above the 30-day average, in % (used by the capped trend rule).
  const stretch = setup.average_30d && coin.market.price ? (n(coin.market.price) / n(setup.average_30d) - 1) * 100 : 0;
  let headline = "Waiting for a setup";
  if (!coin.trading_enabled) headline = `Switched off — no new ${name} trades`;
  else if (setup.pending_episode_since) headline = "Touch detected — waiting for a green candle";
  else if (!setup.entry_window_open) headline = `Paused: no new entries until ${block ? hh(block.end) : ""} UTC`;
  else if (!setup.trend_allows_entries) headline = `Paused: ${name} is in a strong downtrend`;
  else if (coin.pullback?.state === "armed" && next.next_lot_usd != null)
    headline = `Pullback armed — a close back above ${price(coin.pullback.line)} buys`;
  else if (next.next_lot_usd == null) headline = "Signals would be skipped — no free lot";
  else if (setup.zone_state === "below") headline = "Ready — watching for a rise into the zone";
  return <Card title="What the strategy sees now" className="right-now"
    info={`A live checklist of the ${name} entry rules. A buy happens only when every item is green and a green ${candle} candle confirms a touch from below.`}>
    <p className="headline">{headline}</p>
    <ul className="checks">
      <Check ok={setup.zone_state === "below" || setup.zone_state === "inside" ? true : setup.zone_state === "above" ? false : null}
        title={`Price vs ${days}-day zone`} text={zoneText}
        info={`The ${days}-day average is the mean of the last ${days} daily closing prices (UTC). The entry zone is ±${strategy.touch_zone_pct}% around it. A buy needs ${name} to reach the zone from below.`} />
      <Check ok={setup.regime === "missing" ? null : setup.trend_allows_entries} title="Trend filter"
        text={setup.regime === "bearish" ? "Strong downtrend (7-day < 15-day < 30-day average) — entries are skipped."
          : setup.regime === "missing" ? "Needs 30 days of history." : `Trend is ${setup.regime} — entries allowed.`}
        info="Skips buys when the 7-, 15- and 30-day averages are stacked downward, which marks a strong downtrend." />
      {strategy.requires_close_above_30d && <Check ok={setup.average_30d == null || coin.market.price == null ? null
          : n(coin.market.price) > n(setup.average_30d) && (strategy.maximum_above_30d_pct == null || stretch <= n(strategy.maximum_above_30d_pct))}
        title={strategy.maximum_above_30d_pct == null ? "Above 30-day average" : `Above 30-day average, by at most ${n(strategy.maximum_above_30d_pct)}%`}
        text={setup.average_30d == null ? "Needs 30 days of history."
          : n(coin.market.price) <= n(setup.average_30d) ? `${name} is below its 30-day average (${price(setup.average_30d)}).`
            : strategy.maximum_above_30d_pct != null && stretch > n(strategy.maximum_above_30d_pct)
              ? `${name} is ${stretch.toFixed(1)}% above its 30-day average (${price(setup.average_30d)}) — too stretched to buy.`
              : `${name} is ${stretch.toFixed(1)}% above its 30-day average (${price(setup.average_30d)}).`}
        info={`The confirming candle must close above the 30-day average, so ${name} only buys dips inside an uptrend. In the backtest this filter was what kept the later period profitable.`} />}
      {block ? <Check ok={setup.entry_window_open} title="Time window"
        text={setup.entry_window_open ? `Open. Entries pause ${hh(block.start)}–${hh(block.end)} UTC in ${until(setup.entry_window_changes_at)}.`
          : `Paused until ${hh(block.end)} UTC (${until(setup.entry_window_changes_at)}).`}
        info={`In the ${name} backtest, buys placed between ${hh(block.start)} and ${hh(block.end)} UTC did worse, so the strategy skips them. Open lots are still managed during this window.`} />
        : <Check ok title="Time window" text="Open all day — this strategy buys at any hour."
          info={`In the ${name} backtest, skipping any hours of the day did not help, so it trades around the clock.`} />}
      <Check ok={next.next_lot_usd != null} title="Money for the next lot"
        text={!coin.trading_enabled ? `${name} is switched off — switch it on to let it take lots from the shared pot.`
          : next.next_lot_usd != null
          ? n(next.next_lot_usd) < n(next.lot_size_usd)
            ? `Lot ${next.lot_number} of ${next.max_lots} would use ${usd(next.next_lot_usd)} — all that is left of its ${usd(next.lot_size_usd)}.`
            : `Lot ${next.lot_number} of ${next.max_lots} would use ${usd(next.next_lot_usd)}.`
          : !next.slot_free ? `All ${next.max_lots} shared lots are open.` : `No free USDT left on Binance.`}
        info={`Each buy spends one lot of the shared pot, whichever coin or way in fired. When the pot holds less than a full lot, the buy uses whatever is left. A signal is skipped if every shared lot is open or no USDT is free.`} />
      {coin.consolidation && <Check
        ok={coin.consolidation.state === "breaking" || coin.consolidation.pending_break != null ? true
          : coin.consolidation.state === "quiet" ? null : false}
        title={`Quiet band (Mode C)`}
        text={coin.consolidation.pending_break
          ? `Broke out at ${time(coin.consolidation.pending_break.broke_at)}. If ${name} is still above ${price(coin.consolidation.pending_break.zone_top)} at ${time(coin.consolidation.pending_break.confirm_at)}, it buys.`
          : coin.consolidation.state === "breaking"
            ? `${name} has pushed above the quiet band's top of ${price(coin.consolidation.zone_top)} — a close above it starts the ${coin.consolidation.confirmation_wait_minutes}-minute wait.`
            : coin.consolidation.state === "quiet"
              ? `${name} has been quiet for ${coin.consolidation.zone_hours} hours, inside ${price(coin.consolidation.zone_bottom)}–${price(coin.consolidation.zone_top)} (${pct(coin.consolidation.zone_width_pct, 2, false)} wide). A close above the top is the signal.`
              : coin.consolidation.state === "too_wide"
                ? `Not quiet enough: the last ${coin.consolidation.zone_hours} hours span ${pct(coin.consolidation.zone_width_pct, 2, false)}, and Mode C needs ${pct(coin.consolidation.maximum_zone_pct, 1, false)} or tighter.`
                : "Waiting for enough price history to measure the band."}
        info={`Mode C is the second way in, for when ${name} never comes back down to its average. When the last ${coin.consolidation.zone_bars} bars of the ${coin.consolidation.chart_minutes / 60}-hour chart (${coin.consolidation.zone_hours} hours) all sit inside a band no wider than ${pct(coin.consolidation.maximum_zone_pct, 1, false)}, a close above that band's top starts a ${coin.consolidation.confirmation_wait_minutes}-minute wait. If the price is still above the top when the wait ends, the next minute buys. These lots use a tighter −${n(coin.consolidation.stop_pct)}% stop.`} />}
      {coin.pullback && <PullbackCheck coin={coin} />}
      {setup.pending_episode_since && <Check ok={null} title="Waiting for confirmation"
        text={`Touch at ${time(setup.pending_episode_since)}. A green ${candle} candle before ${time(new Date(new Date(setup.pending_episode_since).getTime() + strategy.confirmation_wait_minutes * 60000).toISOString())} triggers the buy.`}
        info={`After a touch from below, the first ${candle} candle that closes higher than it opened (within ${strategy.confirmation_wait_minutes} minutes) confirms the entry. If ${name} leaves the zone first, the setup is cancelled.`} />}
    </ul>
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
    info={`Which ways in are switched on for ${name}. They all draw on the same lots, first come first served — the core (the dip and Mode C) is always on.`}>
    <ul className="ways">
      <li>
        <div><b><span className="src-swatch src-dip">D</span><span className="src-swatch src-breakout">C</span> Core · dip + Mode C</b>
          <small>{lots.open_lots}/{lots.max_lots} lot{lots.max_lots === 1 ? "" : "s"} open · always on</small></div>
        <span className="tag applied">Always on</span>
      </li>
      {modules.map(key => <li key={key}>
        <div><b><span className={`src-swatch ${sourceOf(key).cls}`}>{sourceOf(key).letter}</span>{" "}
          {key === "pullback" ? "Pullback" : "Pyramid adds"}</b>
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

/** The third way in, live: is ETH in an uptrend, under its pullback line, and for how long. */
function PullbackCheck({ coin }: { coin: CoinView }) {
  const p = coin.pullback!;
  const name = coin.label;
  const hours = p.ema_hours;
  const dwell = span(p.dwell_minutes);
  // It buys from the coin's one set of lots, like the dip and Mode C.
  const lots = coin.lots.next_lot_usd == null ? " No free lot right now, so a signal would be skipped." : "";
  const text = p.state === "warming_up" ? `Warming up the ${hours}-hour line from stored prices.`
    : p.state === "no_uptrend" ? `Waiting for an uptrend: the 7-, 15- and 30-day averages must be stacked upward. The pullback entry only buys pauses inside a climb.`
      : p.state === "above" ? `${name} is ${pct(p.distance_to_line_pct, 2, false)} above its ${hours}-hour line (${price(p.line)}). A pullback starts when a minute closes below it.`
        : p.state === "dipping" ? `${name} has been under its ${hours}-hour line for ${duration(p.below_minutes)} — ${duration(p.minutes_to_arm)} more and a close back above ${price(p.line)} buys.`
          : `Armed: under the ${hours}-hour line for ${duration(p.below_minutes)}. The next minute that closes above ${price(p.line)} buys at the following minute's open.`;
  return <Check ok={p.state === "armed" ? true : p.state === "no_uptrend" ? false : null}
    title="Pullback in the uptrend" text={text + (p.state === "warming_up" ? "" : lots)}
    info={`The third way in, for when ${name} trends up in a wide range and never comes back to its ${coin.strategy.signal_average_days}-day average or goes quiet enough for Mode C. In an uptrend, when ${name} spends at least ${dwell} under its ${hours}-hour average line, the first minute that closes back above it buys. It takes a lot from the same set the dip and Mode C use, first come first served, and because it is always bought in an uptrend the lot rides the trend line (Mode A).`} />;
}

/** Which of the two profit-taking modes a lot bought right now would use, and why. */
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
      ? `Both ways in — the dip and Mode C — end the same way. Every lot keeps its stop and starts trailing once it is up. What happens after that depends on the trend at the moment of buying: in a clean uptrend the lot is held against the ${hours}-hour average line (Mode A), otherwise it hands back a share of its best profit (Mode B). The mode is fixed when the lot opens and never changes, so two lots open at once can be in different modes.`
      : `Every ${name} lot takes profit the same way: once it is up ${n(plan.activation_pct)}%, a trailing stop follows the peak and sells after giving back ${n(plan.giveback_pct)}% of it. A trend-riding exit was tested on ${name} and left out — on paper it added money, but a walk-forward test showed the gain could not have been found in advance, and ${name} wins small and often, which is what this exit is for.`}>
    <div className={`mode-now ${hours ? (riding ? "mode-a" : "mode-b") : "mode-b"}`}>
      <span className="mode-chip">{hours ? (riding ? "Mode A" : "Mode B") : "Mode B"}</span>
      <div>
        <b>{riding && hours ? `Ride the trend line` : `Give back ${n(plan.giveback_pct)}% of the gain`}</b>
        <small>{!hours
          ? `Every ${name} lot keeps ${100 - n(plan.giveback_pct)}% of its best profit — both the dip and Mode C, every time. ${name} wins small and often, so nothing is held for a bigger move.`
          : riding
            ? `The market is in a clean uptrend, so the next ${name} lot would be held until a minute closes below the ${hours}-hour line — letting a big move run instead of capping it near +1%.`
            : `The 7-, 15- and 30-day averages are not stacked upward, so the next ${name} lot would use the ordinary trailing stop and keep ${100 - n(plan.giveback_pct)}% of its best profit.`}</small>
      </div>
    </div>
    <dl className="mode-facts">
      {hours && <div><dt>Trend line now<Info text={`The ${hours}-hour exponential average of ${name}'s 1-minute closes. A Mode A lot is sold at the next minute's open once a minute closes below this line.`} /></dt>
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
      {coin.consolidation && <div><dt>Bought by<Info text={`Which way in each open lot came through: the dip into the average, a Mode C break out of a quiet band${coin.pullback ? ", or the pullback entry" : ""}.`} /></dt>
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
        {coin.consolidation && <span>Mode C breaks <b>{counts.breakouts}</b></span>}
        {coin.pullback && <span>Pullbacks <b>{counts.pullbacks}</b> · bought <b>{counts.pullbacks_confirmed}</b></span>}</div>
      <ScrollList visible={5}><ul className="rows">{coin.signals.map(signal => {
        const status = signal.status ?? signal.episode_status;
        const kind = signal.details?.kind as string | undefined;
        const source = sourceOf(kind === "pullback" ? "pullback" : kind === "consolidation" ? "breakout" : "signal");
        const what = kind === "pullback"
          ? `Pullback · ${duration(Number(signal.details.below_minutes ?? 0))} under the line · back above ${time(signal.touch_time, true)}`
          : kind === "consolidation"
            ? `Mode C break ${time(signal.touch_time, true)} · band top ${price(signal.average_value)}`
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
  // The ways in are numbered in the order they are listed: dip, Mode C, pullback, adds.
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
      {c && <Rule label="2 · The quiet band (Mode C)">
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
      {c && <Rule label={block ? "Mode C never buys when" : "Mode C's filters"}>
        {block
          ? <>The clock is between {hh(block.start)} and {hh(block.end)} UTC — its only timing rule.{" "}</>
          : <>None on timing: {name} has no blocked hours, so a break is taken whenever one happens.{" "}</>}
        It does <b>not</b> wait for an uptrend{s.requires_close_above_30d ? ", and it does not use the dip rule's 30-day filter" : ""}:
        demanding one screens out exactly the breaks that start a new trend, and cost money on every coin it
        was tested on.
      </Rule>}
      {coin.pyramid && <Rule label={`${count} \u00b7 Adds (pyramid)`}>
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
        Sell if {name} falls {n(s.stop_pct)}% below the buy price{c ? `, or ${n(c.stop_pct)}% for a Mode C lot` : ""}{pb ? " (a pullback lot uses the dip's stop)" : ""}.
        {" "}The stop sits on Binance, so it works even if this app is off.
      </Rule>
      {hours ? <>
        <Rule label="Mode A · in an uptrend">
          Once up +{n(s.trail_activation_pct)}%, hold while {name} keeps closing above the {hours}-hour trend
          line. The first minute that closes below it sells at the next minute's open. Wins can run far past +1%.
          {pb ? " Every pullback lot is a Mode A lot, since it is only ever bought in an uptrend." : ""}
        </Rule>
        <Rule label="Mode B · any other time">
          Once up +{n(s.trail_activation_pct)}%, a trailing stop follows the peak and sells after giving back{" "}
          {n(s.trail_giveback_pct)}% of the best profit — usually around +1%.
        </Rule>
      </> : <Rule label="Profit">
        At +{n(s.trail_activation_pct)}% a trailing stop starts; it sells after a {n(s.trail_giveback_pct)}% giveback
        of the peak profit.{c && (n(c.trail_activation_pct) !== n(s.trail_activation_pct)
          || n(c.trail_giveback_pct) !== n(s.trail_giveback_pct))
          ? <> A Mode C lot uses its own numbers: the trail starts at +{n(c.trail_activation_pct)}% and gives
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
  const { open } = useControls();
  return <div className="page">
    <section className={`hero ${name.toLowerCase()}`}>
      <span className="eyebrow"><CoinToken symbol={coin.symbol} />{name} / USDT · {ago(coin.market.open_time && new Date(new Date(coin.market.open_time).getTime() + 60_000).toISOString())}</span>
      <strong className="hero-value">{price(coin.market.price)}</strong>
      <div className="hero-sub"><span className={`pill ${tone(coin.market.change_24h_pct)}`}>{pct(coin.market.change_24h_pct)} 24h</span>
        <span className={`pill ${tone(n(coin.money.realized_pnl_usd) + n(coin.money.unrealized_pnl_usd))}`}>{signedUsd(n(coin.money.realized_pnl_usd) + n(coin.money.unrealized_pnl_usd))} {name} P&amp;L</span></div>
      <div className="hero-foot">
        <span>{days}D avg <b>{price(setup.signal_average)}</b><Info text={`Mean of the last ${days} completed daily closes of ${name}. It updates once a day at 00:00 UTC.`} /></span>
        <span>Zone <b>{price(setup.zone_lower)} – {price(setup.zone_upper)}</b></span>
      </div>
    </section>

    {!coin.trading_enabled && <div className="banner warning paused-banner"><p><b>{name} is switched off.</b> No new {name} lots open until you switch it on{coin.positions.length ? "; open lots still close by their stop or trailing stop" : ""}.</p>
      <button className="secondary small" onClick={() => open({ kind: "trading", coin, enable: true })}>Switch on</button></div>}
    <RightNow coin={coin} />

    <Card title={`${name} price chart`} action={<Tabs label="Chart style" value={chartMode} onChange={onChartMode}
      options={[{ value: "line", label: "Line" }, { value: "candles", label: "Candles" }]} />}
      info={`The shaded band is the entry zone around the average. Each trade is coloured by the entry that bought it: a solid line when it opened, a short line where the trailing stop started, and a dashed line when it closed, with a green or red dot at the sale.${
        coin.exit_plan.has_trend_exit ? ` The orange line is the ${n(coin.exit_plan.ema_minutes) / 60}-hour trend line: lots marked "rides" are held against it, and it is only drawn on the 3m, 15m and 1h charts.` : ""}${
        coin.consolidation ? ` The green boxes are stretches where ${name} was quiet enough for Mode C — a close above a box's top is what Mode C buys.` : ""}${
        coin.pullback ? ` The violet line is the ${coin.pullback.ema_hours}-hour pullback line and the violet shading marks where a pullback was armed: in an uptrend and under the line for ${span(coin.pullback.dwell_minutes)} or more — a close back above the line there buys a pullback lot. It is drawn on charts up to 4h.` : ""} Each buy carries a badge saying who bought it: D the dip, C Mode C${coin.pullback ? ", P the pullback" : ""}, M you — with the trade's number.`}>
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
    <BnbCard data={data} compact />
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
