import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { control, credentialsStatus, LockedError, lockDevice, sessionStatus, unlockDevice, type BinanceCredentials, type CoinView, type Dashboard, type DeviceSession, type Position } from "./api";
import { BinanceSheet } from "./binance";
import { amount, n, pct, price, signedUsd, time, tone, usd } from "./format";
import { Info, Sheet } from "./ui";

type SheetState =
  | { kind: "pot" }
  | { kind: "entry-module"; coin: CoinView; module: "pullback" | "pyramid" }
  | { kind: "buy-now"; coin: CoinView }
  | { kind: "close"; position: Position }
  | { kind: "trading"; coin: CoinView; enable: boolean }
  | { kind: "trading-mode"; mode: "off" | "shadow" | "live" }
  | { kind: "cancel"; requestId: string; what: string }
  | { kind: "unlock" }
  | { kind: "device" }
  | { kind: "binance" };

type Controls = {
  open: (sheet: SheetState) => void;
  flash: string | null;
  dismissFlash: () => void;
  session: DeviceSession | null;
  /** The server said this device is locked: show the unlock step, then come back to what was being done. */
  locked: () => void;
  /** Whether a Binance key is attached (null until known). */
  binance: BinanceCredentials | null;
};

const ControlsContext = createContext<Controls>({
  open: () => undefined, flash: null, dismissFlash: () => undefined, session: null, locked: () => undefined, binance: null,
});
export const useControls = () => useContext(ControlsContext);

export const EXPLAIN = {
  money: "All money stays in your Binance spot wallet. This app only decides when to buy and sell. Add or withdraw funds in Binance itself.",
  growth: "Tested growth plan (backtest, all five coins, Oct 2024 – Sep 2026): start at 3 × $100. Each time the wallet grows by another $100, add one lot until there are 5. After that, add $20 to every lot for each further $100 (5 × $120, 5 × $140 …). You change it here by hand; the bot never changes it on its own.",
  buyNow: "Buys one full lot at the market price right now, without waiting for a strategy signal, and parks the same stop on Binance. Use sparingly — it is outside the strategy.",
  entryModule: "Switches an extra way in off, lets it share the coin's lots, or gives it lots of its own. Its own lots are extra money from your pot that only this way in may spend — the core (the dip and Mode C) can never take them, and it can never take the core's.",
  pot: "One set of lots shared by every coin you switch on. Whichever coin signals first takes the next free lot; no coin has money of its own, so nothing sits idle. If losses leave less than a full lot, the last buy uses what is left. Nothing moves in Binance. Open lots keep their size; new lots use the new size.",
  close: "Sells this whole lot on Binance at the market price and cancels its stop order. In shadow mode it is only recorded, not sold.",
  pause: "Switches this coin off: its signals and Buy now are skipped, so the shared lots go to the other coins. Its signals keep being tracked so you can see what it would have done.",
  resume: "Switches this coin on: from the next minute its signals can take any free lot in the shared pot, first come first served.",
  unlock: "Enter the control key (STRATEGY_EDIT_TOKEN in the server's .env) once on this device. The server gives the device a 30-day pass; the key itself is not stored in the browser. Viewing never needs it. Changing the key on the server locks every device.",
  modeLive: "Real orders go to Binance from now on: market buys for signals, a stop-loss order parked on Binance for every lot, and market sells when the trailing stop or your Close button fires.",
  modeShadow: "The bot works out every order and records it, but sends nothing to Binance. Use this to watch the strategy with live prices before risking money.",
  modeOff: "Nothing is bought. Open lots keep their stop orders on Binance and are still managed, so they can still be sold.",
};

function ConfirmSheet({ text, note, confirmLabel, run, onDone, onCancel, danger }:
  { text: ReactNode; note?: ReactNode; confirmLabel: string; run: () => Promise<string>; onDone: (message: string) => void;
    onCancel?: () => void; danger?: boolean }) {
  const { locked } = useControls();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return <>
    <p className="sheet-text">{text}</p>
    {note && <div className="sheet-note">{note}</div>}
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="sheet-actions">
      {onCancel && <button className="ghost" onClick={onCancel} disabled={busy}>Cancel</button>}
      <button className={danger ? "danger" : "primary"} disabled={busy} onClick={async () => {
        setBusy(true); setError(null);
        try { onDone(await run()); } catch (reason) {
          if (reason instanceof LockedError) { locked(); return; }
          setError(reason instanceof Error ? reason.message : "Request failed");
        }
        finally { setBusy(false); }
      }}>{busy ? "Sending…" : confirmLabel}</button>
    </div>
  </>;
}

