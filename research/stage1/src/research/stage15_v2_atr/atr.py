"""Causal hourly Wilder ATR derived from raw one-minute candles."""

import numpy as np
import pandas as pd


def require(condition, message):
    if not condition:
        raise ValueError(message)


def hourly_candles(raw):
    indexed = raw.set_index("open_time")
    output = indexed.resample("1h", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), count=("close", "size"),
    ).reset_index()
    require(output["count"].eq(60).all(), "Incomplete hourly candle")
    return output


def wilder_atr(candles, periods=14):
    previous_close = candles.close.shift(1)
    true_range = pd.concat([
        candles.high - candles.low,
        (candles.high - previous_close).abs(),
        (candles.low - previous_close).abs(),
    ], axis=1).max(axis=1).to_numpy(float)
    atr = np.full(len(candles), np.nan)
    if len(candles) >= periods:
        atr[periods - 1] = true_range[:periods].mean()
        for index in range(periods, len(candles)):
            atr[index] = (atr[index - 1] * (periods - 1) + true_range[index]) / periods
    return atr, true_range


def attach_entry_atr(entries, hourly, atr_values):
    completed_hour = pd.DatetimeIndex(entries).floor("1h") - pd.Timedelta("1h")
    hourly_times = pd.DatetimeIndex(hourly.open_time)
    index = hourly_times.get_indexer(completed_hour)
    values = np.where(index >= 0, atr_values[np.maximum(index, 0)], np.nan)
    return pd.DataFrame({"entry_timestamp": pd.DatetimeIndex(entries),
                         "atr_reference_hour": completed_hour, "atr_14_1h": values})

