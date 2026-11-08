from pathlib import Path
import sys

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_sol_full_ma_signal_exit_grid import (  # noqa: E402
    ACTIVATIONS,
    GIVEBACKS,
    STOPS,
    ThresholdIndex,
    precompute_outcomes,
)


def test_threshold_index_matches_first_raw_crossing():
    high = np.array([10.0, 11.0, 9.0, 14.0, 12.0])
    low = np.array([9.0, 8.0, 7.0, 11.0, 6.0])
    index = ThresholdIndex(high, low)
    assert index.first_ge(1, 13.0) == 3
    assert index.first_ge(4, 13.0) == -1
    assert index.first_le(2, 6.5) == 4
    assert index.first_le(0, 7.5) == 2


def test_activation_candle_cannot_trail_and_same_candle_stop_wins():
    arrays = {
        "open": np.array([100.0, 104.0, 104.0]),
        "high": np.array([104.0, 105.0, 105.0]),
        "low": np.array([100.0, 103.0, 104.0]),
        "close": np.array([104.0, 104.0, 104.0]),
    }
    fills = pd.DataFrame([{"entry_index": 0, "entry_fill": 100.0}])
    index = ThresholdIndex(arrays["high"], arrays["low"])
    exits, prices, kinds = precompute_outcomes(fills, arrays, index)
    ai = ACTIVATIONS.index(4.0)
    gi = GIVEBACKS.index(20.0)
    si = STOPS.index(3.0)
    assert exits[0, ai, gi, si] == 1
    assert prices[0, ai, gi, si] == 103.2
    assert kinds[0, ai, gi, si] == 1

    arrays["low"][0] = 96.0
    index = ThresholdIndex(arrays["high"], arrays["low"])
    exits, prices, kinds = precompute_outcomes(fills, arrays, index)
    assert exits[0, ai, gi, si] == 0
    assert prices[0, ai, gi, si] == 97.0
    assert kinds[0, ai, gi, si] == 3