/** What closing a lot now would do, from the server's live estimate. */
export function CloseBreakdown({ position }: { position: Position }) {
  const estimate = position.close_estimate;
  if (!estimate) return <p className="small">No live price yet — the lot would close at the current minute's closing price.</p>;
  const net = n(estimate.net_pnl_usd);
  return <div className="breakdown">
    <div className="preview-row"><span>Sell {amount(position.quantity)} {position.coin} at about</span><b>{price(estimate.exit_fill_price)}</b></div>
    <div className="preview-row"><span>You paid</span><b>{usd(position.allocation_usd)} at {price(position.entry_fill_price)}</b></div>
    <div className="preview-row"><span>Exit fee ({estimate.fee_asset === "BNB" ? "from BNB wallet" : "USDT"})</span><b className="down">−{usd(estimate.fee_usd, 3)}</b></div>
    <div className="preview-row"><span>Slippage</span><b className="down">−{usd(estimate.slippage_usd, 3)}</b></div>
    <div className="preview-row"><span>USDT back in your wallet</span><b>{usd(estimate.cash_back_usd)}</b></div>
    <div className="preview-row total"><span>Result of this trade</span><b className={tone(net)}>{signedUsd(net)} ({pct(estimate.net_return_pct)})</b></div>
    {position.trailing_active
      ? <p className="small muted">The trailing stop is active and would otherwise sell at {price(position.trail_price)} or higher.</p>
      : <p className="small muted">Otherwise it waits for the stop at {price(position.stop_price)} or the trailing start at {price(position.activation_price)}.</p>}
    <p className="small muted">Estimated at the latest price {price(estimate.price)}. The sell goes to Binance at the end of this minute and fills at the market price then, so the result can differ slightly.</p>
  </div>;
}

