"""ETH's own best consolidation families, across sizings and both fee levels."""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import sol_consolidation_combined as combined
import stage3_replay as replay

SYMBOL = "ETHUSDT"
WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
# (label, chart, zone bars, zone %, confirm, stop) - the most robust families, plus the SOL rule for reference
CANDIDATES = [
    ("A 30m/24h/2.5%/3m/-2.5%", 30, 48, 2.5, 3, 2.5),
    ("B 15m/12h/1.0%/1m/-2.5%", 15, 48, 1.0, 1, 2.5),
    ("C 5m/2h/0.3%/1m/-2.0%", 5, 24, 0.3, 1, 2.0),
    ("D 120m/24h/2.5%/30m/-3.5%", 120, 12, 2.5, 30, 3.5),
    ("E 30m/20h/2.0%/1m/-2.0%", 30, 40, 2.0, 1, 2.0),
    ("SOL rule 60m/24h/2.0%/0m/-4%", 60, 24, 2.0, 0, 4.0),
]
GIVEBACK = 22.0          # middle of the ladder; the families pass at every giveback


def fixed(entries, table, column, times, lot, lots, start, end):
    research.LOT, research.LOTS, research.INITIAL, research.TABLE, research.COLS = lot, lots, 300.0, table, v4.COLS
    mask = (times[entries] >= start) & (times[entries] < end)
    stats = research.simulate(entries[mask], np.flatnonzero(mask))
    return {key: float(value[column]) for key, value in stats.items()}


def main() -> None:
    raw = replay.load_raw(SYMBOL, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    rows = []
    for label, chart, bars, zone, confirm, stop in CANDIDATES:
        high, low, open_, close, last_minute = v4.bars_for(raw, chart)
        entries = v4.entries_for(high, low, close, last_minute, bars, zone, confirm, grid.CLOSE, len(raw))
        v4.STOPS = [stop]
        v4.EXITS = [(a, g, s) for s in v4.STOPS for a, g in v4.PAIRS]
        v4.COLS = len(v4.EXITS)
        table = v4.exits_for(entries)
        column = [i for i, (a, g, s) in enumerate(v4.EXITS) if g == GIVEBACK][0]
        activation = v4.EXITS[column][0]
        print(f"{label}: {len(entries)} signals, trail +{activation}% / {GIVEBACK}% giveback", flush=True)
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
    out.to_csv(grid.ROOT / "results" / "eth_consolidation_sizing.csv", index=False)
    pd.set_option("display.width", 250)
    for fee in ("USDT", "BNB"):
        print(f"\n=== {fee} fees")
        print(out[out.fees == fee].drop(columns=["fees"]).set_index(["setting", "sizing"]).round(2).to_string())


if __name__ == "__main__":
    main()
