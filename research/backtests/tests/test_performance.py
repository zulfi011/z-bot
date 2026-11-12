import numpy as np
import pandas as pd

from src.backtesting.performance import calculate_performance, daily_equity_curve


def test_calculates_trade_and_drawdown_metrics():
    times = pd.date_range("2026-01-01", periods=4, freq="1D", tz="UTC")
    curve = pd.DataFrame({
        "timestamp": times,
        "total_equity_usd": [100, 110, 88, 105],
        "drawdown_pct": [0, 0, -20, -4.545454545],
    })
    trades = pd.DataFrame({
        "trade_id": ["a", "b", "c"],
        "net_profit_usd": [10, -22, 17],
        "net_return_pct": [10, -20, 19.318181818],
    })
    metrics = calculate_performance(trades, curve, 100)
    assert metrics["final_equity_usd"] == 105
    assert metrics["win_rate_pct"] == 2 / 3 * 100
    assert np.isclose(metrics["profit_factor"], 27 / 22)
    assert metrics["max_drawdown_pct"] == -20
    assert metrics["max_drawdown_usd"] == -22
    assert metrics["worst_trade_id"] == "b"
    assert metrics["drawdown_recovered"] is False


def test_daily_curve_keeps_last_snapshot_each_day():
    times = pd.to_datetime([
        "2026-01-01T00:01Z", "2026-01-01T23:59Z", "2026-01-02T23:59Z"
    ])
    frame = pd.DataFrame({
        "timestamp": times,
        "cash_usd": [100, 90, 105], "open_position_value_usd": [0, 10, 0],
        "realized_pnl_usd": [0, 0, 5], "unrealized_pnl_usd": [0, 0, 0],
        "total_equity_usd": [100, 100, 105], "drawdown_pct": [0, 0, 0],
        "open_positions": [0, 1, 0],
    })
    daily = daily_equity_curve(frame)
    assert len(daily) == 2
    assert daily.iloc[0].cash_usd == 90
    assert daily.iloc[1].total_equity_usd == 105