function TradingSheet({ coin, enable, data, onDone, onCancel }:
  { coin: CoinView; enable: boolean; data: Dashboard | null; onDone: (message: string) => void; onCancel: () => void }) {
  const live = data?.coins[coin.symbol] ?? coin;
  const [closeAll, setCloseAll] = useState(false);
  const name = live.label;
  const open = live.positions;
  const total = open.reduce((sum, position) => sum + n(position.close_estimate?.net_pnl_usd), 0);
  if (enable) {
    return <ConfirmSheet text={EXPLAIN.resume} confirmLabel={`Switch ${name} on`} onCancel={onCancel}
      note={<>{name} then shares the pot's {live.lots.max_lots} × {usd(live.lots.lot_size_usd, 0)} lots with the other coins that are on. Nothing is bought immediately — it waits for its next signal.</>}
      run={async () => { await control(`/api/v1/coins/${live.symbol}/trading`, "PUT", { enabled: true }); return `${name} is on — its next signal can take a free lot.`; }}
      onDone={onDone} />;
  }
  return <ConfirmSheet danger={closeAll} text={EXPLAIN.pause} onCancel={onCancel}
    confirmLabel={closeAll ? `Switch ${name} off & close ${open.length} lot${open.length === 1 ? "" : "s"}` : `Switch ${name} off`}
    note={open.length === 0 ? <>{name} has no open lots, so nothing else changes.</> : <>
      <p className="small">{name} has <b>{open.length} open lot{open.length === 1 ? "" : "s"}</b>. What should happen to {open.length === 1 ? "it" : "them"}?</p>
      <div className="choice">
        <label><input type="radio" checked={!closeAll} onChange={() => setCloseAll(false)} />
          <span><b>Keep open trades running</b><small>They finish normally by their stop or trailing stop. No new {name} lot opens until you switch it on again.</small></span></label>
        <label><input type="radio" checked={closeAll} onChange={() => setCloseAll(true)} />
          <span><b>Close all open trades now</b><small>Sells every {name} lot at the close of the current minute. Estimated result: <b className={tone(total)}>{signedUsd(total)}</b> after fees and slippage.</small></span></label>
      </div>
    </>}
    run={async () => {
      await control(`/api/v1/coins/${live.symbol}/trading`, "PUT", { enabled: false, close_positions: closeAll });
      return closeAll ? `${name} is off — its ${open.length} open lot(s) close at the end of this minute.` : `${name} is off — open lots keep running; no new ${name} trades until you switch it on.`;
    }}
    onDone={onDone} />;
}

/** What the tested growth plan suggests for a pot of this size: 3 lots, one more per $100 up to 5, then +$20 a lot. */
export function suggestedPot(value: number): { lots: number; lot: number } {
  const steps = Math.max(0, Math.floor((value - 300) / 100));
  return steps <= 2 ? { lots: 3 + steps, lot: 100 } : { lots: 5, lot: 100 + 20 * (steps - 2) };
}

function PotSheet({ data, onDone }: { data: Dashboard | null; onDone: (message: string) => void }) {
  const limits = data?.money.limits;
  const pot = data?.money.pot;
  const budget = n(data?.money.budget_usd);
  const { locked } = useControls();
  const [lotSize, setLotSize] = useState(String(n(pot?.lot_size_usd) || 100));
  const [lots, setLots] = useState(String(pot?.lots || 3));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const size = Number(lotSize), count = Number(lots);
  const shapeOk = size > 0 && Number.isInteger(count) && count >= 1 && count <= 50 && /^\d+(\.\d{1,2})?$/.test(lotSize.trim());
  const shape = `${count} × ${usd(size, size % 1 ? 2 : 0)}`;
  const total = size * count;
  const unchanged = size === n(pot?.lot_size_usd) && count === pot?.lots;
  const suggestion = suggestedPot(budget);
  const openNow = pot?.open_lots ?? 0;
  return <>
    <p className="sheet-text">{EXPLAIN.pot}</p>
    <div className="field-row">
      <label className="field"><span>Number of lots</span>
        <input inputMode="numeric" type="number" min="1" max="50" step="1" value={lots} onChange={event => setLots(event.target.value)} /></label>
      <label className="field"><span>Money per lot (USDT)</span>
        <input inputMode="decimal" type="number" min={n(limits?.minimum_lot_usd)} step="1" value={lotSize} onChange={event => setLotSize(event.target.value)} /></label>
    </div>
    <div className="chips">{[[3, 100], [4, 100], [5, 100], [5, 120], [5, 140], [5, 160]].map(([b, a]) =>
      <button key={`${b}x${a}`} type="button" onClick={() => { setLots(String(b)); setLotSize(String(a)); }}>{b} × {usd(a, 0)}</button>)}</div>
    <div className="sheet-note preview">
      {!shapeOk ? <span className="form-error">Enter 1–50 lots and a lot size (up to 2 decimals).</span> : <>
        <div className="preview-row"><span>Shared pot</span><b>{shape} = {usd(total)}</b></div>
        <div className="preview-row"><span>Your money (free USDT + open lots)</span><b>{usd(budget)}</b></div>
        <div className="preview-row"><span>Open lots now</span><b>{openNow}</b></div>
        <div className="preview-row"><span>Growth plan suggests for {usd(budget, 0)}</span>
          <b><button type="button" className="link" onClick={() => { setLots(String(suggestion.lots)); setLotSize(String(suggestion.lot)); }}>
            {suggestion.lots} × {usd(suggestion.lot, 0)}</button></b></div>
        {total > budget + 0.01 && <p className="form-warning">The pot is {usd(total - budget)} more than you have. That is allowed: the last lot simply buys with whatever USDT is left, or waits.</p>}
        {count < openNow && <p className="form-warning">{openNow} lots are open now. They keep running; no new lot opens until fewer than {count} are open.</p>}
      </>}
    </div>
    <p className="small muted">{EXPLAIN.growth}</p>
    {error && <p className="form-error" role="alert">{error}</p>}
    <button className="primary wide" disabled={busy || !shapeOk || unchanged} onClick={async () => {
      setBusy(true); setError(null);
      try {
        await control("/api/v1/pot", "PUT", { lot_size_usd: lotSize.trim(), lots: count });
        onDone(`Shared pot is now ${shape}.`);
      } catch (reason) {
        if (reason instanceof LockedError) { locked(); return; }
        setError(reason instanceof Error ? reason.message : "Request failed");
      }
      finally { setBusy(false); }
    }}>{busy ? "Saving…" : unchanged ? "No change" : `Save ${shape}`}</button>
  </>;
}

const MODULE_TEXT = {
  pullback: {
    title: "Pullback",
    what: "In an uptrend, after at least 3 hours below the 24-hour line, the first close back above it buys.",
    tested: "Backtest: it pays for its slot on ETH. It shares the coin's lots with the dip and Mode C.",
  },
  pyramid: {
    title: "Pyramid adds",
    what: "While a lot is winning, another lot is added every +1% above its buy price (up to 3), as long as price is above the 16-hour line. Adds are always held against that line.",
    tested: "Backtest: sharing the lots earns more than reserving lots for it, and lifts ETH from $80 to $100 of profit per $100 - at a deeper drawdown.",
  },
} as const;

function EntryModuleSheet({ coin, module, data, onDone }:
  { coin: CoinView; module: "pullback" | "pyramid"; data: Dashboard | null; onDone: (message: string) => void }) {
  const live = data?.coins[coin.symbol] ?? coin;
  const current = live.entries?.[module];
  const text = MODULE_TEXT[module];
  const [enabled, setEnabled] = useState(Boolean(current?.enabled));
  const { locked } = useControls();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unchanged = enabled === Boolean(current?.enabled);
  const openHere = current?.open_lots ?? 0;
  return <>
    <p className="sheet-text">{text.what}</p>
    <div className="choice">
      {([[true, "On", `It draws on the shared pot's ${live.lots.max_lots} lot${live.lots.max_lots === 1 ? "" : "s"} like every other way in, first come first served.`],
         [false, "Off", "No new lots from this way in. Signals are still tracked so you can see what it would have done."]] as const)
        .map(([value, title, note]) =>
          <label key={String(value)}><input type="radio" checked={enabled === value} onChange={() => setEnabled(value)} />
            <span><b>{title}</b><small>{note}</small></span></label>)}
    </div>
    {!enabled && openHere > 0 && <p className="form-warning">
      {openHere} {module} lot{openHere === 1 ? "" : "s"} {openHere === 1 ? "is" : "are"} open. Switching off stops new
      ones; the open {openHere === 1 ? "one keeps" : "ones keep"} running to their stop or trend line.</p>}
    <p className="small muted">{text.tested}</p>
    {error && <p className="form-error" role="alert">{error}</p>}
    <button className="primary wide" disabled={busy || unchanged} onClick={async () => {
      setBusy(true); setError(null);
      try {
        await control(`/api/v1/coins/${live.symbol}/entries/${module}`, "PUT", { enabled });
        onDone(`${live.label} ${module} is ${enabled ? "on, sharing its lots" : "off"}.`);
      } catch (reason) {
        if (reason instanceof LockedError) { locked(); return; }
        setError(reason instanceof Error ? reason.message : "Request failed");
      } finally { setBusy(false); }
    }}>{busy ? "Saving…" : unchanged ? "No change" : "Save"}</button>
  </>;
}

function UnlockSheet({ onUnlocked, onCancel }: { onUnlocked: (session: DeviceSession) => void; onCancel: () => void }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true); setError(null);
    try { onUnlocked(await unlockDevice(key.trim())); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unlock failed"); setKey(""); }
    finally { setBusy(false); }
  };
  return <form onSubmit={event => { event.preventDefault(); if (key.trim() && !busy) submit(); }}>
    <p className="sheet-text">{EXPLAIN.unlock}</p>
    <label className="field"><span>Control key</span>
      <input type="password" autoComplete="current-password" autoFocus placeholder="Your control key" value={key}
        onChange={event => setKey(event.target.value)} /></label>
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="sheet-actions">
      <button type="button" className="ghost" onClick={onCancel} disabled={busy}>Cancel</button>
      <button type="submit" className="primary" disabled={busy || !key.trim()}>{busy ? "Checking…" : "Unlock this device"}</button>
    </div>
  </form>;
}

