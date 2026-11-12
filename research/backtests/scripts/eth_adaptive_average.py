"""Does ETH's dip entry do better with a FASTER average while the market is in an uptrend?

The dip buys a touch of the 7-day average from below. In an uptrend price runs away from a 7-day average and the
entry waits for weeks. This tries shorter averages - 5d, 3d, 2d, 1d, 12h, 6h, 3h - both as a straight swap and as
an adaptive rule: the short average while the daily averages are stacked 7 > 15 > 30, the deployed 7-day otherwise.

Everything else is ETH as deployed: 5-minute signal candles, a touch within +-0.5% of the average approached from
below, a green candle within 30 minutes, no entries 06:00-12:00 UTC, no entries in a stacked downtrend, and the
deployed exit (stop -4.5%, trail +1.315%, Mode A on the 16-hour line when bought in an uptrend).

Averages, both without lookahead:
  N days   completed UTC daily closes, effective the next day - the deployed definition (7d here reproduces live)
  N hours  the mean of the last N hours of 1-minute closes, as of the minute BEFORE the signal candle opens
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_pullback as pb
import eth_regime as rg

EDGE = 1e-12
FEE, MIN_ORDER = 7.5 / 10_000, 5.0
LENGTHS = [("7d (deployed)", 7 * 1440), ("5d", 5 * 1440), ("3d", 3 * 1440), ("2d", 2 * 1440), ("1d", 1440),
           ("12h", 720), ("6h", 360), ("3h", 180)]


def average_by_bar(raw, frame, minutes: int) -> np.ndarray:
    """The average each signal candle is measured against, one value per candle."""
    if minutes % 1440 == 0:                       # the deployed convention for whole days
        table = replay.daily_average_n(raw, minutes // 1440)
        days = frame["open_time"].floor("D")
        return np.array([float(table[day]) if table.get(day) is not None else np.nan for day in days])
    # Short horizons have no daily equivalent: the mean of the last N minutes, ending before this candle opens.
    rolling = pd.Series(grid.CLOSE).rolling(minutes).mean().to_numpy()
    index = frame["first_raw"] + np.arange(len(frame["close"])) * (frame["open_time"][1] - frame["open_time"][0]).seconds // 60
    return np.where(index > 0, rolling[np.maximum(index - 1, 0)], np.nan)


def entries_for(raw, rule, frame, average) -> np.ndarray:
    """live_ema_hold_all.live_entries, with the average supplied instead of read from the strategy."""
    zone = rule["zone_pct"] / 100
    high, low, close, open_ = frame["high"], frame["low"], frame["close"], frame["open"]
    a7, a15, a30 = frame[7], frame[15], frame[30]
    with np.errstate(invalid="ignore"):
        lower, upper = average * (1 - zone), average * (1 + zone)
        touched = np.isfinite(average) & (high >= lower * (1 - EDGE)) & (low <= upper * (1 + EDGE))
        prior_below = np.zeros(len(high), bool)
        prior_below[1:] = np.isfinite(average[:-1]) & (high[:-1] < lower[:-1] * (1 - EDGE))
        missing = ~(np.isfinite(a7) & np.isfinite(a15) & np.isfinite(a30))
        bearish = ~missing & (a7 < a15) & (a15 < a30)
    eligible = touched & ~np.r_[False, touched[:-1]] & prior_below & ~(bearish | missing)
    bullish_candle = close > open_
    steps = 30 // rule["minutes"]
    confirmations = []
    for origin in np.flatnonzero(eligible):
        for offset in range(steps + 1):
            index = origin + offset
            if index >= len(high):
                break
            if bullish_candle[index]:
                confirmations.append(index)
                break
            if not touched[index]:
                break
    confirmations = np.asarray(confirmations, dtype=np.int64)
    entries = frame["first_raw"] + (confirmations + 1) * rule["minutes"]
    entries = entries[entries < len(raw) - 1]
    if rule["blocked"]:
        hours = grid.TIMES.hour.to_numpy()[entries]
        entries = entries[~((hours >= rule["blocked"][0]) & (hours < rule["blocked"][1]))]
    return entries


def dip_trades(entries, bullish, ema, rule):
    out = []
    for entry in entries:
        entry = int(entry)
        line = ema if bullish[entry] else None
        o, p, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], 4.5, line)
        out.append((entry, o, p, "dip"))
    return out


def simulate(trades, lots, lot, start, end):
    """One shared wallet, `lots` slots, the live buying rule (a full lot, or what is left)."""
    wallet, slots, taken = lots * lot, [], []
    for entry, exit_index, price, source in trades:
        if not (start <= grid.TIMES[entry] < end):
            continue
        wallet += sum(s[1] for s in slots if s[0] <= entry)
        slots = [s for s in slots if s[0] > entry]
        if exit_index < 0 or len(slots) >= lots or wallet < MIN_ORDER:
            continue
        spend = min(lot, np.floor(wallet * 100) / 100)
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        proceeds = spend / (fill * (1 + FEE)) * price * (1 - grid.SLIP) * (1 - FEE)
        wallet -= spend
        slots.append((exit_index, proceeds))
        taken.append({"source": source, "pnl": proceeds - spend})
    wallet += sum(s[1] for s in slots)
    return {"profit": wallet - lots * lot, "ledger": pd.DataFrame(taken)}


def score(label, trades, lots=3, lot=100.0, candidates=None):
    runs = {w: simulate(trades, lots, lot, *research.WINDOWS[w]) for w in ("full", "unseen", *rg.TESTS)}
    led = runs["full"]["ledger"]
    wf = [runs[w]["profit"] for w in rg.TESTS]
    wins = led[led.pnl > 0] if len(led) else led
    return {"average used": label, "candidates": candidates, "taken": len(led),
            "win%": round(100 * (led.pnl > 0).mean(), 1) if len(led) else 0.0,
            "avg_win": round(wins.pnl.mean(), 2) if len(wins) else 0.0,
            "profit": round(runs["full"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "windows": f"{sum(x > 0 for x in wf)}/6", "unseen": round(runs["unseen"]["profit"], 2)}


def main() -> None:
    raw, bullish, ema, mode_c = pb.setup()
    rule = live.load_rule("eth")
    daily = replay.daily_averages(raw)
    frame = grid.signal_frame(raw, daily, rule["minutes"])
    for period in (7, 15, 30):
        frame[period] = np.array([np.nan if v is None else float(v) for v in frame[period]])
    pd.set_option("display.width", 250)

    # the deployed dip, for reference and as a check that the generalised code reproduces it
    deployed = live.live_entries(raw, rule)
    seven = entries_for(raw, rule, frame, average_by_bar(raw, frame, 7 * 1440))
    print(f"deployed dip entries {len(deployed)}; rebuilt with the 7-day average {len(seven)}; "
          f"identical: {np.array_equal(np.asarray(deployed), seven)}")

    print("\n=== 1. one fixed average for every market (dip only, $300 as 3 x $100)")
    rows, built = [], {}
    for label, minutes in LENGTHS:
        entries = entries_for(raw, rule, frame, average_by_bar(raw, frame, minutes))
        built[label] = entries
        rows.append(score(label, dip_trades(entries, bullish, ema, rule), candidates=len(entries)))
    print(pd.DataFrame(rows).set_index("average used").to_string())

    print("\n=== 2. adaptive: the short average while 7d > 15d > 30d, the 7-day average otherwise")
    days = frame["open_time"].floor("D")
    bar_bullish = np.array([bool(v) for v in (frame[7] > frame[15]) & (frame[15] > frame[30])])
    long_average = average_by_bar(raw, frame, 7 * 1440)
    rows = []
    for label, minutes in LENGTHS[1:]:
        short = average_by_bar(raw, frame, minutes)
        mixed = np.where(bar_bullish, short, long_average)
        entries = entries_for(raw, rule, frame, mixed)
        built[f"adaptive {label}"] = entries
        rows.append(score(f"7d, {label} in uptrends", dip_trades(entries, bullish, ema, rule), candidates=len(entries)))
    rows.insert(0, score("7d always (deployed)", dip_trades(built["7d (deployed)"], bullish, ema, rule),
                         candidates=len(built["7d (deployed)"])))
    print(pd.DataFrame(rows).set_index("average used").to_string())

    print("\n=== 3. how often each average is touched while the market is in an uptrend")
    counts = []
    for label, minutes in LENGTHS:
        entries = built[label]
        share = bullish[entries].mean() * 100 if len(entries) else 0
        counts.append({"average": label, "candidate entries": len(entries),
                       "in an uptrend": f"{share:.0f}%", "per month": round(len(entries) / 22, 1)})
    print(pd.DataFrame(counts).set_index("average").to_string())


if __name__ == "__main__":
    main()
