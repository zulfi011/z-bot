"""Exact raw-minute spot execution with fees, slippage, and conservative conflicts."""

import numpy as np
import pandas as pd

from src.research.target_vs_stop_first_hit import build_sparse_max_table, find_first_threshold_hit


WINDOW = 1440
SCENARIOS = {
    "gross": (0.0, 0.0),
    "fee_only": (10.0, 0.0),
    "realistic": (10.0, 2.0),
    "stressed": (10.0, 5.0),
    "severe": (10.0, 10.0),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


class SpotExecutionEngine:
    def __init__(self, raw):
        self.raw = raw.reset_index(drop=True)
        self.times = pd.DatetimeIndex(self.raw.open_time)
        require(self.times.is_unique and self.times.is_monotonic_increasing
                and str(self.times.tz) == "UTC", "Invalid raw times")
        require((self.times[1:] - self.times[:-1] == pd.Timedelta("1min")).all(), "Raw gaps")
        self.open = self.raw.open.to_numpy(float); self.high = self.raw.high.to_numpy(float)
        self.low = self.raw.low.to_numpy(float); self.close = self.raw.close.to_numpy(float)
        require(np.isfinite(self.raw[["open", "high", "low", "close"]].to_numpy(float)).all(),
                "Missing prices")
        self.high_table = build_sparse_max_table(self.high)
        self.negative_low_table = build_sparse_max_table(-self.low)

    def calculate(self, timestamps):
        times = pd.DatetimeIndex(timestamps).drop_duplicates().sort_values()
        start = self.times.get_indexer(times); safe_start = np.maximum(start, 0)
        complete = (start >= 0) & (start + WINDOW - 1 < len(self.times))
        end = np.where(complete, start + WINDOW - 1, -1); left = np.where(complete, start, -1)
        raw_entry = np.where(start >= 0, self.open[safe_start], np.nan)
        output = pd.DataFrame({"entry_timestamp": times, "raw_entry_open": raw_entry,
                               "execution_window_complete": complete})
        for scenario, (fee_bps, slip_bps) in SCENARIOS.items():
            fee = fee_bps / 10000; slip = slip_bps / 10000
            entry_fill = raw_entry * (1 + slip)
            target_price = entry_fill * 1.04; stop_price = entry_fill * .96
            target_hit, target_index = find_first_threshold_hit(self.high_table, left, end, target_price)
            stop_hit, stop_index = find_first_threshold_hit(self.negative_low_table, left, end, -stop_price)
            safe_target = np.maximum(target_index, 0); safe_stop = np.maximum(stop_index, 0)
            target_market = np.where(target_hit, np.maximum(target_price, self.open[safe_target]), np.nan)
            stop_market = np.where(stop_hit, np.minimum(stop_price, self.open[safe_stop]), np.nan)
            hold_market = np.where(complete, self.close[np.maximum(end, 0)], np.nan)
            target_first = target_hit & (~stop_hit | (target_index < stop_index))
            stop_first = stop_hit & (~target_hit | (stop_index <= target_index))
            raw_exit = np.where(target_first, target_market, np.where(stop_first, stop_market, hold_market))
            exit_fill = raw_exit * (1 - slip)
            net_multiple = exit_fill * (1 - fee) / (entry_fill * (1 + fee))
            duration = np.where(target_first, target_index - start + 1,
                                np.where(stop_first, stop_index - start + 1, WINDOW))
            exit_type = np.full(len(times), "time", object)
            exit_type[target_first] = "profit_target"
            exit_type[stop_first] = "protective_stop"
            exit_type[target_hit & stop_hit & (target_index == stop_index)] = "ambiguous_stop"
            exit_type[~complete] = "incomplete"
            output[f"{scenario}_entry_fill"] = entry_fill
            output[f"{scenario}_exit_fill"] = np.where(complete, exit_fill, np.nan)
            output[f"{scenario}_return_pct"] = np.where(complete, (net_multiple - 1) * 100, np.nan)
            output[f"{scenario}_duration_minutes"] = np.where(complete, duration, np.nan)
            output[f"{scenario}_exit_type"] = exit_type
        return output

    def validate_samples(self, outcomes, count=160):
        sample = outcomes.loc[outcomes.execution_window_complete].sample(
            n=min(count, outcomes.execution_window_complete.sum()), random_state=1524
        )
        checks = 0
        for row in sample.itertuples(index=False):
            start = self.times.get_loc(row.entry_timestamp); raw_entry = self.open[start]
            for scenario, (fee_bps, slip_bps) in SCENARIOS.items():
                fee = fee_bps / 10000; slip = slip_bps / 10000
                entry = raw_entry * (1 + slip)
                targets = np.flatnonzero(self.high[start:start + WINDOW] >= entry * 1.04)
                stops = np.flatnonzero(self.low[start:start + WINDOW] <= entry * .96)
                target_index = targets[0] if len(targets) else np.inf
                stop_index = stops[0] if len(stops) else np.inf
                expected = ("ambiguous_stop" if stop_index == target_index and np.isfinite(stop_index)
                            else "protective_stop" if stop_index < target_index
                            else "profit_target" if np.isfinite(target_index) else "time")
                require(getattr(row, f"{scenario}_exit_type") == expected,
                        f"Execution replay mismatch: {scenario}")
                expected_entry = raw_entry * (1 + slip)
                require(np.isclose(getattr(row, f"{scenario}_entry_fill"), expected_entry),
                        "Entry slippage mismatch")
                checks += 2
        return checks
