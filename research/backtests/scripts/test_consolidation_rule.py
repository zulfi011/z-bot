"""The SOL consolidation rule, unchanged, on another coin.

Rule: 1-hour chart, zone = last 24 hours, zone width <= 2%, buy at the next minute's open after an hourly close
above the zone top, stop −4%, trailing armed at +1.283% giving back 22%, no trend or hour filters.

Sizings: all-in (whole balance, one position at a time), 2 x $150, and 3 x $100. Costs 2 bps slippage per side,
fees 10 bps (USDT) and 7.5 bps (BNB). Usage: test_consolidation_rule.py ETHUSDT [more symbols]
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import sol_consolidation_combined as combined
import stage3_replay as replay

CHART, BARS, ZONE, CONFIRM, ACTIVATION, GIVEBACK, STOP = 60, 24, 2.0, 0, 1.283, 22.0, 4.0
WF = [f"wf{i}_test" for i in range(len(research.TESTS))]


def fixed(entries, table, column, times, lot, lots, start, end):
    research.LOT, research.LOTS, research.INITIAL, research.TABLE, research.COLS = lot, lots, 300.0, table, v4.COLS
    mask = (times[entries] >= start) & (times[entries] < end)
    stats = research.simulate(entries[mask], np.flatnonzero(mask))
    return {key: float(value[column]) for key, value in stats.items()}


def main() -> None:
    symbols = [s.upper() for s in sys.argv[1:]] or ["ETHUSDT"]
    rows = []
    for symbol in symbols:
        raw = replay.load_raw(symbol, include_holdout=True)
        raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
        grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
        times = pd.DatetimeIndex(raw.open_time)
        high, low, open_, close, last_minute = v4.bars_for(raw, CHART)
        entries = v4.entries_for(high, low, close, last_minute, BARS, ZONE, CONFIRM, grid.CLOSE, len(raw))
        v4.STOPS = [STOP]
        v4.EXITS = [(a, g, s) for s in v4.STOPS for a, g in v4.PAIRS]
        v4.COLS = len(v4.EXITS)
        table = v4.exits_for(entries)
        column = [i for i, (a, g, s) in enumerate(v4.EXITS) if np.isclose(a, ACTIVATION) and g == GIVEBACK][0]
        print(f"{symbol}: {len(entries)} breakout signals in the whole file", flush=True)
        for fee_bps, fee_name in ((10.0, "USDT"), (7.5, "BNB")):
            grid.FEE = fee_bps / 10_000
            sizings = {
                "all-in": lambda s, e: combined.all_in(entries, table[0][:, column], table[1][:, column], times, s, e, grid.FEE),
                "2 × $150": lambda s, e: fixed(entries, table, column, times, 150.0, 2, s, e),
                "3 × $100": lambda s, e: fixed(entries, table, column, times, 100.0, 3, s, e),
            }
            for name, run in sizings.items():
                periods = {window: run(*research.WINDOWS[window]) for window in ("full", "earlier", "later", "unseen", *WF)}
                walk = sum(periods[w]["profit"] for w in WF)
                rows.append({"coin": symbol.removesuffix("USDT"), "fees": fee_name, "sizing": name,
                             "trades": int(periods["full"]["trades"]),
                             "win_rate": round(100 * periods["full"]["wins"] / max(periods["full"]["trades"], 1)),
                             "full": periods["full"]["profit"], "earlier": periods["earlier"]["profit"],
                             "later": periods["later"]["profit"], "unseen": periods["unseen"]["profit"],
                             "walk_forward": walk, "wf_windows": f"{sum(periods[w]['profit'] > 0 for w in WF)}/6",
                             "drawdown": periods["full"]["dd"]})
    out = pd.DataFrame(rows)
    out.to_csv(grid.ROOT / "results" / f"consolidation_rule_{'_'.join(s.removesuffix('USDT').lower() for s in symbols)}.csv",
               index=False)
    pd.set_option("display.width", 250)
    for fee in ("USDT", "BNB"):
        print(f"\n=== {fee} fees")
        print(out[out.fees == fee].drop(columns=["fees"]).set_index(["coin", "sizing"]).round(2).to_string())


if __name__ == "__main__":
    main()
