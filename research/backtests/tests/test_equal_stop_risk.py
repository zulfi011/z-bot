import numpy as np
import pandas as pd

from experiments.eth_canonical_v1.engine import CandidateTrade, MarketData, PortfolioConfig, replay_portfolio
from experiments.eth_canonical_v1.equal_stop_risk import equal_risk_sizer, gap_stress


def test_equal_risk_sizer_inverts_stop_distance_and_honours_cap():
    stops = {"dip": 4.5, "pullback": 4.5, "breakout": 3.5}
    size = equal_risk_sizer(stops, risk_usd=4.5, maximum_order_usd=130)
    dip = CandidateTrade(0, 1, 100, "dip", 1, "dip")
    breakout = CandidateTrade(0, 1, 100, "breakout", 1, "breakout")
    assert np.isclose(size(dip), 100.0)
    assert np.isclose(size(breakout), 128.57142857142858)


def test_variable_lots_cannot_borrow_from_shared_wallet():
    times = pd.date_range("2025-01-01", periods=4, freq="min", tz="UTC")
    market = MarketData(times, np.full(4, 100.0), np.full(4, 100.0))
    candidates = [
        CandidateTrade(0, 3, 100.0, "breakout", 1, "a"),
        CandidateTrade(0, 3, 100.0, "breakout", 1, "b"),
    ]
    config = PortfolioConfig(initial_capital=200, lot_size=100, maximum_lots=2,
                             fee_per_side=0, slippage_per_side=0, mark_frequency_minutes=1)
    result = replay_portfolio(candidates, market, times[0], times[-1] + pd.Timedelta(minutes=1),
                              config, lot_sizer=lambda _candidate: 130.0)
    assert result.trades.spend.tolist() == [130.0, 70.0]
    assert np.isclose(result.trades.spend.sum(), 200.0)


def test_gap_stress_changes_only_protective_stop_exit_prices():
    stopped = CandidateTrade(0, 1, 95.0, "dip", 2, "stop", exit_kind="protective_stop")
    winner = CandidateTrade(0, 1, 105.0, "dip", 1, "win", exit_kind="strategy_exit")
    stressed = gap_stress([stopped, winner], 50)
    assert np.isclose(stressed[0].exit_price, 95.0 * 0.995)
    assert stressed[1].exit_price == 105.0
