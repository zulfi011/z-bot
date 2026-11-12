import { useEffect, useMemo, useRef, useState } from "react";
import type { ChartPoint, EquityPoint, Marker, Num } from "./api";
import { label, n, pct, price, signedUsd, time, tone, usd } from "./format";
import { sourceOf } from "./sources";
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

type Layer = "average" | "zone" | "trend" | "quiet" | "pullback" | "trades";
const LAYERS_KEY = "chart-layers";
const readLayers = (): Record<Layer, boolean> => {
  const all = { average: true, zone: true, trend: true, quiet: true, pullback: true, trades: true };
  try { return { ...all, ...JSON.parse(localStorage.getItem(LAYERS_KEY) ?? "{}") }; } catch { return all; }
};

/** Width of an element in CSS pixels, kept current. */
function useWidth<T extends Element>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(entries => setWidth(entries[0].contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

type TradeView = {
  key: string; source: ReturnType<typeof sourceOf>; status: string; won: boolean; open: boolean;
  pnl: Num | null; exitLabel: string; entryTime: string; exitTime: string | null; entryPrice: Num; exitPrice: Num | null;
  entry: { x: number; y: number }; exit: { x: number; y: number } | null; end: { x: number; y: number };
  entryShown: boolean; exitShown: boolean;
};
type Dot = { kind: "buy" | "sell"; x: number; y: number; trade: TradeView };
type Group = { kind: "buy" | "sell"; x: number; y: number; trades: TradeView[] };

/** The whole period as a thin line, with the visible window: drag it to move, drag its edges to zoom. */
function Overview({ points, view, onChange }:
  { points: ChartPoint[]; view: { from: number; to: number }; onChange: (next: { from: number; to: number }, instant?: boolean) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{ mode: "move" | "left" | "right"; x: number; view: { from: number; to: number } } | null>(null);
  const count = points.length - 1;
  const closes = points.map(point => n(point.close));
  const low = Math.min(...closes), high = Math.max(...closes);
  const line = closes.map((value, index) => `${index / Math.max(count, 1) * 1000},${36 - (value - low) / Math.max(high - low, 1e-9) * 30 - 3}`).join(" ");
  const left = view.from / Math.max(count, 1) * 100, right = view.to / Math.max(count, 1) * 100;
  const indexAt = (clientX: number) => {
    const rect = box.current!.getBoundingClientRect();
    return Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1) * count;
  };
  return <div className="overview" ref={box}
    onPointerDown={event => {
      const at = indexAt(event.clientX), edge = (view.to - view.from) * 0.12 + count * 0.008;
      const mode = Math.abs(at - view.from) < edge ? "left" : Math.abs(at - view.to) < edge ? "right"
        : at > view.from && at < view.to ? "move" : null;
      if (!mode) { const span = view.to - view.from; onChange({ from: at - span / 2, to: at + span / 2 }); return; }
      event.currentTarget.setPointerCapture(event.pointerId);
      drag.current = { mode, x: event.clientX, view };
    }}
    onPointerMove={event => {
      const d = drag.current; if (!d) return;
      const rect = box.current!.getBoundingClientRect();
      const shift = (event.clientX - d.x) / rect.width * count;
      const next = d.mode === "move" ? { from: d.view.from + shift, to: d.view.to + shift }
        : d.mode === "left" ? { from: Math.min(d.view.from + shift, d.view.to - 6), to: d.view.to }
          : { from: d.view.from, to: Math.max(d.view.to + shift, d.view.from + 6) };
      onChange(next, true);
    }}
    onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
    role="slider" aria-label="Visible part of the chart: drag to move, drag the edges to zoom"
    aria-valuemin={0} aria-valuemax={count} aria-valuenow={Math.round(view.from)}>
    <svg viewBox="0 0 1000 36" preserveAspectRatio="none" aria-hidden="true"><polyline points={line} /></svg>
    <i className="overview-shade" style={{ left: 0, width: `${left}%` }} />
    <i className="overview-shade" style={{ left: `${right}%`, right: 0 }} />
    <span className="overview-window" style={{ left: `${left}%`, width: `${Math.max(right - left, 1)}%` }}><b /><b /></span>
  </div>;
}

/** The card shown for a marker: every trade at that spot, in plain words. */
function TradeCard({ group, points, onClose }: { group: Group & { left: number; top: number; below: boolean }; points: ChartPoint[]; onClose: () => void }) {
  const latest = points.at(-1);
  return <div className={`trade-card ${group.below ? "below" : ""}`} style={{ left: `${group.left}%`, top: group.top }} role="dialog"
    aria-label="Trade details" onPointerDown={event => event.stopPropagation()}>
    <button type="button" className="trade-card-close" aria-label="Close" onClick={onClose}>✕</button>
    {group.trades.map(trade => {
      const nowPct = trade.open && latest ? (n(latest.close) / n(trade.entryPrice) - 1) * 100 : null;
      return <div key={trade.key} className="trade-card-row">
        <b><i className={`src-swatch ${trade.source.cls}`}>{trade.source.letter}</i>{trade.source.name} <span className="arrow">→</span> {trade.open ? "still open" : trade.exitLabel}</b>
        <small>Bought {time(trade.entryTime, true)} at {price(trade.entryPrice)}</small>
        {trade.exitTime && <small>Sold {time(trade.exitTime, true)} at {price(trade.exitPrice)}</small>}
        <span className={trade.open ? tone(nowPct) : trade.won ? "up" : "down"}>
          {trade.open ? `now ${price(latest?.close)} (${pct(nowPct)})` : signedUsd(trade.pnl)}</span>
      </div>;
    })}
  </div>;
}

export function PriceChart({ coin, points, markers, zonePct, averageDays, mode, trendHours, zoneHours, pullbackHours,
  pullbackDwell, height = 250 }:
  { coin: string; points: ChartPoint[]; markers: Marker[]; zonePct: number; averageDays: number;
    mode: "line" | "candles"; trendHours?: number | null; zoneHours?: number | null; pullbackHours?: number | null;
    pullbackDwell?: number | null; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const [layers, setLayers] = useState(readLayers);
  const [picked, setPicked] = useState<string | null>(null);
  const [frame, seen] = useSeen<HTMLDivElement>();
  const [stage, stageWidth] = useWidth<HTMLDivElement>();
  const toggle = (layer: Layer) => setLayers(current => {
    const next = { ...current, [layer]: !current[layer] };
    try { localStorage.setItem(LAYERS_KEY, JSON.stringify(next)); } catch { /* ignore */ }
    return next;
  });
  // Pinch or wheel to zoom, drag or swipe to look back, double-tap to see everything again.
  const { ref, view, zoomed, reset, handlers, zoomAt, setRange } = useChartView(points.length, fraction =>
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
      ...(point.trend_line == null || !layers.trend ? [] : [n(point.trend_line)]),
      ...(point.pullback_line == null || !layers.pullback ? [] : [n(point.pullback_line)]),
      ...(point.zone_top == null || !layers.quiet ? [] : [n(point.zone_top), n(point.zone_bottom)]),
      ...(point.signal_average == null || !(layers.average || layers.zone) ? [] : [n(point.signal_average) * (1 - zone), n(point.signal_average) * (1 + zone)])]);
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
    // The quiet band, drawn only where the price really was consolidating.
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
    const latest = { x: x(points.length - 1), y: y(n(points.at(-1)!.close)) };
    const trades: TradeView[] = markers.map(marker => {
      const open = marker.status === "open" || !marker.exit_time;
      const entry = { x: xTime(marker.entry_time), y: y(n(marker.entry_fill_price)) };
      const exit = marker.exit_time ? { x: xTime(marker.exit_time), y: y(n(marker.exit_fill_price)) } : null;
      return {
        key: marker.position_id, source: sourceOf(marker.entry_source), status: marker.status, open,
        won: !open && n(marker.realized_pnl_usd) >= 0, pnl: marker.realized_pnl_usd,
        exitLabel: label(marker.exit_reason ?? ""), entryTime: marker.entry_time, exitTime: marker.exit_time,
        entryPrice: marker.entry_fill_price, exitPrice: marker.exit_fill_price,
        entry, exit, end: exit ?? latest, entryShown: inRange(marker.entry_time), exitShown: !!exit && inRange(marker.exit_time),
      };
    // A trade is drawn when any part of it overlaps the view.
    }).filter(trade => !(trade.end.x < -20 || trade.entry.x > W + 20));
    return { x, y, band, average, line, trend: polyline("trend_line"), pullback: polyline("pullback_line"),
             quiet, armed, trades, first, last, candle: Math.max(1.5, bucket * 0.6) };
  }, [points, markers, zonePct, height, view.from, view.to, layers]);

  // Trade lines close together on screen share one hover target (the card lists them all) until zoomed in.
  const groups = useMemo(() => {
    if (!chart || !layers.trades) return [] as (Group & { left: number })[];
    const toPx = (value: number) => value / W * (stageWidth || 800);
    const dots: Dot[] = chart.trades.flatMap(trade => [
      ...(trade.entryShown ? [{ kind: "buy" as const, x: trade.entry.x, y: trade.entry.y, trade }] : []),
      ...(trade.exitShown && trade.exit ? [{ kind: "sell" as const, x: trade.exit.x, y: trade.exit.y, trade }] : []),
    ]).sort((a, b) => a.x - b.x);
    const out: Group[] = [];
    for (const dot of dots) {
      const near = out.find(group => group.kind === dot.kind && Math.abs(toPx(group.x) - toPx(dot.x)) < 10);
      if (near) near.trades.push(dot.trade);
      else out.push({ kind: dot.kind, x: dot.x, y: dot.y, trades: [dot.trade] });
    }
    return out.map(group => ({ ...group, left: group.x / W * 100 }));
  }, [chart, layers.trades, stageWidth]);

  if (!chart) return <div className="chart-empty">Waiting for price data…</div>;
  const active = hover == null ? null : points[hover];
  const last = points.at(-1)!;
  const range = `${time(points[chart.first].open_time, true)} → ${time(points[chart.last].open_time, true)}`;
  const pickedGroup = groups.find(group => `${group.kind}-${group.trades[0].key}` === picked);
  const pickedKeys = new Set(pickedGroup?.trades.map(trade => trade.key) ?? []);
  // A new interval (different first candle or length) fades in instead of snapping.
  const series = `${points[0].open_time}-${points.length}-${mode}`;
  const chips: { layer: Layer; label: string; cls: string; show: boolean }[] = [
    { layer: "average", label: `${averageDays}-day average`, cls: "lg-avg", show: true },
    { layer: "zone", label: `±${zonePct}% entry zone`, cls: "lg-zone", show: true },
    { layer: "trend", label: `${trendHours}h trend line`, cls: "lg-trend", show: !!chart.trend },
    { layer: "quiet", label: `${zoneHours}h quiet band`, cls: "lg-quiet", show: chart.quiet.length > 0 || !!zoneHours },
    { layer: "pullback", label: `${pullbackHours}h pullback line`, cls: "lg-pull", show: !!chart.pullback },
    { layer: "trades", label: "Trades", cls: "lg-trades", show: markers.length > 0 },
  ];
  return <div className={`chart price-chart ${seen ? "in-view" : "waiting"}`} ref={frame}>
    <div className="chart-stage" style={{ height }} ref={stage} onPointerDown={() => setPicked(null)}>
      <svg key={series} ref={ref} viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" style={{ height }} {...handlers}
        aria-label={`${coin} price with the ${averageDays}-day average and ±${zonePct}% entry zone. Pinch or scroll to zoom, drag to move.`}>
        {layers.pullback && chart.armed.map((span, index) => <rect key={`armed-${index}`} className="pullback-armed"
          x={span.left} width={Math.max(1, span.right - span.left)} y={0} height={height} />)}
        {layers.zone && chart.band && <polygon points={chart.band} className="zone-band" />}
        {layers.quiet && chart.quiet.map((box, index) => <polygon key={index} points={box} className="quiet-band" />)}
        <g className="price-series">
          {mode === "line" ? <polyline points={chart.line} className="price-line" /> : points.map((point, index) => {
            if (index < chart.first - 1 || index > chart.last + 1) return null;
            const up = n(point.close) >= n(point.open), cx = chart.x(index);
            const top = chart.y(Math.max(n(point.open), n(point.close))), bottom = chart.y(Math.min(n(point.open), n(point.close)));
            return <g key={point.open_time} className={up ? "candle up" : "candle down"}>
              <line x1={cx} x2={cx} y1={chart.y(n(point.high))} y2={chart.y(n(point.low))} />
              <rect x={cx - chart.candle / 2} width={chart.candle} y={top} height={Math.max(1, bottom - top)} />
            </g>;
          })}
        </g>
        {layers.average && chart.average && <polyline points={chart.average} className="average-line" />}
        {layers.pullback && chart.pullback && <polyline points={chart.pullback} className="pullback-line" />}
        {layers.trend && chart.trend && <polyline points={chart.trend} className="trend-line" />}
        {/* Each trade: a solid line where it was bought (its way-in colour), a dashed line where it was sold
            (green win, red loss). No numbers: hover or tap a line for the details. */}
        {layers.trades && chart.trades.map(trade => <g key={trade.key} className={`trade-mark ${trade.source.cls} ${pickedKeys.has(trade.key) ? "picked" : ""}`}>
          {trade.entryShown && <line className="trade-open" x1={trade.entry.x} x2={trade.entry.x} y1={0} y2={height} />}
          {trade.exitShown && trade.exit && <line className={`trade-close ${trade.won ? "won" : "lost"}`} x1={trade.exit.x} x2={trade.exit.x} y1={0} y2={height} />}
        </g>)}
        {hover != null && <line className="crosshair" x1={chart.x(hover)} x2={chart.x(hover)} y1={0} y2={height} />}
      </svg>
      {/* Invisible, finger-wide strips over each trade line: hover or tap one to see the trade. */}
      <div className="chart-marks">
        {groups.map(group => {
          const id = `${group.kind}-${group.trades[0].key}`;
          return <button key={id} type="button" className={`trade-hit ${picked === id ? "picked" : ""}`}
            style={{ left: `${group.left}%` }}
            aria-label={`${group.trades.length} trade${group.trades.length === 1 ? "" : "s"} ${group.kind === "buy" ? "bought" : "sold"} here`}
            onPointerDown={event => event.stopPropagation()}
            onMouseEnter={() => matchMedia("(hover: hover)").matches && setPicked(id)}
            onMouseLeave={() => matchMedia("(hover: hover)").matches && setPicked(current => current === id ? null : current)}
            onClick={() => setPicked(current => current === id ? null : id)} />;
        })}
      </div>
      {pickedGroup && <TradeCard points={points} onClose={() => setPicked(null)}
        group={{ ...pickedGroup, left: Math.min(Math.max(pickedGroup.left, 14), 86), top: 8, below: true }} />}
      <ChartZoom zoomed={zoomed} onZoom={zoomAt} onReset={reset} anchor={view.to >= points.length - 1.5 ? 1 : 0.5} />
    </div>
    <Overview points={points} view={view} onChange={setRange} />
    <div className="chart-readout">
      {active ? <>
        <span>{time(active.open_time, true)}</span><b>{price(active.close)}</b>
        <span>H {price(active.high)} · L {price(active.low)}</span>
        {active.signal_average != null && <span className="avg">{averageDays}D {price(active.signal_average)}</span>}
        {active.trend_line != null && layers.trend && <span className="trend">Trend {price(active.trend_line)}</span>}
        {active.pullback_line != null && layers.pullback && <span className="pull">Pullback line {price(active.pullback_line)}</span>}
        {active.pullback_armed && <span className="pull"><b className="pull">armed</b></span>}
        {active.zone_top != null && layers.quiet && <span className="quiet">Quiet {price(active.zone_bottom)}–{price(active.zone_top)}</span>}
      </> : <>
        <span>Latest</span><b>{price(last.close)}</b>
        {last.signal_average != null && <span className="avg">{averageDays}D avg {price(last.signal_average)}</span>}
        <span className="muted">{zoomed ? range : "Hover a marker for its trade · scroll, pinch or drag the strip to zoom"}</span>
      </>}
    </div>
    <div className="layer-chips" role="group" aria-label="Show or hide chart layers">
      {chips.filter(chip => chip.show).map(chip => <button key={chip.layer} type="button" aria-pressed={layers[chip.layer]}
        className={`layer-chip ${layers[chip.layer] ? "on" : ""}`} onClick={() => toggle(chip.layer)}>
        <i className={chip.cls} />{chip.label}</button>)}
      {pullbackDwell && layers.pullback && chart.armed.length > 0
        ? <span className="layer-note"><i className="lg-armed" />pullback armed ({pullbackDwell / 60}h+ under the line)</span> : null}
    </div>
  </div>;
}

/** Zoom buttons, for when a mouse wheel or two fingers are not to hand. */
function ChartZoom({ zoomed, onZoom, onReset, anchor = 0.5 }:
  { zoomed: boolean; onZoom: (factor: number, anchor: number) => void; onReset: () => void; anchor?: number }) {
  return <div className="chart-zoom">
    <button type="button" aria-label="Zoom in" onClick={() => onZoom(1 / 1.6, anchor)}>+</button>
    <button type="button" aria-label="Zoom out" onClick={() => onZoom(1.6, anchor)}>−</button>
    {zoomed && <button type="button" className="reset" onClick={onReset}>Fit</button>}
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
      <ChartZoom zoomed={zoomed} onZoom={zoomAt} onReset={reset} anchor={window.to >= points.length - 1.5 ? 1 : 0.5} />
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
