"""A coin's best consolidation families across sizings and both fee levels.

Usage: consolidation_sizing.py trx
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

WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
GIVEBACK = 22.0        # middle of the trailing ladder; these families pass at every giveback
# (label, chart minutes, zone bars, zone %, confirm minutes, stop %)
CANDIDATES = {
    "trx": [("A 60m/48h/2.5%/1m/-3.0%", 60, 48, 2.5, 1, 3.0),
            ("B 60m/40h/2.0%/3m/-3.0%", 60, 40, 2.0, 3, 3.0),
            ("C 60m/48h/2.5%/1m/-2.0%", 60, 48, 2.5, 1, 2.0),
            ("D 15m/10h/1.0%/30m/-2.5%", 15, 40, 1.0, 30, 2.5),
            ("E 60m/20h/2.0%/1m/-3.0%", 60, 20, 2.0, 1, 3.0),
            ("SOL rule 60m/24h/2.0%/0m/-4%", 60, 24, 2.0, 0, 4.0)],
    "aave": [("A 60m/12h/2.0%/1m/-3.5%", 60, 12, 2.0, 1, 3.5),
             ("B 30m/12h/2.0%/1m/-3.5%", 30, 24, 2.0, 1, 3.5),
             ("C 60m/12h/2.5%/5m/-3.5%", 60, 12, 2.5, 5, 3.5),
             ("D 30m/12h/2.0%/60m/-3.5%", 30, 24, 2.0, 60, 3.5)],
    "eth": [("A 120m/24h/2.5%/30m/-3.5%", 120, 12, 2.5, 30, 3.5)],
    "btc": [("A 10m/3.3h/0.3%/1m/-2.0%", 10, 20, 0.3, 1, 2.0),
            ("B 10m/3.3h/0.3%/1m/-1.5%", 10, 20, 0.3, 1, 1.5),
            ("C 10m/3.3h/0.3%/30m/-2.0%", 10, 20, 0.3, 30, 2.0),
            ("D 5m/3.3h/0.3%/5m/-1.5%", 5, 40, 0.3, 5, 1.5)],
}


def fixed(entries, table, column, times, lot, lots, start, end):
    research.LOT, research.LOTS, research.INITIAL, research.TABLE, research.COLS = lot, lots, 300.0, table, v4.COLS
    mask = (times[entries] >= start) & (times[entries] < end)
    stats = research.simulate(entries[mask], np.flatnonzero(mask))
    return {key: float(value[column]) for key, value in stats.items()}


def main() -> None:
    coin = (sys.argv[1] if len(sys.argv) > 1 else "trx").lower()
    raw = replay.load_raw(f"{coin.upper()}USDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    rows = []
    for label, chart, bars, zone, confirm, stop in CANDIDATES[coin]:
        high, low, open_, close, last_minute = v4.bars_for(raw, chart)
        entries = v4.entries_for(high, low, close, last_minute, bars, zone, confirm, grid.CLOSE, len(raw))
        v4.STOPS = [stop]
        v4.EXITS = [(a, g, s) for s in v4.STOPS for a, g in v4.PAIRS]
        v4.COLS = len(v4.EXITS)
        table = v4.exits_for(entries)
        column = [i for i, (a, g, s) in enumerate(v4.EXITS) if g == GIVEBACK][0]
        print(f"{label}: {len(entries)} signals", flush=True)
        for fee_bps, fee_name in ((10.0, "USDT"), (7.5, "BNB")):
            grid.FEE = fee_bps / 10_000
            sizings = {
                "all-in": lambda s, e: combined.all_in(entries, table[0][:, column], table[1][:, column], times, s, e, grid.FEE),
                "2 × $150": lambda s, e: fixed(entries, table, column, times, 150.0, 2, s, e),
                "3 × $100": lambda s, e: fixed(entries, table, column, times, 100.0, 3, s, e),
            }
            for name, run in sizings.items():
                periods = {w: run(*research.WINDOWS[w]) for w in ("full", "earlier", "later", "unseen", *WF)}
                rows.append({"setting": label, "fees": fee_name, "sizing": name,
                             "trades": int(periods["full"]["trades"]),
                             "win_rate": round(100 * periods["full"]["wins"] / max(periods["full"]["trades"], 1)),
                             "full": periods["full"]["profit"], "earlier": periods["earlier"]["profit"],
                             "later": periods["later"]["profit"], "unseen": periods["unseen"]["profit"],
                             "walk_forward": sum(periods[w]["profit"] for w in WF),
                             "wf_windows": f"{sum(periods[w]['profit'] > 0 for w in WF)}/6",
                             "drawdown": periods["full"]["dd"]})
    out = pd.DataFrame(rows)
    out.to_csv(grid.ROOT / "results" / f"{coin}_consolidation_sizing.csv", index=False)
    pd.set_option("display.width", 250)
    for fee in ("USDT", "BNB"):
        print(f"\n=== {coin.upper()}, {fee} fees")
        print(out[out.fees == fee].drop(columns=["fees"]).set_index(["setting", "sizing"]).round(2).to_string())


if __name__ == "__main__":
    main()
