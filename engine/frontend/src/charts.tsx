import { useEffect, useMemo, useRef, useState } from "react";
import type { ChartPoint, EquityPoint, Marker } from "./api";
import { n, pct, price, signedUsd, time, usd } from "./format";
import { SOURCE, sourceOf } from "./sources";
import { useChartView } from "./chartView";

const W = 1000;

/** Consecutive chart buckets where `on` holds, as [first, last] index pairs. */
function runs(points: ChartPoint[], on: (point: ChartPoint) => boolean): [number, number][] {
  const found: [number, number][] = [];
  let first: number | null = null;
  points.forEach((point, index) => {
    if (on(point)) { if (first == null) first = index; }
    else if (first != null) { found.push([first, index - 1]); first = null; }
  });
  if (first != null) found.push([first, points.length - 1]);
  return found;
}

export function PriceChart({ coin, points, markers, zonePct, averageDays, mode, trendHours, zoneHours, pullbackHours,
  pullbackDwell, height = 250 }:
  { coin: string; points: ChartPoint[]; markers: Marker[]; zonePct: number; averageDays: number;
    mode: "line" | "candles"; trendHours?: number | null; zoneHours?: number | null; pullbackHours?: number | null;
    pullbackDwell?: number | null; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  // Pinch or wheel to zoom, drag or swipe to look back, double-tap to see everything again.
  const { ref, view, zoomed, reset, handlers, zoomAt } = useChartView(points.length, fraction =>
    setHover(fraction == null ? null
      : Math.round(Math.min(Math.max(view.from + fraction * (view.to - view.from), 0), points.length - 1))));
  const chart = useMemo(() => {
    if (points.length < 2) return null;
    const zone = zonePct / 100;
    const span = Math.max(view.to - view.from, 1e-6);
    const first = Math.max(Math.floor(view.from), 0), last = Math.min(Math.ceil(view.to), points.length - 1);
    const shown = points.slice(first, last + 1);
    // The price scale follows what is on screen, so zooming in really does open the move up.
    const values = shown.flatMap(point => [n(point.low), n(point.high),
      ...(point.trend_line == null ? [] : [n(point.trend_line)]),
      ...(point.pullback_line == null ? [] : [n(point.pullback_line)]),
      ...(point.zone_top == null ? [] : [n(point.zone_top), n(point.zone_bottom)]),
      ...(point.signal_average == null ? [] : [n(point.signal_average) * (1 - zone), n(point.signal_average) * (1 + zone)])]);
    const low = Math.min(...values), high = Math.max(...values), pad = (high - low) * 0.08 || 1;
    const min = low - pad, max = high + pad;
    const x = (index: number) => (index - view.from) / span * W;
    const y = (value: number) => height - (value - min) / (max - min) * height;
    const start = new Date(points[0].open_time).getTime(), end = new Date(points.at(-1)!.open_time).getTime();
    const step = (end - start) / Math.max(points.length - 1, 1);
    const indexAt = (value: string) => (new Date(value).getTime() - start) / Math.max(step, 1);
    const xTime = (value: string) => x(indexAt(value));
    const bucket = W / Math.max(span, 1);
    const visible = (index: number) => index >= view.from - 1 && index <= view.to + 1;
    const withAverage = points.map((point, index) => ({ point, index }))
      .filter(item => item.point.signal_average != null && visible(item.index));
    const band = withAverage.length ? [
      ...withAverage.map(({ point, index }) => `${x(index)},${y(n(point.signal_average) * (1 + zone))}`),
      ...withAverage.slice().reverse().map(({ point, index }) => `${x(index)},${y(n(point.signal_average) * (1 - zone))}`),
    ].join(" ") : "";
    const average = withAverage.map(({ point, index }) => `${x(index)},${y(n(point.signal_average))}`).join(" ");
    const line = points.map((point, index) => ({ point, index })).filter(item => visible(item.index))
      .map(({ point, index }) => `${x(index)},${y(n(point.close))}`).join(" ");
    const runs = (on: (point: ChartPoint) => boolean) => {
      const found: [number, number][] = [];
      let runStart: number | null = null;
      points.forEach((point, index) => {
        if (on(point)) { if (runStart == null) runStart = index; }
        else if (runStart != null) { found.push([runStart, index - 1]); runStart = null; }
      });
      if (runStart != null) found.push([runStart, points.length - 1]);
      return found.filter(([a, b]) => b >= view.from - 1 && a <= view.to + 1);
    };
    // The Mode C band, drawn only where the price really was consolidating.
    const quiet = runs(point => point.zone_top != null).map(([a, b]) => {
      const part = points.slice(a, b + 1);
      const top = Math.min(...part.map(point => y(n(point.zone_top))));
      const bottom = Math.max(...part.map(point => y(n(point.zone_bottom))));
      return `${x(a) - bucket / 2},${top} ${x(b) + bucket / 2},${top} ${x(b) + bucket / 2},${bottom} ${x(a) - bucket / 2},${bottom}`;
    });
    // Where the pullback entry was loaded: in an uptrend and under its line for the full dwell.
    const armed = runs(point => point.pullback_armed === true)
      .map(([a, b]) => ({ left: x(a) - bucket / 2, right: x(b) + bucket / 2 }));
    const polyline = (key: "trend_line" | "pullback_line") => points.map((point, index) => ({ point, index }))
      .filter(item => item.point[key] != null && visible(item.index))
      .map(({ point, index }) => `${x(index)},${y(n(point[key]))}`).join(" ");
    const inRange = (value: string | null) => {
      if (!value) return false;
      const index = indexAt(value);
      return index >= view.from - 0.5 && index <= view.to + 0.5;
    };
    const trades = markers.map(marker => {
      const source = sourceOf(marker.entry_source);
      const rides = marker.trend_exit_active === true;
      const won = marker.status !== "open" && n(marker.realized_pnl_usd) >= 0;
      return {
        key: marker.position_id, number: marker.trade_number, source, status: marker.status,
        pnl: marker.realized_pnl_usd, rides, won, added: marker.parent_position_id != null,
        entry: inRange(marker.entry_time) ? { x: xTime(marker.entry_time), y: y(n(marker.entry_fill_price)) } : null,
        trail: inRange(marker.trailing_started_at) ? { x: xTime(marker.trailing_started_at!), y: y(n(marker.trailing_start_price)) } : null,
        exit: marker.exit_time && inRange(marker.exit_time) ? { x: xTime(marker.exit_time), y: y(n(marker.exit_fill_price)) } : null,
        text: `Trade ${marker.trade_number} · bought by ${source.long} · ${rides ? "rides the trend line" : "gives profit back"}: `
          + `bought ${time(marker.entry_time, true)} at ${price(marker.entry_fill_price)}`
          + (marker.trailing_started_at ? ` · trailing from ${time(marker.trailing_started_at)} at ${price(marker.trailing_start_price)}` : "")
          + (marker.exit_time ? ` · sold ${time(marker.exit_time, true)} at ${price(marker.exit_fill_price)} (${signedUsd(marker.realized_pnl_usd)})` : " · still open"),
      };
    }).filter(trade => trade.entry || trade.trail || trade.exit);
    return { x, y, band, average, line, trend: polyline("trend_line"), pullback: polyline("pullback_line"),
             quiet, armed, trades, first, last, shown,
             candle: Math.max(1.5, bucket * 0.6), min, max };
  }, [points, markers, zonePct, height, view.from, view.to]);

  if (!chart) return <div className="chart-empty">Waiting for price data…</div>;
  const active = hover == null ? null : points[hover];
  const last = points.at(-1)!;
  const sources = new Set(chart.trades.map(trade => trade.source.letter));
  const leftPct = (value: number) => `${value / W * 100}%`;
  const topPx = (value: number) => `${Math.max(9, Math.min(height - 9, value))}px`;
  const range = `${time(points[chart.first].open_time, true)} → ${time(points[chart.last].open_time, true)}`;
  return <div className="chart">
    <div className="chart-stage" style={{ height }}>
      <svg ref={ref} viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" style={{ height }} {...handlers}
        aria-label={`${coin} price with the ${averageDays}-day average and ±${zonePct}% entry zone. Pinch or scroll to zoom, drag to move.`}>
        {chart.armed.map((span, index) => <rect key={`armed-${index}`} className="pullback-armed"
          x={span.left} width={Math.max(1, span.right - span.left)} y={0} height={height} />)}
        {chart.band && <polygon points={chart.band} className="zone-band" />}
        {chart.quiet.map((box, index) => <polygon key={index} points={box} className="quiet-band" />)}
        {mode === "line" ? <polyline points={chart.line} className="price-line" /> : points.map((point, index) => {
          if (index < chart.first - 1 || index > chart.last + 1) return null;
          const up = n(point.close) >= n(point.open), cx = chart.x(index);
          const top = chart.y(Math.max(n(point.open), n(point.close))), bottom = chart.y(Math.min(n(point.open), n(point.close)));
          return <g key={point.open_time} className={up ? "candle up" : "candle down"}>
            <line x1={cx} x2={cx} y1={chart.y(n(point.high))} y2={chart.y(n(point.low))} />
            <rect x={cx - chart.candle / 2} width={chart.candle} y={top} height={Math.max(1, bottom - top)} />
          </g>;
        })}
        {chart.average && <polyline points={chart.average} className="average-line" />}
        {chart.pullback && <polyline points={chart.pullback} className="pullback-line" />}
        {chart.trend && <polyline points={chart.trend} className="trend-line" />}
        {chart.trades.map(trade => <g key={trade.key} className={`trade-mark ${trade.source.cls}`}>
          <title>{trade.text}</title>
          {trade.entry && <line className="trade-open" x1={trade.entry.x} x2={trade.entry.x} y1={0} y2={height} />}
          {trade.trail && <line className="trade-trail" x1={trade.trail.x - 16} x2={trade.trail.x + 16} y1={trade.trail.y} y2={trade.trail.y} />}
          {trade.exit && <line className="trade-close" x1={trade.exit.x} x2={trade.exit.x} y1={0} y2={height} />}
        </g>)}
        {hover != null && <line className="crosshair" x1={chart.x(hover)} x2={chart.x(hover)} y1={0} y2={height} />}
      </svg>
      {/* Badges live in HTML, not the stretched SVG, so they stay round and readable at any width. */}
      <div className="chart-badges" aria-hidden="true">
        {chart.trades.map(trade => <span key={trade.key}>
          {trade.entry && <i className={`buy-badge ${trade.source.cls}`} title={trade.text}
            style={{ left: leftPct(trade.entry.x), top: topPx(trade.entry.y) }}>{trade.source.letter}{trade.number}</i>}
          {trade.exit && <i className={`sell-dot ${trade.source.cls} ${trade.won ? "won" : "lost"}`} title={trade.text}
            style={{ left: leftPct(trade.exit.x), top: topPx(trade.exit.y) }} />}
        </span>)}
      </div>
      <ChartZoom zoomed={zoomed} onZoom={zoomAt} onReset={reset} />
    </div>
    <div className="chart-readout">
      {active ? <>
        <span>{time(active.open_time, true)}</span><b>{price(active.close)}</b>
        <span>H {price(active.high)} · L {price(active.low)}</span>
        {active.signal_average != null && <span className="avg">{averageDays}D {price(active.signal_average)}</span>}
        {active.trend_line != null && <span className="trend">Trend {price(active.trend_line)}</span>}
        {active.pullback_line != null && <span className="pull">Pullback line {price(active.pullback_line)}</span>}
        {active.pullback_armed && <span className="pull"><b className="pull">armed</b></span>}
        {active.zone_top != null && <span className="quiet">Quiet {price(active.zone_bottom)}–{price(active.zone_top)}</span>}
      </> : <>
        <span>Latest</span><b>{price(last.close)}</b>
        {last.signal_average != null && <span className="avg">{averageDays}D avg {price(last.signal_average)}</span>}
        {last.trend_line != null && <span className="trend">Trend line {price(last.trend_line)}</span>}
        {last.pullback_line != null && <span className="pull">Pullback line {price(last.pullback_line)}</span>}
        <span className="muted">{zoomed ? range : "Touch or hover to inspect · pinch or scroll to zoom"}</span>
      </>}
    </div>
    <div className="chart-foot">
      <div className="trade-legend">
        {chart.trades.length ? chart.trades.map(trade => <span key={trade.key} title={trade.text}>
          <i className={`src-swatch ${trade.source.cls}`}>{trade.source.letter}{trade.number}</i>{trade.source.name}
          {trendHours ? <em className={trade.rides ? "mode-a" : "mode-b"}>{trade.rides ? "rides" : "gives back"}</em> : null}
          <small className={trade.status === "open" ? "" : trade.won ? "up" : "down"}>{trade.status === "open" ? "open" : signedUsd(trade.pnl)}</small>
        </span>) : <span className="muted">No trades in this view</span>}
      </div>
      <div className="legend"><span><i className="lg-price" />{coin}</span><span><i className="lg-avg" />{averageDays}-day average</span>
        <span><i className="lg-zone" />±{zonePct}% entry zone</span>
        {chart.trend && <span><i className="lg-trend" />{trendHours}-hour trend line</span>}
        {chart.quiet.length > 0 && <span><i className="lg-quiet" />{zoneHours}-hour quiet band (Mode C)</span>}
        {chart.pullback && <span><i className="lg-pull" />{pullbackHours}-hour pullback line</span>}
        {chart.armed.length > 0 && <span><i className="lg-armed" />pullback armed{pullbackDwell ? ` (${pullbackDwell / 60}h+ below the line)` : ""}</span>}</div>
    </div>
    {chart.trades.length > 0 && <p className="chart-key">
      {(["D", "C", "P", "+", "M"] as const).filter(letter => sources.has(letter)).map(letter => {
        const source = Object.values(SOURCE).find(item => item.letter === letter)!;
        return <span key={letter} className="key-source"><i className={`src-swatch ${source.cls}`}>{letter}</i>{source.name}</span>;
      })}
      <span className="key-sep" /> <span className="key-open" /> bought · <span className="key-trail" /> trailing started ·
      <span className="key-close" /> sold · <i className="sell-dot won key-dot" /> win · <i className="sell-dot lost key-dot" /> loss</p>}
  </div>;
}

/** Zoom buttons, for when a mouse wheel or two fingers are not to hand. */
function ChartZoom({ zoomed, onZoom, onReset }:
  { zoomed: boolean; onZoom: (factor: number, anchor: number) => void; onReset: () => void }) {
  return <div className="chart-zoom">
    <button type="button" aria-label="Zoom in" onClick={() => onZoom(1 / 1.6, 0.5)}>+</button>
    <button type="button" aria-label="Zoom out" onClick={() => onZoom(1.6, 0.5)}>−</button>
    {zoomed && <button type="button" className="reset" onClick={onReset}>Reset</button>}
  </div>;
}

/** True once the element has scrolled into view (and stays true), so an entrance animation plays where it is seen. */
function useSeen<T extends Element>() {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element || seen) return;
    if (typeof IntersectionObserver === "undefined") { setSeen(true); return; }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { setSeen(true); observer.disconnect(); }
    }, { threshold: 0.35 });
    observer.observe(element);
    return () => observer.disconnect();
  });
  return [ref, seen] as const;
}

