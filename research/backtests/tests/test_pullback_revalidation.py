import pandas as pd

from experiments.eth_canonical_v1.pullback_revalidation import _excluded_month_mask


def test_april_may_exclusion_uses_filled_trade_entry_month():
    trades = pd.DataFrame({"entry_time": pd.to_datetime([
        "2025-03-31T23:59:00Z", "2025-04-01T00:00:00Z",
        "2025-05-31T23:59:00Z", "2025-06-01T00:00:00Z",
    ])})
    mask = _excluded_month_mask(trades, ["2025-04", "2025-05"])
    assert mask.tolist() == [False, True, True, False]
