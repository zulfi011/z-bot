"""Exact raw-minute simulation of time, target, and trailing exits."""

import numpy as np
import pandas as pd

from src.research.target_vs_stop_first_hit import (
    build_sparse_max_table,
    find_first_threshold_hit,
)


HOLD_MINUTES = [15, 30, 60, 120, 240, 480, 720, 1440]
TARGETS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
TRAIL_GIVEBACKS = [20, 30, 40, 50]
TRAIL_ACTIVATION_PCT = 2.5
STOP_PCT = 4.0
WINDOW = 1440
CHUNK_SIZE = 1000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def label(value):
    return f"{value:g}".replace(".", "_")


class ExitEngine:
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
        complete = (start >= 0) & (start + WINDOW - 1 < len(self.times))
        safe_start = np.maximum(start, 0)
        entry = np.where(start >= 0, self.open[safe_start], np.nan)
        end = np.where(complete, start + WINDOW - 1, -1)
        left = np.where(complete, start, -1)
        hold = np.where(
            complete, (self.close[np.maximum(end, 0)] / entry - 1) * 100, np.nan
        )
        stop_price = entry * (1 - STOP_PCT / 100)
        stop_hit, stop_index = find_first_threshold_hit(
            self.negative_low_table, left, end, -stop_price
        )
        safe_stop = np.maximum(stop_index, 0)
        stop_fill = np.where(stop_hit, np.minimum(stop_price, self.open[safe_stop]), np.nan)
        stop_return = (stop_fill / entry - 1) * 100

        output = pd.DataFrame(
            {
                "entry_timestamp": times,
                "exit_audit_entry_price": entry,
                "exit_window_complete_24h": complete,
                "hold_1440m_return_pct": hold,
                "stop_4_hit_index": np.where(stop_hit, stop_index, -1),
                "exit_stop_4_fill_return_pct": np.where(stop_hit, stop_return, np.nan),
            }
        )

        for minutes in HOLD_MINUTES:
            endpoint = start + minutes - 1
            available = (start >= 0) & (endpoint < len(self.times))
            safe_endpoint = np.minimum(np.maximum(endpoint, 0), len(self.times) - 1)
            time_return = np.where(
                available,
                (self.close[safe_endpoint] / entry - 1) * 100,
                np.nan,
            )
            output[f"time_{minutes}_no_stop_return_pct"] = time_return
            output[f"time_{minutes}_no_stop_duration_minutes"] = np.where(
                available, minutes, np.nan
            )
            hit_by_exit = stop_hit & (stop_index <= endpoint)
            protected = np.where(hit_by_exit, stop_return, time_return)
            output[f"time_{minutes}_stop_4_return_pct"] = np.where(
                available, protected, np.nan
            )
            output[f"time_{minutes}_stop_4_duration_minutes"] = np.where(
                hit_by_exit, stop_index - start + 1, np.where(available, minutes, np.nan)
            )
            output[f"time_{minutes}_stop_4_exit_type"] = np.where(
                available, np.where(hit_by_exit, "protective_stop", "time"), "incomplete"
            )

        target_indices = {}
        for target in TARGETS:
            suffix = label(target)
            target_price = entry * (1 + target / 100)
            target_hit, target_index = find_first_threshold_hit(
                self.high_table, left, end, target_price
            )
            target_indices[target] = target_index
            safe_target = np.maximum(target_index, 0)
            target_fill = np.where(
                target_hit, np.maximum(target_price, self.open[safe_target]), np.nan
            )
            target_return = (target_fill / entry - 1) * 100
            no_stop_return = np.where(target_hit, target_return, hold)
            output[f"target_{suffix}_no_stop_return_pct"] = np.where(
                complete, no_stop_return, np.nan
            )
            output[f"target_{suffix}_no_stop_duration_minutes"] = np.where(
                target_hit, target_index - start + 1, np.where(complete, WINDOW, np.nan)
            )
            output[f"target_{suffix}_no_stop_exit_type"] = np.where(
                complete, np.where(target_hit, "profit_target", "time"), "incomplete"
            )

            target_first = target_hit & (~stop_hit | (target_index < stop_index))
            stop_first = stop_hit & (~target_hit | (stop_index < target_index))
            ambiguous = target_hit & stop_hit & (target_index == stop_index)
            combined_return = np.where(target_first, target_return, hold)
            combined_return = np.where(stop_first | ambiguous, stop_return, combined_return)
            combined_duration = np.where(
                target_first,
                target_index - start + 1,
                np.where(stop_first | ambiguous, stop_index - start + 1, WINDOW),
            )
            combined_type = np.full(len(times), "time", object)
            combined_type[target_first] = "profit_target"
            combined_type[stop_first] = "protective_stop"
            combined_type[ambiguous] = "ambiguous_stop"
            combined_type[~complete] = "incomplete"
            output[f"target_{suffix}_stop_4_return_pct"] = np.where(
                complete, combined_return, np.nan
            )
            output[f"target_{suffix}_stop_4_duration_minutes"] = np.where(
                complete, combined_duration, np.nan
            )
            output[f"target_{suffix}_stop_4_exit_type"] = combined_type

        self._attach_trailing(output, start, entry, complete, stop_hit, stop_index, stop_return)
        return output

    def _attach_trailing(self, output, start, entry, complete, stop_hit, stop_index, stop_return):
        size = len(start)
        for giveback in TRAIL_GIVEBACKS:
            for risk in ["no_stop", "stop_4"]:
                prefix = f"trail_{giveback}_{risk}"
                output[f"{prefix}_return_pct"] = np.nan
                output[f"{prefix}_duration_minutes"] = np.nan
                output[f"{prefix}_exit_type"] = "incomplete"
        positions = np.flatnonzero(complete)
        offsets = np.arange(WINDOW)
        for chunk_start in range(0, len(positions), CHUNK_SIZE):
            pos = positions[chunk_start : chunk_start + CHUNK_SIZE]
            indices = start[pos, None] + offsets
            opened = self.open[indices]
            high = self.high[indices]
            low = self.low[indices]
            close = self.close[indices]
            prices = entry[pos]
            activation_mask = high >= prices[:, None] * (1 + TRAIL_ACTIVATION_PCT / 100)
            activated = activation_mask.any(axis=1)
            activation_index = np.where(activated, activation_mask.argmax(axis=1), WINDOW)
            running_peak = np.maximum.accumulate(high, axis=1)
            prior_peak = np.concatenate([prices[:, None], running_peak[:, :-1]], axis=1)
            for giveback in TRAIL_GIVEBACKS:
                trail = prices[:, None] + (prior_peak - prices[:, None]) * (1 - giveback / 100)
                monitor = offsets[None, :] > activation_index[:, None]
                trigger_mask = monitor & (low <= trail)
                triggered = trigger_mask.any(axis=1)
                trigger_index = np.where(triggered, trigger_mask.argmax(axis=1), WINDOW - 1)
                row = np.arange(len(pos))
                trail_fill = np.minimum(trail[row, trigger_index], opened[row, trigger_index])
                trail_return = (trail_fill / prices - 1) * 100
                no_stop_return = np.where(
                    triggered, trail_return, (close[:, -1] / prices - 1) * 100
                )
                no_stop_duration = np.where(triggered, trigger_index + 1, WINDOW)
                no_stop_type = np.where(triggered, "trailing_stop", "time")

                for risk in ["no_stop", "stop_4"]:
                    prefix = f"trail_{giveback}_{risk}"
                    if risk == "no_stop":
                        result_return = no_stop_return
                        duration = no_stop_duration
                        exit_type = no_stop_type
                    else:
                        raw_stop = stop_hit[pos]
                        stop_at = stop_index[pos] - start[pos]
                        initial_first = raw_stop & (stop_at <= activation_index)
                        ambiguous = raw_stop & activated & (stop_at == activation_index)
                        result_return = np.where(initial_first, stop_return[pos], no_stop_return)
                        duration = np.where(initial_first, stop_at + 1, no_stop_duration)
                        exit_type = np.where(initial_first, "protective_stop", no_stop_type).astype(object)
                        exit_type[ambiguous] = "ambiguous_stop"
                    output.loc[pos, f"{prefix}_return_pct"] = result_return
                    output.loc[pos, f"{prefix}_duration_minutes"] = duration
                    output.loc[pos, f"{prefix}_exit_type"] = exit_type

    def validate_samples(self, result: pd.DataFrame, count: int = 120) -> int:
        sample = result.loc[result.exit_window_complete_24h]
        sample = sample.sample(n=min(count, len(sample)), random_state=1505)
        for row in sample.itertuples(index=False):
            start = self.times.get_loc(row.entry_timestamp)
            entry = self.open[start]
            highs = self.high[start : start + WINDOW]
            lows = self.low[start : start + WINDOW]
            opens = self.open[start : start + WINDOW]
            closes = self.close[start : start + WINDOW]
            require(np.isclose(row.exit_audit_entry_price, entry), "Entry mismatch")
            require(
                np.isclose(row.hold_1440m_return_pct, (closes[-1] / entry - 1) * 100),
                "Hold mismatch",
            )
            stops = np.flatnonzero(lows <= entry * 0.96)
            stop_at = int(stops[0]) if len(stops) else None
            stop_value = None if stop_at is None else (
                min(entry * 0.96, opens[stop_at]) / entry - 1
            ) * 100
            for minutes in HOLD_MINUTES:
                expected = (closes[minutes - 1] / entry - 1) * 100
                require(
                    np.isclose(getattr(row, f"time_{minutes}_no_stop_return_pct"), expected),
                    "Time exit mismatch",
                )
                if stop_at is not None and stop_at < minutes:
                    expected = stop_value
                require(
                    np.isclose(getattr(row, f"time_{minutes}_stop_4_return_pct"), expected),
                    "Protected time exit mismatch",
                )
            for target in TARGETS:
                suffix = label(target)
                hits = np.flatnonzero(highs >= entry * (1 + target / 100))
                target_at = int(hits[0]) if len(hits) else None
                target_value = None if target_at is None else (
                    max(entry * (1 + target / 100), opens[target_at]) / entry - 1
                ) * 100
                expected = target_value if target_at is not None else (closes[-1] / entry - 1) * 100
                require(
                    np.isclose(getattr(row, f"target_{suffix}_no_stop_return_pct"), expected),
                    "Target exit mismatch",
                )
                if stop_at is not None and (target_at is None or stop_at <= target_at):
                    expected = stop_value
                require(
                    np.isclose(getattr(row, f"target_{suffix}_stop_4_return_pct"), expected),
                    "Target/stop exit mismatch",
                )
            for giveback in TRAIL_GIVEBACKS:
                expected_return, expected_duration, expected_type = self._reference_trail(
                    highs, lows, opens, closes, entry, giveback
                )
                require(
                    np.isclose(getattr(row, f"trail_{giveback}_no_stop_return_pct"), expected_return),
                    "Trailing return mismatch",
                )
                require(
                    getattr(row, f"trail_{giveback}_no_stop_duration_minutes") == expected_duration,
                    "Trailing duration mismatch",
                )
                require(
                    getattr(row, f"trail_{giveback}_no_stop_exit_type") == expected_type,
                    "Trailing type mismatch",
                )
                if stop_at is not None and (
                    expected_type == "time"
                    or stop_at <= self._activation_index(highs, entry)
                ):
                    combined_return = stop_value
                    combined_duration = stop_at + 1
                    combined_type = (
                        "ambiguous_stop"
                        if stop_at == self._activation_index(highs, entry)
                        else "protective_stop"
                    )
                else:
                    combined_return = expected_return
                    combined_duration = expected_duration
                    combined_type = expected_type
                require(
                    np.isclose(getattr(row, f"trail_{giveback}_stop_4_return_pct"), combined_return),
                    "Protected trailing return mismatch",
                )
                require(
                    getattr(row, f"trail_{giveback}_stop_4_duration_minutes") == combined_duration,
                    "Protected trailing duration mismatch",
                )
                require(
                    getattr(row, f"trail_{giveback}_stop_4_exit_type") == combined_type,
                    "Protected trailing type mismatch",
                )
        return len(sample)

    @staticmethod
    def _activation_index(highs, entry):
        hits = np.flatnonzero(highs >= entry * 1.025)
        return int(hits[0]) if len(hits) else WINDOW

    @staticmethod
    def _reference_trail(highs, lows, opens, closes, entry, giveback):
        activation = None
        for index, high in enumerate(highs):
            if high >= entry * 1.025:
                activation = index
                break
        if activation is None:
            return (closes[-1] / entry - 1) * 100, WINDOW, "time"
        peak = highs[: activation + 1].max()
        for index in range(activation + 1, WINDOW):
            trail = entry + (peak - entry) * (1 - giveback / 100)
            if lows[index] <= trail:
                fill = min(trail, opens[index])
                return (fill / entry - 1) * 100, index + 1, "trailing_stop"
            peak = max(peak, highs[index])
        return (closes[-1] / entry - 1) * 100, WINDOW, "time"
