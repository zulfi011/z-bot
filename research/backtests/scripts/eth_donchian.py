"""A third way into ETH: the N-day high breakout (Donchian channel, the classic Turtle entry).

Mode C can only fire after compression - it needs a band no wider than 2.5% over 24 hours. A Donchian
break asks nothing about how wide the market has been; it just wants a new high. So it fires on trend
INITIATION in volatile markets, exactly where Mode C is disqualified.

  channel     the highest high of the previous N days, as it stood before this minute
  trigger     a 1-minute close above that channel; the buy lands on the next minute's open
  dedup       only the first minute of each break counts, so a steady rally buys once, not every minute
  filters     ETH's blocked hours 06:00-12:00 UTC, shared with both existing entries

No trend filter. Requiring the averages stacked upward before a break screens out exactly the breaks
that START a trend - it cost money on every coin when tested on Mode C.

One parameter, N. Exits are the deployed ones, unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import three_modes as tm

COIN = "eth"
DAYS = [5, 10, 20, 30, 55]


def donchian_entries(high, close, days, times, blocked=(6, 12), cooldown_hours=0):
    """First 1-minute close above the previous N days' highest high."""
    window = days * 1440
    channel = pd.Series(high).rolling(window).max().shift(1).to_numpy()
    broke = np.isfinite(channel) & (close > channel)
    first = broke & ~np.r_[False, broke[:-1]]
    where = np.flatnonzero(first)
    if cooldown_hours:
        kept, last = [], -10**9
        for index in where:
            if index - last >= cooldown_hours * 60:
                kept.append(index)
                last = index
        where = np.asarray(kept, dtype=np.int64)
    entries = where + 1
    entries = entries[entries < len(close) - 1]
    if blocked:
        hour = times[entries].hour
        entries = entries[~((hour >= blocked[0]) & (hour < blocked[1]))]
    return entries.astype(np.int64)


def mode_c_entries(raw):
    mc = tm.MODE_C
    high, low, open_, close, last_minute = v4.bars_for(raw, mc["chart"])
    entries = v4.entries_for(high, low, close, last_minute, mc["bars"], mc["zone"], mc["confirm"],
                             grid.CLOSE, len(raw))
    hour = grid.TIMES[entries].hour
    return entries[~((hour >= 6) & (hour < 12))]


def build(raw, bullish, ema, mode_c, donchian=(), donchian_exit="dip"):
    rule = live.load_rule(COIN)
    trades = []
    for entry in live.live_entries(raw, rule):
        entry = int(entry)
        line = ema if bullish[entry] else None
        out, price, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], tm.DIP_STOP, line)
        trades.append((entry, out, price, "dip"))
    for entry in mode_c:
        entry = int(entry)
        line = ema if bullish[entry] else None
        out, price, _ = opt.trade(entry, tm.MODE_C["arm"], tm.MODE_C["giveback"], tm.MODE_C["stop"], line)
        trades.append((entry, out, price, "breakout"))
    arm, giveback, stop = ((rule["activation_pct"], rule["giveback_pct"], tm.DIP_STOP)
                           if donchian_exit == "dip" else
                           (tm.MODE_C["arm"], tm.MODE_C["giveback"], tm.MODE_C["stop"]))
    for entry in donchian:
        entry = int(entry)
        line = ema if bullish[entry] else None
        out, price, _ = opt.trade(entry, arm, giveback, stop, line)
        trades.append((entry, out, price, "donchian"))
    return sorted(trades, key=lambda row: row[0])


def evaluate(label, trades, fee=7.5 / 10_000):
    row = tm.evaluate(label, trades, fee)
    ledger = tm.account(trades, *research.WINDOWS["full"], fee)["ledger"]
    row["donchian"] = int((ledger.source == "donchian").sum()) if len(ledger) else 0
    return row


def setup():
    raw = replay.load_raw("ETHUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=tm.EMA_HOURS * 60, adjust=False).mean().to_numpy()
    return raw, bullish, ema, mode_c_entries(raw)


COLUMNS = ["trades", "dip", "modeC", "donchian", "win_rate", "avg_win", "avg_loss", "profit",
           "earlier", "later", "unseen", "walk_forward", "wf_windows", "drawdown"]


def main() -> None:
    raw, bullish, ema, mode_c = setup()
    pd.set_option("display.width", 300)
    window = (grid.TIMES >= research.WINDOWS["full"][0]) & (grid.TIMES < research.WINDOWS["full"][1])

    print("=== how many candidates each channel length produces (before slots)")
    counts = []
    for days in DAYS:
        entries = donchian_entries(grid.HIGH, grid.CLOSE, days, grid.TIMES)
        counts.append({"channel days": days, "candidates": len(entries),
                       "in full window": int(window[entries].sum())})
    print(pd.DataFrame(counts).to_string(index=False))

    base = evaluate("dip + Mode C (deployed today)", build(raw, bullish, ema, mode_c))
    print("\n=== Donchian ADDED as a third way in (deployed dip exit: stop -4.5%, arm 1.315%, giveback 30%)")
    rows = [base]
    for days in DAYS:
        entries = donchian_entries(grid.HIGH, grid.CLOSE, days, grid.TIMES)
        rows.append(evaluate(f"+ Donchian {days}-day high", build(raw, bullish, ema, mode_c, entries)))
    print(pd.DataFrame(rows).set_index("strategy")[COLUMNS].to_string())

    print("\n=== same, but the Donchian lots use Mode C's tighter exit (stop -3.5%, giveback 22%)")
    rows = [base]
    for days in DAYS:
        entries = donchian_entries(grid.HIGH, grid.CLOSE, days, grid.TIMES)
        rows.append(evaluate(f"+ Donchian {days}-day high",
                             build(raw, bullish, ema, mode_c, entries, donchian_exit="breakout")))
    print(pd.DataFrame(rows).set_index("strategy")[COLUMNS].to_string())

    print("\n=== Donchian ALONE on its own $300 (is the rule any good by itself?)")
    rows = []
    for days in DAYS:
        entries = donchian_entries(grid.HIGH, grid.CLOSE, days, grid.TIMES)
        only = [t for t in build(raw, bullish, ema, [], entries) if t[3] == "donchian"]
        rows.append(evaluate(f"Donchian {days}-day alone", only))
    print(pd.DataFrame(rows).set_index("strategy")[
        ["trades", "win_rate", "avg_win", "avg_loss", "profit", "earlier", "later", "unseen",
         "walk_forward", "wf_windows", "drawdown"]].to_string())


if __name__ == "__main__":
    main()
