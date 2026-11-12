import numpy as np
import pandas as pd

from experiments.eth_canonical_v1.execution_calibration import TEMPLATE_COLUMNS, observed_scenarios


def test_observed_scenarios_refuse_to_invent_missing_data(tmp_path):
    scenarios, status = observed_scenarios(tmp_path / "missing.csv", minimum=30)
    assert scenarios == []
    assert status["status"] == "missing"


def test_observed_scenarios_require_minimum_complete_real_fills(tmp_path):
    path = tmp_path / "fills.csv"
    rows = []
    for index in range(5):
        row = dict.fromkeys(TEMPLATE_COLUMNS)
        row.update(symbol="ETHUSDT", side="buy", status="filled", fee_rate_bps=7.5,
                   next_open_slippage_bps=index, order_latency_ms=100 + index,
                   recovered_retry=False)
        rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False)
    scenarios, status = observed_scenarios(path, minimum=30)
    assert scenarios == []
    assert status == {"status": "insufficient", "fills": 5,
                      "reason": "Need 30 complete real ETH fills; found 5"}


def test_observed_percentiles_use_adverse_slippage_only(tmp_path):
    path = tmp_path / "fills.csv"
    rows = []
    for index in range(30):
        row = dict.fromkeys(TEMPLATE_COLUMNS)
        row.update(symbol="ETHUSDT", side="buy" if index % 2 == 0 else "sell", status="filled",
                   fee_rate_bps=7 + index / 10, next_open_slippage_bps=index - 5,
                   order_latency_ms=50 + index, recovered_retry=index == 0)
        rows.append(row)
    rejected = dict.fromkeys(TEMPLATE_COLUMNS)
    rejected.update(symbol="ETHUSDT", side="buy", status="rejected", recovered_retry=False)
    rows.append(rejected)
    pd.DataFrame(rows).to_csv(path, index=False)
    scenarios, status = observed_scenarios(path, minimum=30)
    assert [scenario["name"] for scenario in scenarios] == ["observed_median", "observed_p90", "observed_worst"]
    assert np.isclose(scenarios[0]["slippage_bps_per_side"], 9.5)
    assert scenarios[-1]["slippage_bps_per_side"] == 24
    assert status["rejected_orders"] == 1 and status["recovered_retries"] == 1
