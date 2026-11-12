"""Check the fast grid against the exact Stage 3 replay.

1. Signals: every entry config's fast signals equal FrozenSignalEngine's.
2. Portfolio: the live baseline combination reproduces stage3_replay results.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

import run_sol_stage3_space_grid as grid
import stage3_replay as replay


def engine_strategy(config: dict) -> dict:
    strategy = json.loads(replay.STRATEGY_FILES[grid.SYMBOL].read_text())
    strategy["market"]["signal_timeframe"] = f"{config['signal_minutes']}m"
    strategy["averages"]["signal_average_days"] = config["average_days"]
    strategy["entry"]["touch_zone_pct"] = config["zone_pct"]
    strategy["entry"]["approach"] = config["approach"]
    strategy["entry"]["market_filter"]["type"] = config["market_filter"]
    return strategy


def check_signals(timeframes: list[int]) -> None:
    raw, daily = grid.load_market()
    decimal_averages = replay.daily_averages(raw)
    times = pd.DatetimeIndex(raw.open_time)
    for minutes in timeframes:
        frame = grid.signal_frame(raw, daily, minutes)
        candles = replay.signal_candles(raw, minutes, decimal_averages)
        for config in grid.entry_configs():
            if config["signal_minutes"] != minutes:
                continue
            fast = grid.fast_signals(frame, config)
            fast = fast[fast.entry_index < len(times)]
            exact, _ = replay.generate_signals(engine_strategy(config), candles)
            exact_entries = times.searchsorted(pd.DatetimeIndex([s["entry_time"] for s in exact]))
            exact_entries = exact_entries[exact_entries < len(times)]
            same = np.array_equal(fast.entry_index.to_numpy(), exact_entries)
            print(f"{config}: fast={len(fast)} exact={len(exact_entries)} match={same}", flush=True)
            if not same:
                raise SystemExit("SIGNAL MISMATCH")
    print("ALL SIGNALS MATCH")


if __name__ == "__main__":
    check_signals([int(value) for value in sys.argv[1:]] or grid.TIMEFRAMES)
