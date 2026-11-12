import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

type Placement = { top: number; left: number; above: boolean };

function useBubble(open: boolean, anchor: React.RefObject<HTMLElement | null>) {
  const [place, setPlace] = useState<Placement | null>(null);
  useLayoutEffect(() => {
    if (!open || !anchor.current) { setPlace(null); return; }
    const update = () => {
      const rect = anchor.current!.getBoundingClientRect();
      const width = Math.min(280, window.innerWidth - 24);
      const left = Math.max(12, Math.min(window.innerWidth - width - 12, rect.left + rect.width / 2 - width / 2));
      const above = rect.bottom + 150 > window.innerHeight && rect.top > 160;
      setPlace({ top: above ? rect.top - 8 : rect.bottom + 8, left, above });
    };
    update();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => { window.removeEventListener("scroll", update, true); window.removeEventListener("resize", update); };
  }, [open, anchor]);
  return place;
}

function Bubble({ text, place }: { text: ReactNode; place: Placement | null }) {
  if (!place) return null;
  return createPortal(
    <div role="tooltip" className={`bubble ${place.above ? "above" : ""}`}
      style={{ top: place.top, left: place.left, width: Math.min(280, window.innerWidth - 24) }}>{text}</div>,
    document.body,
  );
}

/** ⓘ explanation: hover on desktop, tap on phones. */
export function Info({ text, label = "What does this mean?" }: { text: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLButtonElement>(null);
  const place = useBubble(open, ref);
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  return <>
    <button ref={ref} type="button" className="info" aria-label={label} aria-expanded={open}
      onClick={event => { event.stopPropagation(); setOpen(value => !value); }}
      onMouseEnter={() => matchMedia("(hover: hover)").matches && setOpen(true)}
      onMouseLeave={() => matchMedia("(hover: hover)").matches && setOpen(false)}>i</button>
    {open && <Bubble text={text} place={place} />}
  </>;
}

/** Hover explanation for a control; phones see the same text inside the confirmation sheet. */
export function Tip({ text, children }: { text: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const place = useBubble(open, ref);
  return <span ref={ref} className="tip"
    onMouseEnter={() => matchMedia("(hover: hover)").matches && setOpen(true)}
    onMouseLeave={() => setOpen(false)} onFocus={() => matchMedia("(hover: hover)").matches && setOpen(true)}
    onBlur={() => setOpen(false)}>{children}{open && <Bubble text={text} place={place} />}</span>;
}

export function Card({ title, info, action, children, className = "" }:
  { title?: ReactNode; info?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>
    {(title || action) && <header className="card-head"><h2>{title}{info && <Info text={info} />}</h2>{action}</header>}
    {children}
  </section>;
}

export function Stat({ label, value, sub, info, valueClass = "" }:
  { label: ReactNode; value: ReactNode; sub?: ReactNode; info?: ReactNode; valueClass?: string }) {
  return <div className="stat">
    <span className="stat-label">{label}{info && <Info text={info} />}</span>
    <strong className={valueClass}>{value}</strong>
    {sub && <small>{sub}</small>}
  </div>;
}

export function Toggle({ checked, onChange, label, disabled }:
  { checked: boolean; onChange: (value: boolean) => void; label: string; disabled?: boolean }) {
  return <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled}
    className={`toggle ${checked ? "on" : ""}`} onClick={() => onChange(!checked)}><span /></button>;
}

export function Sheet({ title, onClose, children }: { title: ReactNode; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.classList.add("sheet-open");
    return () => { document.removeEventListener("keydown", onKey); document.body.classList.remove("sheet-open"); };
  }, [onClose]);
  return createPortal(
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined}
        onClick={event => event.stopPropagation()}>
        <div className="sheet-grip" />
        <header><h3>{title}</h3><button className="icon-button" aria-label="Close" onClick={onClose}>✕</button></header>
        {children}
      </div>
    </div>,
    document.body,
  );
}

/**
 * Shows the first `visible` rows of the list inside it at their real height; the rest scroll within the box.
 * The child must be the list itself (ul, ol or div), whose direct children are the rows.
 */
export function ScrollList({ visible, children }: { visible: number; children: ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number | null>(null);
  const [atEnd, setAtEnd] = useState(false);
  useLayoutEffect(() => {
    const element = box.current;
    const list = element?.firstElementChild as HTMLElement | null;
    if (!element || !list) return;
    const measure = () => {
      const rows = Array.from(list.children) as HTMLElement[];
      if (rows.length <= visible) { setHeight(null); return; }
      // Cut halfway into the gap after the last visible row, so the box ends cleanly between rows.
      const top = list.getBoundingClientRect().top;
      const lastBottom = rows[visible - 1].getBoundingClientRect().bottom;
      const nextTop = rows[visible].getBoundingClientRect().top;
      setHeight(Math.ceil((lastBottom + nextTop) / 2 - top));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    return () => observer.disconnect();
  });
  const scrollable = height != null;
  return <div ref={box} className={`scroll-list ${scrollable && !atEnd ? "more" : ""}`}
    style={scrollable ? { maxHeight: height } : undefined}
    onScroll={event => {
      const target = event.currentTarget;
      setAtEnd(target.scrollTop + target.clientHeight >= target.scrollHeight - 4);
    }}>{children}</div>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><strong>{title}</strong>{children && <span>{children}</span>}</div>;
}

export function Tabs<T extends string>({ value, options, onChange, label }:
  { value: T; options: { value: T; label: string }[]; onChange: (value: T) => void; label: string }) {
  return <div className="tabs" role="tablist" aria-label={label}>
    {options.map(option => <button key={option.value} role="tab" aria-selected={value === option.value}
      className={value === option.value ? "active" : ""} onClick={() => onChange(option.value)}>{option.label}</button>)}
  </div>;
}

const TOKEN_MARK: Record<string, string> = { SOL: "S", ETH: "Ξ", BTC: "₿", AAVE: "A", TRX: "T", BNB: "B" };

/** Round coin badge (one colour and mark per coin). */
export function CoinToken({ symbol }: { symbol: string }) {
  const label = symbol.replace(/USDT$/, "");
  return <span className={`token ${label.toLowerCase()}`} aria-hidden>{TOKEN_MARK[label] ?? label[0]}</span>;
}
