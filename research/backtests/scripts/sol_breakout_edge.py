"""Do SOL consolidation breakouts predict anything? Forward returns after the signal vs a random minute.

No exits, no fees, no sizing - just: after this signal, where is the price N minutes later, compared with
buying at a random minute. If a signal has no edge here, no exit rule can create one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

HORIZONS = [15, 30, 60, 240, 1440]
RULES = [("15 min zone, 0.3% wide", 5, 3, 0.3, 0), ("1 hour zone, 0.3% wide", 5, 12, 0.3, 0),
         ("1 hour zone, 0.5% wide", 15, 4, 0.5, 0), ("4 hour zone, 0.5% wide", 15, 16, 0.5, 0),
         ("4 hour zone, 1% wide", 30, 8, 1.0, 0), ("8 hour zone, 1% wide", 30, 16, 1.0, 0),
         ("24 hour zone, 2% wide", 60, 24, 2.0, 0), ("24 hour zone, 2% wide, 30m wait", 60, 24, 2.0, 30)]


def stats(close, entries, horizon, fill):
    entries = entries[entries + horizon < len(close)]
    if not len(entries):
        return None
    forward = close[entries + horizon] / fill[entries] - 1
    return {"signals": len(entries), "median_%": 100 * np.median(forward), "mean_%": 100 * forward.mean(),
            "up_%": 100 * (forward > 0).mean(), "beat_19bps_%": 100 * (forward > 0.0019).mean()}


def main() -> None:
    raw = replay.load_raw("SOLUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    close, fill = grid.CLOSE, grid.OPEN
    pd.set_option("display.width", 200)

    rng = np.random.default_rng(0)
    baseline = rng.choice(len(close) - 1500, 20_000, replace=False)
    rows = []
    for horizon in HORIZONS:
        base = stats(close, baseline, horizon, fill)
        rows.append({"rule": "any random minute", "horizon_min": horizon, **base})
    for label, chart, bars, zone, confirm in RULES:
        high, low, open_, close_tf, last_minute = v4.bars_for(raw, chart)
        entries = v4.entries_for(high, low, close_tf, last_minute, bars, zone, confirm, close, len(raw))
        for horizon in HORIZONS:
            result = stats(close, entries, horizon, fill)
            if result:
                rows.append({"rule": label, "horizon_min": horizon, **result})
    out = pd.DataFrame(rows)
    print("forward move after the signal (no fees, no exits). 19 bps = the round-trip cost:\n")
    for horizon in HORIZONS:
        print(f"--- {horizon} minutes later")
        print(out[out.horizon_min == horizon].drop(columns=["horizon_min"]).round(3).to_string(index=False))
        print()


if __name__ == "__main__":
    main()
