"""Stress one candidate: every trailing setting, then the neighbouring zone / wait / stop / chart settings.

Usage: consolidation_stress.py TRXUSDT 60 40 2.0 3 3.0 [sizing]   sizing = allin | 3x100 (default 3x100)
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


def evaluate(raw, times, chart, bars, zone, confirm, stop, pairs, sizing):
    high, low, open_, close, last_minute = v4.bars_for(raw, chart)
    entries = v4.entries_for(high, low, close, last_minute, bars, zone, confirm, grid.CLOSE, len(raw))
    v4.STOPS = [stop]
    v4.EXITS = [(a, g, s) for s in v4.STOPS for a, g in pairs]
    v4.COLS = len(v4.EXITS)
    if not len(entries):
        return []
    table = v4.exits_for(entries)
    rows = []
    for column, (activation, giveback, _) in enumerate(v4.EXITS):
        def run(start, end):
            if sizing == "allin":
                return combined.all_in(entries, table[0][:, column], table[1][:, column], times, start, end, grid.FEE)
            research.LOT, research.LOTS, research.INITIAL = 100.0, 3, 300.0
            research.TABLE, research.COLS = table, v4.COLS
            mask = (times[entries] >= start) & (times[entries] < end)
            stats = research.simulate(entries[mask], np.flatnonzero(mask))
            return {key: float(value[column]) for key, value in stats.items()}
        periods = {w: run(*research.WINDOWS[w]) for w in ("full", "earlier", "later", "unseen", *WF)}
        rows.append({"chart": chart, "bars": bars, "zone": zone, "wait": confirm, "stop": stop,
                     "trail": activation, "giveback": giveback, "trades": int(periods["full"]["trades"]),
                     "full": periods["full"]["profit"], "earlier": periods["earlier"]["profit"],
                     "later": periods["later"]["profit"], "unseen": periods["unseen"]["profit"],
                     "wf": sum(periods[w]["profit"] for w in WF),
                     "wf_windows": f"{sum(periods[w]['profit'] > 0 for w in WF)}/6", "dd": periods["full"]["dd"]})
    return rows


def main() -> None:
    symbol = sys.argv[1].upper()
    chart, bars, zone, confirm, stop = int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5]), float(sys.argv[6])
    sizing = sys.argv[7] if len(sys.argv) > 7 else "3x100"
    raw = replay.load_raw(symbol, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.FEE = 7.5 / 10_000
    times = pd.DatetimeIndex(raw.open_time)
    pd.set_option("display.width", 250)

    print(f"=== {symbol} {chart}m / {bars} bars / {zone}% / {confirm}m wait / -{stop}% stop, {sizing}, BNB fees")
    print("every trailing setting:")
    rows = evaluate(raw, times, chart, bars, zone, confirm, stop, v4.PAIRS, sizing)
    print(pd.DataFrame(rows).drop(columns=["chart", "bars", "zone", "wait", "stop"]).round(2).to_string(index=False))

    mid = [(a, g) for a, g in v4.PAIRS if g == 22.0]
    zones = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]
    waits = [0, 1, 3, 5, 10, 15, 30, 60]
    stops = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    charts = [1, 3, 5, 10, 15, 30, 60, 120, 240]
    bar_counts = [10, 12, 20, 24, 40, 48]
    def step(values, value, shift):
        position = values.index(value) + shift
        return values[position] if 0 <= position < len(values) else None
    probes = [(chart, bars, zone, confirm, stop)]
    for shift in (-1, 1):
        for axis, values, current in (("zone", zones, zone), ("wait", waits, confirm), ("stop", stops, stop),
                                      ("chart", charts, chart), ("bars", bar_counts, bars)):
            moved = step(values, current, shift)
            if moved is None:
                continue
            probe = {"chart": chart, "bars": bars, "zone": zone, "wait": confirm, "stop": stop}
            probe[axis] = moved
            probes.append((probe["chart"], probe["bars"], probe["zone"], probe["wait"], probe["stop"]))
    print("\nneighbours (trail +1.283% / 22% giveback):")
    out = [r for settings in probes for r in evaluate(raw, times, *settings, mid, sizing)]
    print(pd.DataFrame(out).drop(columns=["trail", "giveback"]).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
