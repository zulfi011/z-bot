import numpy as np
import pandas as pd

from experiments.eth_canonical_v1.portfolio_risk import (
    CoinMarket, PortfolioCandidate, RiskLimits, assign_common_episodes,
    replay_shared_wallet,
)


def candidate(coin, times, entry, exit_at, exit_price, kind="strategy_exit"):
    return PortfolioCandidate(
        coin, entry, exit_at, exit_price, "dip", kind, f"{coin}:{entry}",
        times[entry], times[exit_at],
    )


def setup():
    times = pd.date_range("2025-01-01", periods=12, freq="min", tz="UTC")
    market = CoinMarket(times, np.full(12, 100.0), np.full(12, 100.0))
    config = {
        "wallet": {"initial_capital_usd": 200.0, "lot_size_usd": 100.0,
                   "per_coin_maximum_lots": {"ETH": 1, "BTC": 1}},
        "costs": {"fee_bps_per_side": 0.0, "slippage_bps_per_side": 0.0},
    }
    return times, {"ETH": market, "BTC": market}, config


def test_common_episode_uses_cross_coin_time_gap():
    times, _, _ = setup()
    book = [candidate("ETH", times, 0, 2, 101), candidate("BTC", times, 5, 7, 101),
            candidate("ETH", times, 11, 11, 101)]
    grouped = assign_common_episodes(book, maximum_gap_minutes=5)
    assert [item.market_episode for item in grouped] == ["crypto:0001", "crypto:0001", "crypto:0002"]


def test_episode_coin_cap_blocks_correlated_second_coin():
    times, markets, config = setup()
    book = assign_common_episodes(
        [candidate("ETH", times, 0, 8, 101), candidate("BTC", times, 1, 9, 101)], 5
    )
    result = replay_shared_wallet(markets, book, times[0], times[-1] + pd.Timedelta(minutes=1),
                                  config, RiskLimits(200, maximum_coins_per_episode=1))
    assert result[0]["trades"] == 1
    assert result[2].iloc[0].reason == "correlated_episode_coins"


def test_protective_stops_receive_synchronized_stress_slippage():
    times, markets, config = setup()
    book = assign_common_episodes(
        [candidate("ETH", times, 0, 2, 95, "protective_stop"),
         candidate("BTC", times, 3, 5, 101, "strategy_exit")], 5
    )
    base = replay_shared_wallet(markets, book, times[0], times[-1] + pd.Timedelta(minutes=1),
                                config, RiskLimits(200))[0]
    stress = replay_shared_wallet(markets, book, times[0], times[-1] + pd.Timedelta(minutes=1),
                                  config, RiskLimits(200, extra_stop_slippage_bps=50))[0]
    assert stress["net_profit"] < base["net_profit"]
    assert np.isclose(base["net_profit"] - stress["net_profit"], 0.475)
