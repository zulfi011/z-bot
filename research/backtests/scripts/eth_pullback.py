"""A third way into ETH: buy the shallow pullback inside an uptrend.

The dip entry needs price to fall all the way back to the 7-day average, and Mode C needs a quiet band to
form first. Neither fires when ETH simply trends upward in a wide range - which is where ETH makes its
money. This entry fills that hole.

  trend       the daily averages are stacked 7d > 15d > 30d (the same test Mode A uses)
  pullback    a 1-minute close drops BELOW the N-hour EMA and stays below for at least `dwell` minutes
  trigger     the first close back ABOVE that EMA ends the pullback; the buy lands on the next minute's open
  filters     ETH's blocked hours 06:00-12:00 UTC, shared with both existing entries

`dwell` is what separates a real pullback from price brushing the line: without it a close oscillating
around the EMA fires dozens of times an hour.

Every pullback lot is by construction bought in an uptrend, so it exits through Mode A - the 16-hour EMA
hold - exactly like a dip lot bought in the same conditions. Nothing about the deployed rules changes.

$300 as 3 x $100 lots, BNB fees, shared with the dip entry and Mode C, first come first served.
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
HOURS = [4, 8, 12, 24, 48]
DWELL = [15, 60, 180]


def pullback_entries(close, bullish, hours, dwell, times, blocked=(6, 12)):
    """First 1-minute close back above the N-hour EMA after a pullback of at least `dwell` minutes."""
    line = pd.Series(close).ewm(span=hours * 60, adjust=False).mean().to_numpy()
    below = close < line
    index = np.arange(len(close))
    last_above = np.maximum.accumulate(np.where(~below, index, 0))
    run = index - last_above                                   # consecutive minutes below, ending here
    reclaim = (~below) & np.r_[False, below[:-1]]
    reclaim[0] = False
    where = np.flatnonzero(reclaim)
    where = where[run[where - 1] >= dwell]
    where = where[bullish[where]]                              # the uptrend test, read at the signal
    entries = where + 1                                        # buy at the next minute's open
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


def build(raw, bullish, ema, mode_c, pullback=()):
    """The deployed system, plus the pullback entries supplied."""
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
    for entry in pullback:
        entry = int(entry)
        line = ema if bullish[entry] else None
        out, price, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], tm.DIP_STOP, line)
        trades.append((entry, out, price, "pullback"))
    return sorted(trades, key=lambda row: row[0])


def evaluate(label, trades, fee=7.5 / 10_000):
    """three_modes.evaluate, with the third source counted."""
    row = tm.evaluate(label, trades, fee)
    full = tm.account(trades, *research.WINDOWS["full"], fee)
    ledger = full["ledger"]
    row["pullback"] = int((ledger.source == "pullback").sum()) if len(ledger) else 0
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


def main() -> None:
    raw, bullish, ema, mode_c = setup()
    pd.set_option("display.width", 300)
    window = (grid.TIMES >= research.WINDOWS["full"][0]) & (grid.TIMES < research.WINDOWS["full"][1])
    print(f"the daily averages are stacked 7d>15d>30d {100 * bullish[window].mean():.1f}% of the time")

    print("\n=== how many candidates each setting produces (before slots)")
    counts = []
    for hours in HOURS:
        for dwell in DWELL:
            entries = pullback_entries(grid.CLOSE, bullish, hours, dwell, grid.TIMES)
            inside = window[entries].sum()
            counts.append({"EMA hours": hours, "dwell minutes": dwell, "candidates": len(entries),
                           "in full window": int(inside)})
    print(pd.DataFrame(counts).to_string(index=False))

    base = evaluate("dip + Mode C (deployed today)", build(raw, bullish, ema, mode_c))
    print("\n=== the pullback entry ADDED as a third way in")
    rows = [base]
    for hours in HOURS:
        for dwell in DWELL:
            entries = pullback_entries(grid.CLOSE, bullish, hours, dwell, grid.TIMES)
            rows.append(evaluate(f"+ pullback, EMA {hours}h, dwell {dwell}m",
                                 build(raw, bullish, ema, mode_c, entries)))
    frame = pd.DataFrame(rows).set_index("strategy")
    print(frame[["trades", "dip", "modeC", "pullback", "win_rate", "avg_win", "avg_loss", "profit",
                 "earlier", "later", "unseen", "walk_forward", "wf_windows", "drawdown"]].to_string())

    print("\n=== the pullback entry ALONE, on its own $300 (is the rule any good by itself?)")
    rows = []
    for hours in HOURS:
        for dwell in DWELL:
            entries = pullback_entries(grid.CLOSE, bullish, hours, dwell, grid.TIMES)
            only = [t for t in build(raw, bullish, ema, [], entries) if t[3] == "pullback"]
            rows.append(evaluate(f"pullback only, EMA {hours}h, dwell {dwell}m", only))
    frame = pd.DataFrame(rows).set_index("strategy")
    print(frame[["trades", "win_rate", "avg_win", "avg_loss", "profit", "earlier", "later", "unseen",
                 "walk_forward", "wf_windows", "drawdown"]].to_string())


if __name__ == "__main__":
    main()
