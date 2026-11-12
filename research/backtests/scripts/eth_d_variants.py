"""Candidate D on ETH: every trailing variant and the neighbouring zone / wait / stop settings, all-in sizing."""
from __future__ import annotations
import pandas as pd
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import sol_consolidation_combined as combined
import stage3_replay as replay

WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
BASE = (120, 12, 2.5, 30, 3.5)
NEIGHBOURS = [BASE, (120, 12, 2.0, 30, 3.5), (120, 12, 3.0, 30, 3.5), (120, 12, 2.5, 15, 3.5),
              (120, 12, 2.5, 60, 3.5), (120, 12, 2.5, 30, 3.0), (120, 12, 2.5, 30, 4.0),
              (120, 10, 2.5, 30, 3.5), (120, 24, 2.5, 30, 3.5), (60, 24, 2.5, 30, 3.5), (240, 12, 2.5, 30, 3.5)]

def run(raw, times, chart, bars, zone, confirm, stop, pairs):
    high, low, open_, close, last_minute = v4.bars_for(raw, chart)
    entries = v4.entries_for(high, low, close, last_minute, bars, zone, confirm, grid.CLOSE, len(raw))
    v4.STOPS, v4.PAIRS_USED = [stop], pairs
    v4.EXITS = [(a, g, s) for s in v4.STOPS for a, g in pairs]
    v4.COLS = len(v4.EXITS)
    table = v4.exits_for(entries)
    out = []
    for column, (activation, giveback, _) in enumerate(v4.EXITS):
        stats = {w: combined.all_in(entries, table[0][:, column], table[1][:, column], times, *research.WINDOWS[w], grid.FEE)
                 for w in ("full", "earlier", "later", "unseen", *WF)}
        out.append({"chart": chart, "bars": bars, "zone": zone, "wait": confirm, "stop": stop,
                    "trail": activation, "giveback": giveback, "trades": int(stats["full"]["trades"]),
                    "full": stats["full"]["profit"], "earlier": stats["earlier"]["profit"],
                    "later": stats["later"]["profit"], "unseen": stats["unseen"]["profit"],
                    "wf": sum(stats[w]["profit"] for w in WF),
                    "wf_windows": f"{sum(stats[w]['profit'] > 0 for w in WF)}/6", "dd": stats["full"]["dd"]})
    return out

def main() -> None:
    raw = replay.load_raw("ETHUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.FEE = 7.5 / 10_000
    times = pd.DatetimeIndex(raw.open_time)
    pd.set_option("display.width", 250)
    print("=== D at every trailing setting (all-in, BNB fees)")
    print(pd.DataFrame(run(raw, times, *BASE, v4.PAIRS)).drop(columns=["chart", "bars", "zone", "wait", "stop"]).round(2).to_string(index=False))
    print("\n=== D's neighbours (trail +1.283% / 22% giveback)")
    mid = [(a, g) for a, g in v4.PAIRS if g == 22.0]
    rows = [r for settings in NEIGHBOURS for r in run(raw, times, *settings, mid)]
    print(pd.DataFrame(rows).drop(columns=["trail", "giveback"]).round(2).to_string(index=False))

if __name__ == "__main__":
    main()
