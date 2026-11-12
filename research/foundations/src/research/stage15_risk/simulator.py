"""Exact raw-minute fixed-stop simulation for inherited Stage 1.5 entries."""

import numpy as np
import pandas as pd

from src.research.target_vs_stop_first_hit import (
    build_sparse_max_table,
    find_first_threshold_hit,
)


STOP_LEVELS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
OBSERVATION_MINUTES = 1440
TARGET_PCT = 2.5


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stop_label(level):
    return f"{level:g}".replace(".", "_")


class FixedStopEngine:
    """Simulate stops from an entry open through the next 1,440 raw candles."""

    def __init__(self, raw: pd.DataFrame):
        self.raw = raw.reset_index(drop=True)
        self.times = pd.DatetimeIndex(self.raw.open_time)
        require(
            self.times.is_unique
            and self.times.is_monotonic_increasing
            and str(self.times.tz) == "UTC",
            "Invalid raw timestamps",
        )
        require(
            (self.times[1:] - self.times[:-1] == pd.Timedelta("1min")).all(),
            "Raw 1m gaps",
        )
        self.open = self.raw.open.to_numpy(float)
        self.high = self.raw.high.to_numpy(float)
        self.low = self.raw.low.to_numpy(float)
        self.close = self.raw.close.to_numpy(float)
        prices = self.raw[["open", "high", "low", "close"]].to_numpy(float)
        require(np.isfinite(prices).all(), "Missing raw prices")
        require(
            (self.low <= np.minimum(self.open, self.close)).all()
            and (self.high >= np.maximum(self.open, self.close)).all()
            and (self.low > 0).all(),
            "Invalid raw OHLC",
        )
        self.high_table = build_sparse_max_table(self.high)
        self.negative_low_table = build_sparse_max_table(-self.low)

    def calculate(self, timestamps) -> pd.DataFrame:
        times = pd.DatetimeIndex(timestamps).drop_duplicates().sort_values()
        start = self.times.get_indexer(times)
        complete = (start >= 0) & (start + OBSERVATION_MINUTES - 1 < len(self.times))
        safe_start = np.maximum(start, 0)
        price = np.where(start >= 0, self.open[safe_start], np.nan)
        end = np.where(complete, start + OBSERVATION_MINUTES - 1, -1)
        left = np.where(complete, start, -1)
        baseline = np.where(
            complete,
            (self.close[np.maximum(end, 0)] / price - 1) * 100,
            np.nan,
        )
        target_hit, target_index = find_first_threshold_hit(
            self.high_table, left, end, price * (1 + TARGET_PCT / 100)
        )
        output = pd.DataFrame(
            {
                "entry_timestamp": times,
                "audit_entry_price": price,
                "stop_window_complete_24h": complete,
                "audit_hold_return_24h_pct": baseline,
                "audit_target_2_5_index": np.where(target_hit, target_index, -1),
            }
        )
        for level in STOP_LEVELS:
            label = stop_label(level)
            stop_price = price * (1 - level / 100)
            hit, hit_index = find_first_threshold_hit(
                self.negative_low_table, left, end, -stop_price
            )
            safe_hit = np.maximum(hit_index, 0)
            fill = np.where(hit, np.minimum(stop_price, self.open[safe_hit]), np.nan)
            stop_return = (fill / price - 1) * 100
            protected_return = np.where(hit, stop_return, baseline)
            outcome = np.full(len(times), "incomplete", object)
            outcome[complete] = "neither"
            outcome[target_hit & ~hit] = "target_only"
            outcome[hit & ~target_hit] = "stop_only"
            outcome[target_hit & hit & (target_index < hit_index)] = "target_first"
            outcome[target_hit & hit & (target_index > hit_index)] = "stop_first"
            outcome[target_hit & hit & (target_index == hit_index)] = "ambiguous_same_minute"
            output[f"stop_{label}_hit"] = pd.array(
                np.where(complete, hit, False), dtype="boolean"
            )
            output.loc[~complete, f"stop_{label}_hit"] = pd.NA
            output[f"stop_{label}_time_minutes"] = np.where(
                hit, hit_index - start + 1, np.nan
            )
            output[f"stop_{label}_fill_return_pct"] = np.where(hit, stop_return, np.nan)
            output[f"stop_{label}_return_24h_pct"] = np.where(
                complete, protected_return, np.nan
            )
            output[f"stop_{label}_paired_change_pp"] = np.where(
                complete, protected_return - baseline, np.nan
            )
            output[f"stop_{label}_target_order"] = outcome
        return output

    def validate_samples(self, result: pd.DataFrame, count: int = 160) -> int:
        complete = result.loc[result.stop_window_complete_24h]
        sample = complete.sample(n=min(count, len(complete)), random_state=1504)
        for row in sample.itertuples(index=False):
            start = self.times.get_loc(row.entry_timestamp)
            price = self.open[start]
            end = start + OBSERVATION_MINUTES
            expected_hold = (self.close[end - 1] / price - 1) * 100
            require(np.isclose(row.audit_entry_price, price), "Entry price mismatch")
            require(
                np.isclose(row.audit_hold_return_24h_pct, expected_hold),
                "Hold return mismatch",
            )
            target = np.flatnonzero(self.high[start:end] >= price * 1.025)
            target_first = target[0] if len(target) else None
            for level in STOP_LEVELS:
                label = stop_label(level)
                hits = np.flatnonzero(self.low[start:end] <= price * (1 - level / 100))
                actual_hit = bool(getattr(row, f"stop_{label}_hit"))
                require(actual_hit == bool(len(hits)), "Stop hit mismatch")
                if not len(hits):
                    expected_return = expected_hold
                    expected_order = "target_only" if target_first is not None else "neither"
                else:
                    offset = int(hits[0])
                    threshold = price * (1 - level / 100)
                    fill = min(threshold, self.open[start + offset])
                    expected_return = (fill / price - 1) * 100
                    if target_first is None:
                        expected_order = "stop_only"
                    elif target_first < offset:
                        expected_order = "target_first"
                    elif target_first > offset:
                        expected_order = "stop_first"
                    else:
                        expected_order = "ambiguous_same_minute"
                    require(
                        getattr(row, f"stop_{label}_time_minutes") == offset + 1,
                        "Stop timing mismatch",
                    )
                require(
                    np.isclose(getattr(row, f"stop_{label}_return_24h_pct"), expected_return),
                    "Protected return mismatch",
                )
                require(
                    getattr(row, f"stop_{label}_target_order") == expected_order,
                    "Target/stop order mismatch",
                )
        return len(sample)