const LOCKED_ICON = <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
const UNLOCKED_ICON = <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M5.5 7V5a2.5 2.5 0 0 1 4.9-.7" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>;

/** Header button: shows whether this device can use the controls, and unlocks or locks it. */
export function DeviceLockButton() {
  const { session, open } = useControls();
  if (!session || !session.controls_enabled) return null;
  return <button className={`icon-button lock-button ${session.unlocked ? "unlocked" : "locked"}`}
    aria-label={session.unlocked ? "This device is unlocked" : "Unlock this device"}
    title={session.unlocked ? "Unlocked — tap to lock this device" : "Locked — tap to unlock the controls"}
    onClick={() => open({ kind: session.unlocked ? "device" : "unlock" })}>
    {session.unlocked ? UNLOCKED_ICON : LOCKED_ICON}</button>;
}

const NEEDS_UNLOCK = new Set<SheetState["kind"]>(["pot", "entry-module", "buy-now", "close", "trading", "trading-mode", "cancel", "binance"]);

export function ControlsProvider({ data, refresh, children }: { data: Dashboard | null; refresh: () => void; children: ReactNode }) {
  const [sheet, setSheet] = useState<SheetState | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [session, setSession] = useState<DeviceSession | null>(null);
  // What the user was trying to do when the unlock step appeared; it opens again right after unlocking.
  const [pending, setPending] = useState<SheetState | null>(null);

  const [binance, setBinance] = useState<BinanceCredentials | null>(null);

  useEffect(() => { sessionStatus().then(setSession).catch(() => setSession(null)); }, []);
  useEffect(() => { credentialsStatus().then(setBinance).catch(() => setBinance(null)); }, []);

  const showFlash = useCallback((message: string) => {
    setFlash(message);
    window.setTimeout(() => setFlash(current => current === message ? null : current), 7000);
  }, []);
  const close = useCallback(() => { setSheet(null); setPending(null); }, []);
  const done = useCallback((message: string) => { setSheet(null); showFlash(message); refresh(); }, [refresh, showFlash]);
  const dismissFlash = useCallback(() => setFlash(null), []);
  const open = useCallback((next: SheetState) => {
    // Going live needs a Binance account: show how to attach one instead.
    if (next.kind === "trading-mode" && next.mode === "live" && binance && !binance.attached) next = { kind: "binance" };
    if (NEEDS_UNLOCK.has(next.kind) && session && session.controls_enabled && !session.unlocked) {
      setPending(next); setSheet({ kind: "unlock" });
      return;
    }
    setSheet(next);
  }, [session, binance]);
  const locked = useCallback(() => {
    setSession(current => current ? { ...current, unlocked: false, expires_at: null } : current);
    setPending(sheet && NEEDS_UNLOCK.has(sheet.kind) ? sheet : null);
    setSheet({ kind: "unlock" });
  }, [sheet]);
  const value = useMemo(() => ({ open, flash, dismissFlash, session, locked, binance }), [open, flash, dismissFlash, session, locked, binance]);

  let title = "";
  let body: ReactNode = null;
  if (sheet?.kind === "unlock") {
    title = "Unlock this device";
    body = <UnlockSheet onCancel={close} onUnlocked={next => {
      setSession(next);
      refresh();
      if (pending) { setSheet(pending); setPending(null); }
      else { setSheet(null); showFlash("This device is unlocked for 30 days."); }
    }} />;
  } else if (sheet?.kind === "device") {
    title = "This device is unlocked";
    body = <ConfirmSheet
      text={<>Buttons that trade or change money work on this device{session?.expires_at ? <> until <b>{time(session.expires_at, true)}</b></> : null}. Lock it if someone else can use it, or if you lose it.</>}
      note={<>Changing the control key on the server locks every device at once.</>}
      confirmLabel="Lock this device" danger onCancel={close}
      run={async () => {
        await lockDevice();
        setSession(current => current ? { ...current, unlocked: false, expires_at: null } : current);
        return "This device is locked. Viewing still works; buttons will ask to unlock.";
      }}
      onDone={done} />;
  } else if (sheet?.kind === "binance") {
    title = binance?.attached ? "Your Binance account" : "Attach your Binance account";
    body = <BinanceSheet credentials={binance} live={data?.trading.mode === "live"} onCancel={close}
      onChanged={(next, message) => { setBinance(next); done(message); }} />;
  } else if (sheet?.kind === "entry-module") {
    title = `${MODULE_TEXT[sheet.module].title} · ${sheet.coin.label}`;
    body = <EntryModuleSheet coin={sheet.coin} module={sheet.module} data={data} onDone={done} />;
  } else if (sheet?.kind === "pot") {
    title = "Shared pot";
    body = <PotSheet data={data} onDone={done} />;
  } else if (sheet?.kind === "buy-now") {
    const coin = data?.coins[sheet.coin.symbol] ?? sheet.coin;
    const name = coin.label;
    const next = coin.lots.next_lot_usd;
    title = `Buy one ${name} lot now`;
    body = <ConfirmSheet text={EXPLAIN.buyNow}
      note={next != null
        ? <>Buys <b>{usd(next)}</b> of {name} at about {price(coin.market.price)}, using your Binance USDT
          ({usd(coin.lots.free_usdt)} free).{data?.trading.mode !== "live" && <> Trading is in <b>{data?.trading.mode}</b> mode, so it is only recorded.</>}</>
        : <>No lot is available right now ({coin.lots.slot_free ? `Binance has ${usd(coin.lots.free_usdt)} free USDT` : "all lots are open"}).</>}
      confirmLabel={`Buy ${name} ${next != null ? usd(next) : ""}`}
      run={async () => { await control(`/api/v1/lots/${coin.symbol}/buy-now`); return `${name} buy queued — it fills within a minute.`; }}
      onDone={done} onCancel={close} />;
  } else if (sheet?.kind === "trading-mode") {
    const labels = { off: "Stop all trading", shadow: "Switch to shadow mode", live: "Switch on live trading" };
    const texts = { off: EXPLAIN.modeOff, shadow: EXPLAIN.modeShadow, live: EXPLAIN.modeLive };
    title = labels[sheet.mode];
    body = <ConfirmSheet danger={sheet.mode === "live"} text={texts[sheet.mode]}
      note={sheet.mode === "live"
        ? <><b>This spends real money.</b> Binance has {usd(data?.binance.usdt_free)} free USDT and the shared pot is
          {" "}{data?.money.pot.lots} × {usd(data?.money.pot.lot_size_usd, 0)}. Each signal from a coin that is on buys one
          lot and a stop order is parked on Binance straight away.</>
        : sheet.mode === "off" ? <>Open lots stay protected by their stop orders and can still be sold.</>
          : <>Nothing will reach Binance until you switch to live again.</>}
      confirmLabel={labels[sheet.mode]}
      run={async () => {
        await control("/api/v1/settings/trading", "PUT", { mode: sheet.mode });
        return sheet.mode === "live" ? "Live trading is on — real orders from the next signal."
          : sheet.mode === "off" ? "All trading stopped. Nothing new will be bought."
            : "Shadow mode: decisions are recorded but nothing is sent to Binance.";
      }}
      onDone={done} onCancel={close} />;
  } else if (sheet?.kind === "trading") {
    title = sheet.enable ? `Switch ${sheet.coin.label} on` : `Switch ${sheet.coin.label} off`;
    body = <TradingSheet coin={sheet.coin} enable={sheet.enable} data={data} onDone={done} onCancel={close} />;
  } else if (sheet?.kind === "close") {
    // Use the freshest estimate while the popup stays open.
    const position = data?.positions.find(item => item.position_id === sheet.position.position_id) ?? sheet.position;
    title = `Close ${position.coin} lot ${position.lot_number}?`;
    body = <ConfirmSheet danger text={EXPLAIN.close}
      note={<CloseBreakdown position={position} />}
      confirmLabel="Close"
      run={async () => { await control(`/api/v1/positions/${encodeURIComponent(position.position_id)}/close`); return `${position.coin} lot ${position.lot_number} closes at the end of this minute.`; }}
      onDone={done} onCancel={close} />;
  } else if (sheet?.kind === "cancel") {
    title = "Cancel request";
    body = <ConfirmSheet text={`Cancel the waiting “${sheet.what}” request? Nothing has been applied yet.`}
      confirmLabel="Cancel request"
      run={async () => { await control(`/api/v1/requests/${sheet.requestId}/cancel`); return "Request cancelled."; }}
      onDone={done} onCancel={close} />;
  }

  return <ControlsContext.Provider value={value}>
    {children}
    {sheet && <Sheet title={title} onClose={close}>{body}</Sheet>}
  </ControlsContext.Provider>;
}
