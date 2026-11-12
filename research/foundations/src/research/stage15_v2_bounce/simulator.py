"""Exact raw-minute +4% target, -4% stop, and 24-hour exit simulation."""

import numpy as np
import pandas as pd

from src.research.target_vs_stop_first_hit import build_sparse_max_table, find_first_threshold_hit
from .signals import require


WINDOW = 1440
TARGET_PCT = 4.0
STOP_PCT = 4.0


class FixedExitEngine:
    def __init__(self, raw):
        self.raw = raw.reset_index(drop=True)
        self.times = pd.DatetimeIndex(self.raw.open_time)
        require(self.times.is_unique and self.times.is_monotonic_increasing
                and str(self.times.tz) == "UTC", "Invalid raw timestamps")
        require((self.times[1:] - self.times[:-1] == pd.Timedelta("1min")).all(),
                "Raw 1m gaps")
        self.open = self.raw.open.to_numpy(float)
        self.high = self.raw.high.to_numpy(float)
        self.low = self.raw.low.to_numpy(float)
        self.close = self.raw.close.to_numpy(float)
        require(np.isfinite(self.raw[["open", "high", "low", "close"]].to_numpy(float)).all(),
                "Missing raw prices")
        self.high_table = build_sparse_max_table(self.high)
        self.negative_low_table = build_sparse_max_table(-self.low)

    def calculate(self, timestamps):
        times = pd.DatetimeIndex(timestamps).drop_duplicates().sort_values()
        start = self.times.get_indexer(times)
        complete = (start >= 0) & (start + WINDOW - 1 < len(self.times))
        safe_start = np.maximum(start, 0)
        entry = np.where(start >= 0, self.open[safe_start], np.nan)
        end = np.where(complete, start + WINDOW - 1, -1)
        left = np.where(complete, start, -1)
        target_price = entry * 1.04
        stop_price = entry * .96
        target_hit, target_index = find_first_threshold_hit(self.high_table, left, end, target_price)
        stop_hit, stop_index = find_first_threshold_hit(self.negative_low_table, left, end, -stop_price)
        safe_target = np.maximum(target_index, 0)
        safe_stop = np.maximum(stop_index, 0)
        target_fill = np.where(target_hit, np.maximum(target_price, self.open[safe_target]), np.nan)
        stop_fill = np.where(stop_hit, np.minimum(stop_price, self.open[safe_stop]), np.nan)
        hold = np.where(complete, self.close[np.maximum(end, 0)], np.nan)
        target_first = target_hit & (~stop_hit | (target_index < stop_index))
        stop_first = stop_hit & (~target_hit | (stop_index <= target_index))
        exit_price = np.where(target_first, target_fill, np.where(stop_first, stop_fill, hold))
        duration = np.where(target_first, target_index - start + 1,
                            np.where(stop_first, stop_index - start + 1, WINDOW))
        exit_type = np.full(len(times), "time", object)
        exit_type[target_first] = "profit_target"
        exit_type[stop_first] = "protective_stop"
        exit_type[target_hit & stop_hit & (target_index == stop_index)] = "ambiguous_stop"
        exit_type[~complete] = "incomplete"
        return pd.DataFrame({
            "entry_timestamp": times,
            "entry_price": entry,
            "complete_24h": complete,
            "gross_return_pct": np.where(complete, (exit_price / entry - 1) * 100, np.nan),
            "duration_minutes": np.where(complete, duration, np.nan),
            "exit_type": exit_type,
        })

    def validate_samples(self, outcomes, count=120):
        sample = outcomes.loc[outcomes.complete_24h].sample(
            n=min(count, outcomes.complete_24h.sum()), random_state=1521
        )
        for row in sample.itertuples(index=False):
            start = self.times.get_loc(row.entry_timestamp)
            entry = self.open[start]
            highs = self.high[start:start + WINDOW]
            lows = self.low[start:start + WINDOW]
            target = np.flatnonzero(highs >= entry * 1.04)
            stop = np.flatnonzero(lows <= entry * .96)
            target_index = target[0] if len(target) else np.inf
            stop_index = stop[0] if len(stop) else np.inf
            if np.isfinite(stop_index) and stop_index <= target_index:
                expected_type = "ambiguous_stop" if stop_index == target_index else "protective_stop"
            elif np.isfinite(target_index):
                expected_type = "profit_target"
            else:
                expected_type = "time"
            require(row.exit_type == expected_type, "Exit replay mismatch")
        return len(sample)