export function EquityChart({ points, view, start, end, height = 200 }:
  { points: EquityPoint[]; view: "value" | "performance"; start?: string; end?: string; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const [frame, seen] = useSeen<HTMLDivElement>();
  const { ref, view: window, zoomed, reset, handlers, zoomAt } = useChartView(points.length, fraction =>
    setHover(fraction == null ? null
      : Math.round(Math.min(Math.max(window.from + fraction * (window.to - window.from), 0), points.length - 1))));
  const series = useMemo(() => points.map(point => view === "value" ? n(point.wallet_value_usd) : n(point.strategy_pnl_usd)), [points, view]);
  // "Trading only" is profit since the bot started, so its baseline is zero.
  const initial = view === "value" ? n(points.at(-1)?.wallet_value_usd) : 0;
  if (points.length < 2) return <div className="chart-empty equity-empty">
    <svg viewBox="0 0 120 40" aria-hidden="true"><path d="M4 32 C 24 32, 30 18, 48 20 S 76 30, 92 14 S 112 8, 116 8" /></svg>
    <b>No history yet</b><span>The chart starts when the bot does. Every minute adds a point.</span></div>;
  const first = Math.max(Math.floor(window.from), 0), last = Math.min(Math.ceil(window.to), points.length - 1);
  const shown = series.slice(first, last + 1);
  // Points sit at their real time across the range picked, so 7D and 1M look different even with little history.
  const times = points.map(point => new Date(point.timestamp).getTime());
  const from = start ? Math.min(new Date(start).getTime(), times[0]) : times[0];
  const to = end ? Math.max(new Date(end).getTime(), times.at(-1)!) : times.at(-1)!;
  const span = Math.max(to - from, 1);
  // Zoomed, the visible window is the slice of points on screen rather than the whole period.
  const left = zoomed ? times[first] : from, right = zoomed ? times[last] : to;
  const width = Math.max(right - left, 1);
  const x = (index: number) => (times[index] - left) / width * W;
  const low = Math.min(...shown, view === "performance" ? 0 : Infinity);
  const high = Math.max(...shown, view === "performance" ? 0 : -Infinity);
  // Never stretch a few cents across the whole chart: the visible range is at least 2% of the wallet (or $2 for
  // trading P&L), so a fee looks like a fee and not like a crash.
  const floor = view === "value" ? Math.max(2, Math.abs(initial) * 0.02) : 2;
  const spread = Math.max(high - low, floor), middle = (high + low) / 2;
  const pad = spread * 0.12, min = middle - spread / 2 - pad, max = middle + spread / 2 + pad;
  const y = (value: number) => height - (value - min) / (max - min) * height;
  const visible = points.map((_, index) => index).filter(index => index >= first - 1 && index <= last + 1);
  const line = visible.map(index => `${x(index)},${y(series[index])}`).join(" ");
  const edgeLeft = x(visible[0]), edgeRight = x(visible.at(-1)!);
  const active = hover == null ? null : points[hover];
  const rising = shown.at(-1)! >= shown[0];
  const tick = (at: number) => width <= 2 * 86400000
    ? new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", hour: "2-digit", minute: "2-digit", hour12: false }).format(at)
    : new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "numeric", month: "short" }).format(at);
  const tone = rising ? "up" : "down";
  // Dots are drawn in HTML over the stretched SVG so they stay round; positions are in % of the width.
  const dot = (index: number) => ({ left: `${x(index) / W * 100}%`, top: `${y(series[index])}px` });
  return <div ref={frame} className={`chart equity-chart ${seen ? "in-view" : "waiting"}`}>
    <div className="chart-stage" style={{ height }}>
      {/* A new key on view or range change replays the draw-in animation; the minute refresh does not. */}
      <svg key={`${view}-${start ?? ""}`} ref={ref} viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" style={{ height }} {...handlers}
        aria-label="Account value history. Pinch or scroll to zoom, drag to move.">
        <defs>
          <linearGradient id={`equity-fill-${tone}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" className={`equity-stop-top ${tone}`} />
            <stop offset="100%" className={`equity-stop-bottom ${tone}`} />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map(at => <line key={at} className="equity-grid" x1={0} x2={W} y1={height * at} y2={height * at} />)}
        {view === "performance" && <line className="baseline" x1={0} x2={W} y1={y(0)} y2={y(0)} />}
        <polygon points={`${edgeLeft},${height} ${line} ${edgeRight},${height}`} className="equity-area"
          fill={`url(#equity-fill-${tone})`} />
        <polyline points={line} pathLength={1} className={`equity-line ${tone}`} />
        {hover != null && <line className="crosshair" x1={x(hover)} x2={x(hover)} y1={0} y2={height} />}
      </svg>
      {hover != null && <span className={`equity-dot ${tone}`} style={dot(hover)} aria-hidden="true" />}
      <ChartZoom zoomed={zoomed} onZoom={zoomAt} onReset={reset} />
    </div>
    <div className="chart-axis" aria-hidden="true">
      <span>{tick(left)}</span><span>{tick(left + width / 2)}</span><span>{tick(right)}</span>
    </div>
    <div className="chart-readout">
      {active ? <>
        <span>{time(active.timestamp, true)}</span>
        <b>{usd(view === "value" ? active.wallet_value_usd : active.strategy_pnl_usd)}</b>
        <span>Trading P&amp;L {signedUsd(active.strategy_pnl_usd)}</span><span>Coins {usd(active.positions_usd)}</span>
      </> : <span className="muted">{zoomed ? "Double-tap to zoom out" : "Hover or touch the chart to see any moment"}</span>}
    </div>
  </div>;
}
