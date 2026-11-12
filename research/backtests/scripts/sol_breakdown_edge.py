"""The mirror question: after price leaves a tight intraday zone DOWNWARD, does it bounce?

Spot-only, so this is still a buy - buying the downside break and expecting it to revert, which is what the
negative edge on upside breaks implies. Same measurement: forward move vs a random minute, no fees, no exits.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

HORIZONS = [15, 30, 60, 240]
RULES = [("15 min zone, 0.3% wide", 5, 3, 0.3), ("30 min zone, 0.3% wide", 5, 6, 0.3),
         ("1 hour zone, 0.3% wide", 5, 12, 0.3), ("1 hour zone, 0.5% wide", 15, 4, 0.5),
         ("2 hour zone, 0.5% wide", 15, 8, 0.5), ("4 hour zone, 1% wide", 30, 8, 1.0)]


def downside_entries(high, low, close, last_minute, bars, zone, minute_count):
    top = pd.Series(high).rolling(bars).max().to_numpy()
    bottom = pd.Series(low).rolling(bars).min().to_numpy()
    zone_top, zone_bottom = np.r_[np.nan, top[:-1]], np.r_[np.nan, bottom[:-1]]
    quiet = (zone_top / zone_bottom - 1) <= zone / 100
    broke = quiet & (close < zone_bottom)
    first = broke & ~np.r_[False, broke[:-1]]
    entries = last_minute[np.flatnonzero(first)] + 1
    return entries[entries < minute_count - 1].astype(np.int64)


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
    rng = np.random.default_rng(0)
    baseline = rng.choice(len(close) - 1500, 20_000, replace=False)
    rows = []
    for horizon in HORIZONS:
        rows.append({"rule": "any random minute", "horizon_min": horizon, **stats(close, baseline, horizon, fill)})
    for label, chart, bars, zone in RULES:
        high, low, open_, close_tf, last_minute = v4.bars_for(raw, chart)
        entries = downside_entries(high, low, close_tf, last_minute, bars, zone, len(raw))
        for horizon in HORIZONS:
            result = stats(close, entries, horizon, fill)
            if result:
                rows.append({"rule": f"DOWN break: {label}", "horizon_min": horizon, **result})
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    for horizon in HORIZONS:
        print(f"--- {horizon} minutes after buying the downside break")
        print(out[out.horizon_min == horizon].drop(columns=["horizon_min"]).round(3).to_string(index=False))
        print()


if __name__ == "__main__":
    main()
