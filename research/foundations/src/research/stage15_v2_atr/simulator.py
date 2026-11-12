"""Long-only spot target/stop simulation using entry-time ATR."""

import numpy as np
import pandas as pd

from src.research.target_vs_stop_first_hit import build_sparse_max_table, find_first_threshold_hit
from .atr import require


WINDOW = 1440
STOP_MULTIPLIERS = [1.5, 2.0, 2.5]
REWARD_RISK = [1.5, 2.0, 2.5]


def number(value):
    return f"{value:g}".replace(".", "_")


def strategy_name(stop_multiple, reward_risk):
    return f"atr_stop_{number(stop_multiple)}_rr_{number(reward_risk)}"


def strategy_specs():
    return [(strategy_name(stop, reward), stop, reward)
            for stop in STOP_MULTIPLIERS for reward in REWARD_RISK]


class AtrExitEngine:
    def __init__(self, raw):
        self.raw = raw.reset_index(drop=True)
        self.times = pd.DatetimeIndex(self.raw.open_time)
        require(self.times.is_unique and self.times.is_monotonic_increasing
                and str(self.times.tz) == "UTC", "Invalid raw timestamps")
        require((self.times[1:] - self.times[:-1] == pd.Timedelta("1min")).all(), "Raw 1m gaps")
        self.open = self.raw.open.to_numpy(float)
        self.high = self.raw.high.to_numpy(float)
        self.low = self.raw.low.to_numpy(float)
        self.close = self.raw.close.to_numpy(float)
        require(np.isfinite(self.raw[["open", "high", "low", "close"]].to_numpy(float)).all(),
                "Missing raw prices")
        self.high_table = build_sparse_max_table(self.high)
        self.negative_low_table = build_sparse_max_table(-self.low)

    def calculate(self, entry_context):
        context = entry_context.drop_duplicates("entry_timestamp").sort_values("entry_timestamp").reset_index(drop=True)
        times = pd.DatetimeIndex(context.entry_timestamp)
        start = self.times.get_indexer(times)
        complete = (start >= 0) & (start + WINDOW - 1 < len(self.times)) & context.atr_14_1h.notna().to_numpy()
        safe_start = np.maximum(start, 0)
        entry = np.where(start >= 0, self.open[safe_start], np.nan)
        atr = context.atr_14_1h.to_numpy(float)
        end = np.where(complete, start + WINDOW - 1, -1)
        left = np.where(complete, start, -1)
        hold = np.where(complete, self.close[np.maximum(end, 0)], np.nan)
        output = context.copy()
        output["atr_entry_price"] = entry
        output["atr_pct_of_entry"] = atr / entry * 100
        output["atr_window_complete"] = complete
        for strategy, stop_multiple, reward_risk in strategy_specs():
            risk = atr * stop_multiple
            stop_price = entry - risk
            target_price = entry + risk * reward_risk
            target_hit, target_index = find_first_threshold_hit(self.high_table, left, end, target_price)
            stop_hit, stop_index = find_first_threshold_hit(self.negative_low_table, left, end, -stop_price)
            safe_target = np.maximum(target_index, 0); safe_stop = np.maximum(stop_index, 0)
            target_fill = np.where(target_hit, np.maximum(target_price, self.open[safe_target]), np.nan)
            stop_fill = np.where(stop_hit, np.minimum(stop_price, self.open[safe_stop]), np.nan)
            target_first = target_hit & (~stop_hit | (target_index < stop_index))
            stop_first = stop_hit & (~target_hit | (stop_index <= target_index))
            exit_price = np.where(target_first, target_fill, np.where(stop_first, stop_fill, hold))
            duration = np.where(target_first, target_index - start + 1,
                                np.where(stop_first, stop_index - start + 1, WINDOW))
            exit_type = np.full(len(context), "time", object)
            exit_type[target_first] = "profit_target"
            exit_type[stop_first] = "protective_stop"
            exit_type[target_hit & stop_hit & (target_index == stop_index)] = "ambiguous_stop"
            exit_type[~complete] = "incomplete"
            output[f"{strategy}_stop_distance_pct"] = risk / entry * 100
            output[f"{strategy}_target_distance_pct"] = risk * reward_risk / entry * 100
            output[f"{strategy}_return_pct"] = np.where(complete, (exit_price / entry - 1) * 100, np.nan)
            output[f"{strategy}_duration_minutes"] = np.where(complete, duration, np.nan)
            output[f"{strategy}_exit_type"] = exit_type
        return output

    def validate_samples(self, outcomes, count=150):
        complete = outcomes.loc[outcomes.atr_window_complete]
        sample = complete.sample(n=min(count, len(complete)), random_state=1523)
        for row in sample.itertuples(index=False):
            start = self.times.get_loc(row.entry_timestamp)
            entry = self.open[start]
            for strategy, stop_multiple, reward_risk in strategy_specs():
                risk = row.atr_14_1h * stop_multiple
                targets = np.flatnonzero(self.high[start:start + WINDOW] >= entry + risk * reward_risk)
                stops = np.flatnonzero(self.low[start:start + WINDOW] <= entry - risk)
                target_index = targets[0] if len(targets) else np.inf
                stop_index = stops[0] if len(stops) else np.inf
                actual = getattr(row, f"{strategy}_exit_type")
                expected = ("ambiguous_stop" if stop_index == target_index and np.isfinite(stop_index)
                            else "protective_stop" if stop_index < target_index
                            else "profit_target" if np.isfinite(target_index) else "time")
                require(actual == expected, f"ATR exit replay mismatch: {strategy}")
        return len(sample) * len(strategy_specs())

