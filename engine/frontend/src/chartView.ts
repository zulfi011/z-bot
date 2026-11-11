import { useCallback, useEffect, useRef, useState } from "react";

/** The slice of a chart that is on screen, as fractional positions in the data (0 … count-1). */
export type View = { from: number; to: number };

const MIN_POINTS = 6;          // never zoom in past a handful of candles
const WHEEL_STEP = 1.2;

const clamp = (view: View, count: number): View => {
  const last = Math.max(count - 1, 1);
  const span = Math.min(Math.max(view.to - view.from, Math.min(MIN_POINTS, last)), last);
  let from = Math.min(Math.max(view.from, 0), last - span);
  return { from, to: from + span };
};

/** Pan and zoom for a chart drawn across the full width of an SVG.
 *
 * Mouse: wheel zooms at the cursor, drag pans, double-click resets, moving without a button shows the crosshair.
 * Touch: one finger drags sideways to pan, two fingers pinch to zoom, double-tap resets. The element keeps
 * `touch-action: pan-y`, so the page still scrolls vertically over the chart.
 */
export function useChartView(count: number, onHover?: (fraction: number | null) => void) {
  const ref = useRef<SVGSVGElement | null>(null);
  const [view, setView] = useState<View | null>(null);
  const live = useRef<View>({ from: 0, to: Math.max(count - 1, 1) });
  const pointers = useRef(new Map<number, number>());
  const drag = useRef<{ x: number; view: View; moved: boolean } | null>(null);
  const pinch = useRef<{ distance: number; view: View; anchor: number } | null>(null);
  const tap = useRef(0);
  // A running glide (buttons, wheel, Fit, overview strip) and where it is heading.
  const anim = useRef<number | null>(null);
  const target = useRef<View | null>(null);

  const full: View = { from: 0, to: Math.max(count - 1, 1) };
  const current = view ? clamp(view, count) : full;
  live.current = current;
  const zoomed = view != null && (current.from > 0.5 || current.to < full.to - 0.5);

  const stop = () => { if (anim.current != null) cancelAnimationFrame(anim.current); anim.current = null; target.current = null; };
  /** Glide to a view in ~240 ms (ease-out), or jump when the viewer prefers reduced motion. */
  const animateTo = useCallback((next: View, done?: () => void) => {
    const goal = clamp(next, count);
    const reduce = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (anim.current != null) cancelAnimationFrame(anim.current);
    if (reduce) { anim.current = null; target.current = null; setView(goal); done?.(); return; }
    const from = live.current, start = performance.now();
    target.current = goal;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / 240), e = 1 - Math.pow(1 - t, 3);
      setView({ from: from.from + (goal.from - from.from) * e, to: from.to + (goal.to - from.to) * e });
      if (t < 1) anim.current = requestAnimationFrame(step);
      else { anim.current = null; target.current = null; done?.(); }
    };
    anim.current = requestAnimationFrame(step);
  }, [count]);
  useEffect(() => () => { if (anim.current != null) cancelAnimationFrame(anim.current); }, []);

  const reset = useCallback(() => {
    animateTo({ from: 0, to: Math.max(count - 1, 1) }, () => setView(null));
  }, [animateTo, count]);
  const fractionOf = (clientX: number) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box || !box.width) return 0;
    return Math.min(Math.max((clientX - box.left) / box.width, 0), 1);
  };
  const zoomAt = useCallback((factor: number, anchor: number) => {
    // Build on where a running glide is heading, so quick wheel ticks add up smoothly.
    const view = target.current ?? live.current;
    const span = view.to - view.from;
    const middle = view.from + anchor * span;
    animateTo({ from: middle - anchor * span * factor, to: middle + (1 - anchor) * span * factor });
  }, [animateTo]);
  /** Show exactly this range (used by the overview strip); glides unless `instant`. */
  const setRange = useCallback((next: View, instant = false) => {
    if (instant) { stop(); setView(clamp(next, count)); } else animateTo(next);
  }, [animateTo, count]);

  // The wheel listener has to be non-passive to stop the page scrolling while the chart zooms.
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.deltaY) return;
      event.preventDefault();
      zoomAt(event.deltaY > 0 ? WHEEL_STEP : 1 / WHEEL_STEP, fractionOf(event.clientX));
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const handlers = {
    onPointerDown: (event: React.PointerEvent<SVGSVGElement>) => {
      stop();
      pointers.current.set(event.pointerId, event.clientX);
      event.currentTarget.setPointerCapture?.(event.pointerId);
      if (pointers.current.size === 2) {
        const [a, b] = [...pointers.current.values()];
        pinch.current = { distance: Math.max(Math.abs(a - b), 1), view: live.current,
                          anchor: fractionOf((a + b) / 2) };
        drag.current = null;
        return;
      }
      drag.current = { x: event.clientX, view: live.current, moved: false };
      onHover?.(fractionOf(event.clientX));
    },
    onPointerMove: (event: React.PointerEvent<SVGSVGElement>) => {
      if (pointers.current.has(event.pointerId)) pointers.current.set(event.pointerId, event.clientX);
      if (pinch.current && pointers.current.size >= 2) {
        const [a, b] = [...pointers.current.values()];
        const distance = Math.max(Math.abs(a - b), 1);
        const start = pinch.current;
        const span = (start.view.to - start.view.from) * (start.distance / distance);
        const middle = start.view.from + start.anchor * (start.view.to - start.view.from);
        setView(clamp({ from: middle - start.anchor * span, to: middle + (1 - start.anchor) * span }, count));
        return;
      }
      if (drag.current && event.buttons !== 0) {
        const box = ref.current?.getBoundingClientRect();
        const moved = event.clientX - drag.current.x;
        if (Math.abs(moved) > 3) drag.current.moved = true;
        if (box?.width) {
          const span = drag.current.view.to - drag.current.view.from;
          const shift = (moved / box.width) * span;
          setView(clamp({ from: drag.current.view.from - shift, to: drag.current.view.to - shift }, count));
        }
        return;
      }
      onHover?.(fractionOf(event.clientX));
    },
    onPointerUp: (event: React.PointerEvent<SVGSVGElement>) => {
      pointers.current.delete(event.pointerId);
      if (pointers.current.size < 2) pinch.current = null;
      // A double tap (or double click) puts the whole chart back.
      if (drag.current && !drag.current.moved) {
        const now = Date.now();
        if (now - tap.current < 320) reset();
        tap.current = now;
      }
      drag.current = null;
    },
    onPointerCancel: (event: React.PointerEvent<SVGSVGElement>) => {
      pointers.current.delete(event.pointerId);
      pinch.current = null;
      drag.current = null;
    },
    onPointerLeave: () => { onHover?.(null); },
    onDoubleClick: () => reset(),
  };

  return { ref, view: current, full, zoomed, reset, handlers, fractionOf, zoomAt, setRange };
}
