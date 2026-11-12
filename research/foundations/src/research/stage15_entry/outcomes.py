"""Reprice every candidate at the next 1m open; measure exact forward windows."""

import numpy as np
import pandas as pd

from src.research.target_vs_stop_first_hit import build_sparse_max_table, range_max, find_first_threshold_hit
from .signals import require

HORIZONS = [5, 15, 30, 60, 240, 1440]
WINDOWS = [60, 240, 1440]
STOPS = [1., 1.5, 2., 2.5, 3.]


class OutcomeEngine:
    def __init__(self, raw):
        self.raw = raw
        self.times = pd.DatetimeIndex(raw.open_time)
        require(self.times.is_unique and self.times.is_monotonic_increasing and str(self.times.tz) == "UTC", "Invalid raw timestamps")
        require((self.times[1:] - self.times[:-1] == pd.Timedelta('1min')).all(), "Raw 1m gaps")
        self.open = raw.open.to_numpy(float)
        self.close = raw.close.to_numpy(float)
        self.high = raw.high.to_numpy(float)
        self.low = raw.low.to_numpy(float)
        require(np.isfinite(raw[['open','high','low','close']].to_numpy()).all(), "Missing raw prices")
        require((self.low <= self.open).all() and (self.high >= self.open).all() and (self.low > 0).all(), "Invalid raw OHLC")
        self.high_table = build_sparse_max_table(self.high)
        self.negative_low_table = build_sparse_max_table(-self.low)

    def calculate(self, timestamps):
        times = pd.DatetimeIndex(timestamps).drop_duplicates().sort_values()
        start = self.times.get_indexer(times)
        available = start >= 0
        safe = np.maximum(start, 0)
        price = np.where(available, self.open[safe], np.nan)
        output = pd.DataFrame({'entry_timestamp': times, 'entry_price': price, 'entry_available': available})
        for horizon in HORIZONS:
            end = start + horizon - 1
            complete = available & (end < len(self.times))
            endpoint = np.minimum(np.maximum(end, 0), len(self.times)-1)
            output[f'return_{horizon}m_pct'] = np.where(complete, (self.close[endpoint]/price-1)*100, np.nan)
        for window in WINDOWS:
            end = start + window - 1
            complete = available & (end < len(self.times))
            left = np.where(complete, start, -1)
            right = np.where(complete, end, -1)
            high = range_max(self.high_table, left, right)
            low = -range_max(self.negative_low_table, left, right)
            output[f'mae_{window}m_pct'] = (low/price-1)*100
            output[f'mfe_{window}m_pct'] = (high/price-1)*100
        end = start + 1439
        complete = available & (end < len(self.times))
        output['complete_24h'] = complete
        left, right = np.where(complete, start, -1), np.where(complete, end, -1)
        target_hit, target_index = find_first_threshold_hit(self.high_table, left, right, price*1.025)
        output['target_2_5_reached'] = pd.array(np.where(complete, target_hit, False), dtype='boolean')
        output.loc[~complete, 'target_2_5_reached'] = pd.NA
        output['target_time_minutes'] = np.where(target_hit, target_index-start+1, np.nan)
        for stop in STOPS:
            hit, index = find_first_threshold_hit(self.negative_low_table, left, right, -price*(1-stop/100))
            value = np.full(len(times), 'incomplete', object)
            value[complete] = 'neither'
            value[target_hit & ~hit] = 'target_first'
            value[hit & ~target_hit] = 'stop_first'
            value[target_hit & hit & (target_index < index)] = 'target_first'
            value[target_hit & hit & (target_index > index)] = 'stop_first'
            value[target_hit & hit & (target_index == index)] = 'ambiguous'
            output[f'first_{stop:g}'] = value
        return output

    def validate_samples(self, result, count=160):
        sample = result.loc[result.complete_24h]
        sample = sample.sample(n=min(count, len(sample)), random_state=1502)
        for row in sample.itertuples(index=False):
            start = self.times.get_loc(row.entry_timestamp)
            price = self.open[start]
            require(row.entry_price == price, 'Entry is not next 1m open')
            actual = result.loc[result.entry_timestamp.eq(row.entry_timestamp)].iloc[0]
            for horizon in HORIZONS:
                expected = (self.close[start+horizon-1]/price-1)*100
                require(np.isclose(actual[f'return_{horizon}m_pct'], expected, rtol=1e-12, atol=1e-12), 'Forward timing mismatch')
            for window in WINDOWS:
                require(np.isclose(actual[f'mae_{window}m_pct'], (self.low[start:start+window].min()/price-1)*100), 'MAE mismatch')
                require(np.isclose(actual[f'mfe_{window}m_pct'], (self.high[start:start+window].max()/price-1)*100), 'MFE mismatch')
            highs = self.high[start:start+1440]
            lows = self.low[start:start+1440]
            target = np.flatnonzero(highs >= price*1.025)
            require(bool(actual.target_2_5_reached) == bool(len(target)), 'Target reach mismatch')
            for stop in STOPS:
                hits = np.flatnonzero(lows <= price*(1-stop/100))
                t = target[0] if len(target) else np.inf
                s = hits[0] if len(hits) else np.inf
                expected = 'neither' if t == s == np.inf else ('ambiguous' if t == s else ('target_first' if t < s else 'stop_first'))
                require(actual[f'first_{stop:g}'] == expected, 'First-hit mismatch')
        return len(sample)
