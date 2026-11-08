"""ETH: the best single strategy from everything searched - the live dip entry, the EMA-in-uptrend exit,
and ETH's own consolidation breakout, in one $300 account as 3 x $100 lots.

Entry A (dip)           the deployed rule: 5-minute signals, 7-day average, +-0.5% zone from below, bullish
                        confirmation within 30 minutes, no entries 06:00-12:00 UTC, avoid-strong-bearish.
Entry B (consolidation) ETH's own grid winner: 2-hour chart, zone = last 12 bars (24h), width <= 2.5%,
                        30-minute confirmation wait, buy the next minute's open.

Exits tested per entry type: the deployed giveback, ETH's consolidation exit, and the EMA-in-uptrend hold.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
CONSOL = dict(chart=120, bars=12, zone=2.5, confirm=30, stop=3.5, arm=1.283, giveback=22.0)
EMA_HOURS, EMA_STOP = 16, 4.5


def trade(entry, arm, giveback, stop, ema=None):
    """One position; ema not None means hold to the EMA instead of giving back a share of the profit."""
    fill = grid.OPEN[entry] * (1 + grid.SLIP)
    level = fill * (1 - stop / 100)
    armed = research.first_hit(entry, fill * (1 + arm / 100), True)
    stopped = research.first_hit(entry, level, False, None if armed < 0 else armed)
    if stopped >= 0 and (armed < 0 or stopped <= armed):
        return stopped, min(level, grid.OPEN[stopped]), 2
    if armed < 0:
        return -1, np.nan, 0
    if ema is None:
        hit, price = research.trail_exit(armed, fill, giveback)
        return (hit, min(price, grid.OPEN[hit]), 1) if hit >= 0 else (-1, np.nan, 0)
    last = len(grid.OPEN) - 1
    for position in range(armed + 1, last + 1):
        if grid.LOW[position] <= level:
            return position, min(level, grid.OPEN[position]), 2
        if grid.CLOSE[position] < ema[position]:
            out = min(position + 1, last)
            return out, grid.OPEN[out], 1
    return -1, np.nan, 0


def evaluate(label, entries, exits, times):
    order = np.argsort(entries)
    entries, exits = np.asarray(entries)[order], [exits[i] for i in order]
    idx = np.array([[e[0]] for e in exits], dtype=np.int64)
    price = np.array([[e[1]] for e in exits])
    code = np.array([[e[2]] for e in exits], dtype=np.int8)
    research.TABLE, research.COLS = (idx, price, code), 1
    research.LOT, research.LOTS, research.INITIAL = 100.0, 3, 300.0
    out = {"strategy": label}
    for fee_bps, fee_name in ((7.5, "BNB"), (10.0, "USDT")):
        grid.FEE = fee_bps / 10_000
        stats = {}
        for name, (start, end) in research.WINDOWS.items():
            mask = (times[entries] >= start) & (times[entries] < end)
            stats[name] = research.simulate(entries[mask], np.flatnonzero(mask))
        full = {k: float(v[0]) for k, v in stats["full"].items()}
        if fee_name == "BNB":
            wins, losses = full["wins"], full["trades"] - full["wins"]
            out |= {"trades": int(full["trades"]),
                    "win_rate": 100 * full["wins"] / max(full["trades"], 1),
                    "avg_win": full["gross_win"] / wins if wins else 0.0,
                    "avg_loss": -full["gross_loss"] / losses if losses else 0.0,
                    "profit": full["profit"], "earlier": float(stats["earlier"]["profit"][0]),
                    "later": float(stats["later"]["profit"][0]), "unseen": float(stats["unseen"]["profit"][0]),
                    "wf": sum(float(stats[w]["profit"][0]) for w in WF),
                    "wf_windows": f"{sum(float(stats[w]['profit'][0]) > 0 for w in WF)}/6", "dd": full["dd"]}
        else:
            out["profit_usdt"] = full["profit"]
    return out


def main() -> None:
    rule = live.load_rule("eth")
    raw = replay.load_raw("ETHUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    times = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=EMA_HOURS * 60, adjust=False).mean().to_numpy()

    dip = live.live_entries(raw, rule)
    high, low, open_, close, last_minute = v4.bars_for(raw, CONSOL["chart"])
    breakout = v4.entries_for(high, low, close, last_minute, CONSOL["bars"], CONSOL["zone"], CONSOL["confirm"],
                              grid.CLOSE, len(raw))
    breakout = breakout[~np.isin(breakout, dip)]
    print(f"ETH: {len(dip)} dip signals, {len(breakout)} consolidation signals "
          f"({len(np.intersect1d(dip, breakout))} overlap, removed)", flush=True)

    def dip_deployed(e):
        return trade(e, rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"])
    def dip_ema(e):
        return trade(e, rule["activation_pct"], rule["giveback_pct"], EMA_STOP, ema if bullish[e] else None)
    def brk_own(e):
        return trade(e, CONSOL["arm"], CONSOL["giveback"], CONSOL["stop"])
    def brk_ema(e):
        return trade(e, CONSOL["arm"], CONSOL["giveback"], CONSOL["stop"], ema if bullish[e] else None)

    rows = []
    rows.append(evaluate("1. dip only, deployed exit (today)", dip, [dip_deployed(int(e)) for e in dip], times))
    rows.append(evaluate("2. dip only, EMA16h-in-uptrend exit", dip, [dip_ema(int(e)) for e in dip], times))
    rows.append(evaluate("3. consolidation only, own exit", breakout, [brk_own(int(e)) for e in breakout], times))
    rows.append(evaluate("4. consolidation only, EMA exit", breakout, [brk_ema(int(e)) for e in breakout], times))
    both = np.concatenate([dip, breakout])
    rows.append(evaluate("5. both, deployed + own exits", both,
                         [dip_deployed(int(e)) for e in dip] + [brk_own(int(e)) for e in breakout], times))
    rows.append(evaluate("6. both, EMA exit on dips only", both,
                         [dip_ema(int(e)) for e in dip] + [brk_own(int(e)) for e in breakout], times))
    rows.append(evaluate("7. both, EMA exit on everything", both,
                         [dip_ema(int(e)) for e in dip] + [brk_ema(int(e)) for e in breakout], times))
    frame = pd.DataFrame(rows).set_index("strategy")
    frame.to_csv(grid.ROOT / "results" / "eth_optimal.csv")
    pd.set_option("display.width", 250)
    print("\n=== ETH, $300 as 3 x $100 lots, BNB fees (profit_usdt = same strategy at USDT fees)")
    print(frame.round(2).to_string())


if __name__ == "__main__":
    main()
