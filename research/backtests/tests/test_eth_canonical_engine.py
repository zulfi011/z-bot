from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from experiments.eth_canonical_v1.engine import (
    CandidateTrade,
    MarketData,
    PortfolioConfig,
    replay_portfolio,
)


# Some tests rebuild the real ETH history: they need `python research/download_data.py ETHUSDT` first.
ETH_RAW = Path(__file__).resolve().parents[2] / "foundations" / "data" / "raw" / "ETHUSDT" / "ETHUSDT_1m.parquet"
needs_eth_data = pytest.mark.skipif(not ETH_RAW.exists(),
                                    reason="needs the ETH price data: python research/download_data.py ETHUSDT")


def market(minutes: int = 10, price: float = 100.0) -> MarketData:
    times = pd.date_range("2026-01-01", periods=minutes, freq="min", tz="UTC")
    return MarketData(times, np.full(minutes, price), np.full(minutes, price))


def config(lots: int = 1) -> PortfolioConfig:
    return PortfolioConfig(
        initial_capital=100.0 * lots, lot_size=100.0, maximum_lots=lots,
        fee_per_side=0.0, slippage_per_side=0.0, mark_frequency_minutes=1,
    )


def trade(entry: int, exit_: int, price: float, name: str = "a") -> CandidateTrade:
    return CandidateTrade(entry, exit_, price, "dip", 1, name)


def test_truncates_a_trade_at_the_window_boundary() -> None:
    data = market()
    result = replay_portfolio(
        [trade(1, 8, 150.0)], data, data.times[0], data.times[5], config()
    )
    row = result.trades.iloc[0]
    assert bool(row.endpoint_closed)
    assert row.exit_index == 4
    assert row.exit_raw_price == 100.0
    assert row.pnl == pytest.approx(0.0)


def test_marks_open_positions_instead_of_holding_them_at_cost() -> None:
    data = market()
    data.close[2:5] = 90.0
    result = replay_portfolio(
        [trade(1, 5, 100.0)], data, data.times[0], data.times[8], config()
    )
    assert result.summary["maximum_drawdown_pct"] == pytest.approx(-10.0)


def test_logs_a_candidate_blocked_by_an_occupied_slot() -> None:
    data = market()
    result = replay_portfolio(
        [trade(1, 5, 100.0, "first"), trade(2, 4, 110.0, "blocked")],
        data, data.times[0], data.times[-1] + pd.Timedelta(minutes=1), config(),
    )
    assert result.summary["trades"] == 1
    assert result.summary["blocked_candidates"] == 1
    assert result.blocked_signals.iloc[0].reason == "all_slots_open"


def test_same_minute_order_is_stable() -> None:
    data = market()
    candidates = [trade(1, 4, 110.0, "first"), trade(1, 3, 120.0, "second")]
    result = replay_portfolio(
        candidates, data, data.times[0], data.times[-1] + pd.Timedelta(minutes=1), config()
    )
    assert result.trades.iloc[0].candidate_id == "first"
    assert result.blocked_signals.iloc[0].candidate_id == "second"


def test_entry_policy_only_counts_filled_candidates() -> None:
    data = market()
    candidates = [trade(1, 3, 100.0, "first"), trade(2, 3, 100.0, "slot-blocked"),
                  trade(4, 6, 100.0, "policy-blocked")]

    def one_fill(_candidate, filled, _open_lots):
        return "policy_cap" if filled else None

    result = replay_portfolio(
        candidates, data, data.times[0], data.times[-1] + pd.Timedelta(minutes=1), config(), one_fill
    )
    assert list(result.blocked_signals.reason) == ["all_slots_open", "policy_cap"]


def test_allocation_priority_only_reorders_the_same_minute() -> None:
    from experiments.eth_canonical_v1.allocation import prioritize

    candidates = [
        CandidateTrade(1, 3, 100.0, "dip", 1, "dip"),
        CandidateTrade(1, 3, 100.0, "pullback", 1, "pullback"),
        CandidateTrade(2, 3, 100.0, "breakout", 1, "breakout"),
    ]
    ordered = prioritize(candidates, ["pullback", "dip", "breakout"])
    assert [candidate.candidate_id for candidate in ordered] == ["pullback", "dip", "breakout"]


def test_final_slot_reservation_blocks_only_bullish_non_pullbacks() -> None:
    from experiments.eth_canonical_v1.allocation import reserve_final_slot

    policy = reserve_final_slot(5)
    open_lots = [{}, {}, {}, {}]
    dip = CandidateTrade(1, 3, 100.0, "dip", 1, "dip", bullish_entry=True)
    pullback = CandidateTrade(1, 3, 100.0, "pullback", 1, "pullback", bullish_entry=True)
    bearish_dip = CandidateTrade(1, 3, 100.0, "dip", 1, "bearish", bullish_entry=False)
    assert policy(dip, [], open_lots) == "allocation_final_slot_reserved_for_pullback"
    assert policy(pullback, [], open_lots) is None
    assert policy(bearish_dip, [], open_lots) is None


def test_monthly_profit_includes_zero_trade_months() -> None:
    from experiments.eth_canonical_v1.concentration import monthly_profit

    trades = pd.DataFrame({
        "exit_time": pd.to_datetime(["2026-01-05T00:00:00Z", "2026-03-05T00:00:00Z"]),
        "pnl": [10.0, -2.0],
    })
    result = monthly_profit(
        trades, pd.Timestamp("2026-01-01", tz="UTC"), pd.Timestamp("2026-04-01", tz="UTC")
    )
    assert list(result) == [10.0, 0.0, -2.0]


def test_drawdown_recovery_marks_unrecovered_tail() -> None:
    from experiments.eth_canonical_v1.concentration import drawdown_recoveries

    timestamps = pd.date_range("2026-01-01", periods=6, freq="h", tz="UTC")
    values = np.array([100.0, 90.0, 100.0, 95.0, 94.0, 96.0])
    peaks = np.maximum.accumulate(values)
    equity = pd.DataFrame({
        "timestamp": timestamps, "drawdown_usd": values - peaks,
        "drawdown_pct": 100 * (values / peaks - 1),
    })
    result = drawdown_recoveries(equity)
    assert list(result.recovered) == [True, False]
    assert result.iloc[0].duration_days == pytest.approx(1 / 24)
    assert result.iloc[1].duration_days == pytest.approx(2 / 24)


def test_moving_block_bootstrap_is_reproducible() -> None:
    from experiments.eth_canonical_v1.overfitting import moving_block_bootstrap

    values = np.array([1.0, 2.0, 3.0, 4.0])
    first = moving_block_bootstrap(values, block_length=2, samples=20, seed=7)
    second = moving_block_bootstrap(values, block_length=2, samples=20, seed=7)
    assert np.array_equal(first, second)
    assert len(first) == 20


def test_cscv_pbo_detects_unstable_selection() -> None:
    from experiments.eth_canonical_v1.overfitting import cscv_pbo

    # Each strategy wins one block and loses its complementary block. Selecting the
    # in-sample winner therefore puts it below the median out of sample.
    matrix = np.array([
        [10.0, 0.0, 0.0, 0.0],
        [0.0, 10.0, 0.0, 0.0],
        [-10.0, 0.0, 0.0, 0.0],
        [0.0, -10.0, 0.0, 0.0],
    ])
    pbo, splits = cscv_pbo(matrix)
    assert len(splits) == 6
    assert pbo > 0


def test_economic_trade_classes_keep_boundary_values_flat() -> None:
    from experiments.eth_canonical_v1.trade_quality import classify_returns

    returns = pd.Series([-0.26, -0.25, 0.0, 0.25, 0.26])
    assert list(classify_returns(returns, 0.25)) == ["loser", "flat", "flat", "flat", "winner"]


@needs_eth_data
def test_fee_floor_builder_restores_the_canonical_floor() -> None:
    from experiments.eth_canonical_v1 import baseline as baseline_module
    from experiments.eth_canonical_v1.fee_floor import build_with_floor

    original = baseline_module.floor_arm.COSTS
    _, candidates, _ = build_with_floor(0.24)
    assert candidates
    assert baseline_module.floor_arm.COSTS == original


def test_risk_policy_blocks_when_the_unarmed_cap_is_full() -> None:
    from experiments.eth_canonical_v1.risk_throttle import risk_policy

    data = market()
    candidate = CandidateTrade(2, 5, 100.0, "dip", 1, "next")
    open_lot = {"arm_index": None, "quantity": 1.0, "spend": 100.0,
                "entry_index": 0, "exit_index": 5, "pnl": 0.0, "market_episode": "one"}
    policy = risk_policy(data, config(), np.zeros(len(data.times), dtype=bool), maximum_unarmed=1)
    assert policy(candidate, [open_lot], [open_lot]) == "risk_maximum_unarmed_1"


def test_risk_policy_uses_marked_open_losses() -> None:
    from experiments.eth_canonical_v1.risk_throttle import risk_policy

    data = market()
    data.close[1] = 90.0
    candidate = CandidateTrade(2, 5, 100.0, "dip", 1, "next")
    open_lot = {"arm_index": None, "quantity": 1.0, "spend": 100.0,
                "entry_index": 0, "exit_index": 5, "pnl": 0.0, "market_episode": "one"}
    policy = risk_policy(data, config(), np.zeros(len(data.times), dtype=bool), total_open_loss=5.0)
    assert policy(candidate, [open_lot], [open_lot]) == "risk_total_open_loss"


def test_failure_checkpoint_uses_the_next_completed_five_minute_candle() -> None:
    from experiments.eth_canonical_v1.failure_exit import checkpoint_index

    times = pd.date_range("2026-01-01 00:00", periods=500, freq="min", tz="UTC")
    # Entry 00:02 + 6h = 06:02. The first 5m candle completed after that ends 06:05,
    # whose final constituent minute opens at 06:04.
    assert checkpoint_index(times, 2, 6) == 364


def test_forward_complete_month_count_requires_whole_utc_months() -> None:
    from experiments.eth_canonical_v1.forward_challengers import complete_utc_months

    start = pd.Timestamp("2026-10-01", tz="UTC")
    assert complete_utc_months(start, pd.Timestamp("2026-10-31 23:59", tz="UTC")) == 0
    assert complete_utc_months(start, pd.Timestamp("2026-11-01", tz="UTC")) == 1
    assert complete_utc_months(start, pd.Timestamp("2027-01-01", tz="UTC")) == 3


def test_unarmed_timeout_preserves_armed_and_closed_candidates() -> None:
    from experiments.eth_canonical_v1.time_to_arm import apply_unarmed_timeout

    data = market(500)
    candidates = [
        CandidateTrade(2, 490, 110.0, "dip", 1, "unarmed", arm_index=None),
        CandidateTrade(2, 490, 110.0, "dip", 1, "armed", arm_index=100),
        CandidateTrade(2, 200, 110.0, "dip", 1, "closed", arm_index=None),
    ]
    changed, eligible = apply_unarmed_timeout(candidates, data, 6)
    assert changed[0].exit_kind == "unarmed_timeout"
    assert changed[0].exit == 365
    assert changed[1] == candidates[1]
    assert changed[2] == candidates[2]
    assert eligible.candidate_id.tolist() == ["unarmed"]


def test_path_failure_requires_both_weak_mfe_and_large_mae() -> None:
    from experiments.eth_canonical_v1 import baseline as baseline_module
    from experiments.eth_canonical_v1.mfe_mae_path import apply_path_failure

    data = market(500)
    baseline_module.grid.OPEN = data.open.copy()
    baseline_module.grid.HIGH = np.full(500, 100.1)
    baseline_module.grid.LOW = np.full(500, 97.5)
    baseline_module.grid.SLIP = 0.0
    candidates = [CandidateTrade(2, 490, 110.0, "dip", 1, "failed", arm_index=None)]
    changed, eligible = apply_path_failure(candidates, data, 6, 0.25, 2.0)
    assert changed[0].exit_kind == "path_failure"
    assert eligible.candidate_id.tolist() == ["failed"]


def test_monthly_sizer_freezes_target_and_marks_open_positions() -> None:
    from experiments.eth_canonical_v1.monthly_compounding import monthly_equity_sizer

    data = MarketData(
        pd.date_range("2026-01-01", periods=32 * 24 * 60, freq="min", tz="UTC"),
        np.full(32 * 24 * 60, 100.0), np.full(32 * 24 * 60, 100.0),
    )
    portfolio = config(lots=5)
    sizer = monthly_equity_sizer(data, portfolio, 0.20, 70.0, 130.0, False)
    january = CandidateTrade(1, 10, 100.0, "dip", 1, "jan")
    february_index = 31 * 24 * 60
    february = CandidateTrade(february_index, february_index + 5, 100.0, "dip", 1, "feb")
    assert sizer(january, [], []) == pytest.approx(100.0)
    closed = [{"entry_index": 1, "exit_index": 10, "pnl": 50.0,
               "quantity": 1.0, "spend": 100.0}]
    assert sizer(february, closed, []) == pytest.approx(110.0)


def test_continuous_compounding_sizer_marks_open_positions_at_entry() -> None:
    from experiments.eth_canonical_v1.continuous_compounding import (
        continuous_equity_sizer,
    )

    data = market(10)
    data.close[2] = 90.0
    portfolio = config(lots=5)
    sizer = continuous_equity_sizer(data, portfolio)
    candidate = CandidateTrade(2, 8, 100.0, "dip", 1, "next")
    open_lot = {"entry_index": 1, "exit_index": 8, "quantity": 1.0, "spend": 100.0, "pnl": 0.0}
    # $500 account less $10 marked loss, split over five slots.
    assert sizer(candidate, [open_lot], [open_lot]) == pytest.approx(98.0)


def test_manual_ratchet_only_moves_up_and_leaves_cash_limiting_to_the_engine() -> None:
    from experiments.eth_canonical_v1.manual_ratchet_compounding import manual_ratchet_sizer

    data = market(10)
    data.close[2] = 200.0
    data.close[3] = 90.0
    portfolio = config(lots=5)
    sizer = manual_ratchet_sizer(data, portfolio, initial_lot=100.0, profit_step=100.0,
                                 lot_increase=20.0)
    winner = {"entry_index": 1, "exit_index": 8, "quantity": 1.0, "spend": 100.0, "pnl": 0.0}
    at_high = CandidateTrade(2, 8, 100.0, "dip", 1, "high")
    at_low = CandidateTrade(3, 8, 100.0, "dip", 1, "low")
    assert sizer(at_high, [winner], [winner]) == pytest.approx(120.0)
    assert sizer(at_low, [winner], [winner]) == pytest.approx(120.0)


def test_drop_entries_emit_only_first_crossing_and_buy_next_minute() -> None:
    from experiments.eth_canonical_v1.drop_rebound_mode_b import drop_entries

    close = np.array([100, 100, 100, 100, 100, 98, 97, 100, 98, 100, 100], dtype=float)
    # With a five-minute rolling high and a 2% threshold, minutes 5 and 8 cross
    # from false to true. Orders land at the following minute opens.
    assert drop_entries(close, 5, 2.0).tolist() == [6, 9]


@needs_eth_data
def test_reproduces_the_frozen_eth_v5_baseline() -> None:
    from experiments.eth_canonical_v1.baseline import STAGE2_ROOT, build_baseline

    expected = json.loads(
        (STAGE2_ROOT / "config" / "experiments" / "eth_canonical_v1.json").read_text()
    )
    data, candidates, windows = build_baseline()
    p = expected["portfolio"]
    c = expected["costs"]
    result = replay_portfolio(
        candidates, data, *windows["full"],
        PortfolioConfig(
            initial_capital=p["initial_capital_usd"], lot_size=p["lot_size_usd"],
            maximum_lots=p["lots"], minimum_order_usd=p["minimum_order_usd"],
            fee_per_side=c["fee_bps_per_side"] / 10_000,
            slippage_per_side=c["slippage_bps_per_side"] / 10_000,
        ),
    )
    tolerance = expected["acceptance_tolerance"]
    for key, target in expected["acceptance"].items():
        assert result.summary[key] == pytest.approx(target, abs=tolerance)


def test_stronger_confirmation_predicates_are_distinct() -> None:
    from experiments.eth_canonical_v1.confirmation_quality import confirmation_passes

    open_ = np.array([99.0, 100.0, 100.0])
    close = np.array([100.0, 100.2, 100.8])
    high = np.array([100.5, 100.7, 101.0])
    assert confirmation_passes("current_green", 1, open_, close, high, 100.5, 100.75)
    assert not confirmation_passes("close_above_zone_midpoint", 1, open_, close, high, 100.5, 100.75)
    assert confirmation_passes("close_above_zone_midpoint", 2, open_, close, high, 100.5, 100.75)
    assert confirmation_passes("close_above_zone_top", 2, open_, close, high, 100.5, 100.75)
    assert confirmation_passes("close_above_previous_5m_high", 2, open_, close, high, 100.5, 100.75)


@needs_eth_data
def test_current_confirmation_rebuilds_canonical_dip_entries() -> None:
    from experiments.eth_canonical_v1 import baseline as baseline_module
    from experiments.eth_canonical_v1.confirmation_quality import build_candidates

    _, canonical, _ = baseline_module.build_baseline()
    _, rebuilt, _, _ = build_candidates("current_green")
    assert [c.entry for c in rebuilt if c.source == "dip"] == [c.entry for c in canonical if c.source == "dip"]


def test_delayed_fixed_stop_only_tightens() -> None:
    from experiments.eth_canonical_v1.delayed_stop_tightening import tightened_stop_level

    variant = {"type": "fixed_from_entry", "stop_pct": 3.0}
    assert tightened_stop_level(100.0, 4.5, variant, 96.0) == pytest.approx(97.0)


def test_delayed_swing_stop_uses_buffer_and_three_percent_cap() -> None:
    from experiments.eth_canonical_v1.delayed_stop_tightening import tightened_stop_level

    variant = {"type": "post_entry_swing_low", "buffer_pct": 0.25, "maximum_stop_distance_pct": 3.0}
    assert tightened_stop_level(100.0, 4.5, variant, 99.0) == pytest.approx(98.7525)
    assert tightened_stop_level(100.0, 4.5, variant, 95.0) == pytest.approx(97.0)


def test_structural_stop_enforces_minimum_distance() -> None:
    from experiments.eth_canonical_v1.setup_stop_risk import structural_stop

    stop, distance = structural_stop(100.0, 99.5, 0.25, 1.5, 4.5)
    assert distance == pytest.approx(1.5)
    assert stop == pytest.approx(98.5)


def test_structural_stop_rejects_a_setup_wider_than_maximum() -> None:
    from experiments.eth_canonical_v1.setup_stop_risk import structural_stop

    stop, distance = structural_stop(100.0, 94.0, 0.25, 1.5, 4.5)
    assert stop is None
    assert distance > 4.5


def test_pullback_quality_predicates_are_distinct() -> None:
    from experiments.eth_canonical_v1.pullback_quality import filter_passes

    args = (100.0, 99.9, 100.1, 100.2, 100.15)
    assert filter_passes("current_pullback", *args)
    assert filter_passes("ema_rising_6h", *args)
    assert not filter_passes("ema_rising_12h", *args)
    assert filter_passes("reclaim_above_previous_5m_high", *args)
    assert not filter_passes("reclaim_above_previous_5m_high", 100.0, 99.9, 99.8, 100.1, 100.2)


@needs_eth_data
def test_current_pullback_signal_rebuild_matches_canonical_entries() -> None:
    from experiments.eth_canonical_v1 import baseline as baseline_module
    from experiments.eth_canonical_v1.pullback_quality import (
        CONTROL,
        allowed_entries,
        pullback_signal_table,
    )

    _, canonical, _ = baseline_module.build_baseline()
    expected = {candidate.entry for candidate in canonical if candidate.source == "pullback"}
    assert allowed_entries(CONTROL, pullback_signal_table()) == expected


@needs_eth_data
def test_current_mode_c_rebuild_matches_canonical_entries() -> None:
    from experiments.eth_canonical_v1 import baseline as baseline_module
    from experiments.eth_canonical_v1.mode_c_retest import (
        current_mode_c_entries,
        mode_c_breakouts,
    )

    raw, _ = baseline_module.compare.load("ETHUSDT")
    _, canonical, _ = baseline_module.build_baseline()
    expected = np.asarray([c.entry for c in canonical if c.source == "breakout"], dtype=np.int64)
    assert np.array_equal(current_mode_c_entries(raw, mode_c_breakouts(raw)), expected)


def test_volatility_sizing_schedule_uses_the_frozen_tiers() -> None:
    from experiments.eth_canonical_v1.volatility_sizing import order_size_for_state

    schedule = {"normal_size_usd": 100.0, "high_size_usd": 70.0, "extreme_size_usd": 50.0}
    assert order_size_for_state("normal", schedule) == 100.0
    assert order_size_for_state("high", schedule) == 70.0
    assert order_size_for_state("extreme", schedule) == 50.0


def test_protective_reentry_confirmation_requires_all_three_conditions() -> None:
    from experiments.eth_canonical_v1.protective_reentry import strong_reentry_confirmation

    assert strong_reentry_confirmation(99.0, 101.0, 100.0, 100.5)
    assert not strong_reentry_confirmation(101.0, 100.8, 100.0, 100.5)
    assert not strong_reentry_confirmation(99.0, 99.9, 100.0, 99.8)
    assert not strong_reentry_confirmation(99.0, 100.4, 100.0, 100.5)


@needs_eth_data
def test_dip_stop_episodes_have_frozen_zone_metadata() -> None:
    from experiments.eth_canonical_v1 import baseline as baseline_module
    from experiments.eth_canonical_v1.protective_reentry import dip_stop_episodes

    raw, _ = baseline_module.compare.load("ETHUSDT")
    _, canonical, _ = baseline_module.build_baseline()
    episodes = dip_stop_episodes(raw, canonical)
    assert episodes
    assert len({episode.parent_id for episode in episodes}) == len(episodes)
    assert all(episode.zone_top > 0 and episode.stop_index > episode.parent_entry for episode in episodes)


def test_futures_crowding_requires_positive_joint_extremes() -> None:
    from experiments.eth_canonical_v1.futures_crowding import crowded_long

    assert crowded_long(0.001, 0.0008, 0.10, 0.08)
    assert not crowded_long(-0.001, -0.002, 0.10, 0.08)
    assert not crowded_long(0.001, 0.0008, -0.01, -0.02)
    assert not crowded_long(0.0007, 0.0008, 0.10, 0.08)
    assert not crowded_long(0.001, 0.0008, 0.07, 0.08)


def test_drop_addon_green_confirmation_uses_next_open_after_first_green() -> None:
    from experiments.eth_canonical_v1.drop_rebound_addon_quality import confirmed_entries

    open_ = np.asarray([100.0, 100.0, 99.0, 98.0, 99.0, 100.0])
    close = np.asarray([100.0, 99.0, 98.0, 99.0, 98.0, 100.0])
    variant = {"type": "first_green_1m", "maximum_wait_minutes": 3}
    assert np.array_equal(confirmed_entries(open_, close, np.asarray([2]), variant), np.asarray([4]))


def test_drop_addon_rebound_confirmation_is_measured_from_trigger_close() -> None:
    from experiments.eth_canonical_v1.drop_rebound_addon_quality import confirmed_entries

    open_ = np.full(7, 100.0)
    close = np.asarray([100.0, 100.0, 95.0, 95.1, 95.23, 95.3, 95.0])
    variant = {"type": "rebound_from_trigger", "rebound_pct": 0.25, "maximum_wait_minutes": 3}
    assert np.array_equal(confirmed_entries(open_, close, np.asarray([3]), variant), np.asarray([6]))


def test_drop_addon_uptrend_requires_all_three_conditions() -> None:
    from experiments.eth_canonical_v1.drop_rebound_uptrend import uptrend_passes

    assert uptrend_passes(105.0, 104.0, 106.0, 103.0, 102.0, 101.0)
    assert not uptrend_passes(103.0, 104.0, 106.0, 103.0, 102.0, 101.0)
    assert not uptrend_passes(105.0, 104.0, 106.0, 99.0, 100.0, 101.0)
    assert not uptrend_passes(105.0, 104.0, 100.0, 103.0, 102.0, 101.0)


def test_loosened_drop_filters_only_enforce_enabled_checks() -> None:
    from experiments.eth_canonical_v1.drop_rebound_uptrend_loosened import loosened_filter_passes

    ema_only = {
        "require_ema_rising": True, "reject_bearish_daily_stack": False,
        "require_above_30d": False,
    }
    ema_non_bearish = {**ema_only, "reject_bearish_daily_stack": True}
    ema_above_30d = {**ema_only, "require_above_30d": True}
    assert loosened_filter_passes(ema_only, 105.0, 104.0, 90.0, 99.0, 100.0, 101.0)
    assert not loosened_filter_passes(ema_non_bearish, 105.0, 104.0, 110.0, 99.0, 100.0, 101.0)
    assert not loosened_filter_passes(ema_above_30d, 105.0, 104.0, 100.0, 103.0, 102.0, 101.0)


def test_minimum_net_floor_accounts_for_both_sides_of_costs() -> None:
    from experiments.eth_canonical_v1.drop_rebound_min_net_floor import raw_exit_for_net_return

    entry_fill, fee, slip = 100.02, 0.00075, 0.0002
    raw_exit = raw_exit_for_net_return(entry_fill, 0.20, fee, slip)
    quantity = 100.0 / (entry_fill * (1 + fee))
    proceeds = quantity * raw_exit * (1 - slip) * (1 - fee)
    assert proceeds / 100.0 - 1 == pytest.approx(0.002)


def test_wider_giveback_must_improve_profit_and_average_win() -> None:
    from experiments.eth_canonical_v1.drop_rebound_giveback import wider_giveback_passes

    control = {
        "profit": 100.0, "later_profit": 40.0, "walk_forward_profit": 90.0,
        "addon_average_win": 0.5, "headline_win_rate_pct": 85.0,
    }
    row = {
        "giveback_pct": 45.0, "profit": 101.0, "later_profit": 41.0,
        "walk_forward_profit": 91.0, "addon_average_win": 0.6,
        "headline_win_rate_pct": 84.0, "additional_trades": 50,
        "walk_forward_windows_improved_vs_base": 4, "average_loss": -3.0,
        "max_drawdown_pct": -9.0,
    }
    acceptance = {
        "full_profit_change_gt": 0.0, "later_profit_change_gte": 0.0,
        "walk_forward_profit_change_gt": 0.0, "addon_average_win_change_gt": 0.0,
        "maximum_combined_win_rate_reduction_pp": 2.0,
    }
    safety = {
        "minimum_combined_headline_win_rate_pct": 75.0, "minimum_additional_trades": 20,
        "minimum_walk_forward_windows_improved": 4,
    }
    base = {"average_loss": -4.5, "max_drawdown_pct": -9.7}
    assert wider_giveback_passes(row, control, base, acceptance, safety)
    assert not wider_giveback_passes({**row, "addon_average_win": 0.4}, control, base, acceptance, safety)


def test_higher_low_confirmation_enters_after_neckline_break_close() -> None:
    from experiments.eth_canonical_v1.drop_rebound_higher_low import higher_low_entries

    high = np.asarray([10.0, 9.5, 9.0, 10.0, 9.2, 10.8, 10.5, 10.0])
    low = np.asarray([9.5, 8.8, 8.0, 8.9, 8.5, 9.0, 9.2, 9.1])
    close = np.asarray([9.8, 9.0, 8.4, 9.5, 8.8, 10.2, 10.1, 9.8])
    entries, episodes = higher_low_entries(
        high, low, close, np.asarray([3]), wing=1, maximum_minutes=5,
    )
    assert np.array_equal(entries, np.asarray([6]))
    assert episodes[0]["first_low"] == 2
    assert episodes[0]["second_low"] == 4
    assert episodes[0]["neckline"] == pytest.approx(10.0)


def test_volatility_adjusted_drop_requires_both_thresholds() -> None:
    from experiments.eth_canonical_v1.drop_rebound_volatility import volatility_adjusted_entries

    close = np.asarray([100.0, 100.0, 94.0, 94.0, 94.0])
    volatility = np.full(len(close), 3.0)
    assert np.array_equal(
        volatility_adjusted_entries(close, volatility, 2, 5.0, 2.0), np.asarray([3])
    )
    assert len(volatility_adjusted_entries(close, volatility, 2, 5.0, 3.0)) == 0


def test_failed_bounce_exit_is_next_open_after_completed_checkpoint() -> None:
    from experiments.eth_canonical_v1.drop_rebound_failed_bounce_exit import apply_failed_bounce_exit

    data = market(minutes=10)
    data.open[4] = 97.0
    unarmed = CandidateTrade(1, 8, 110.0, "drop_rebound", 1, "late", arm_index=6)
    armed = CandidateTrade(1, 8, 110.0, "drop_rebound", 1, "armed", arm_index=3)
    adjusted, changed = apply_failed_bounce_exit([unarmed, armed], 3, data)
    assert changed == 1
    assert adjusted[0].exit == 4
    assert adjusted[0].exit_price == pytest.approx(97.0)
    assert adjusted[0].arm_index is None
    assert adjusted[1] == armed


def test_drop_episode_limit_blocks_nearby_signal_until_recovery_or_new_window() -> None:
    from experiments.eth_canonical_v1.drop_rebound_episode_limit import limit_entries_by_episode

    close = np.asarray([100.0, 100.0, 100.0, 94.0, 96.0, 94.0, 95.0, 94.0, 95.0])
    limited, log = limit_entries_by_episode(close, np.asarray([4, 6, 8]), 3, episode_minutes=3)
    assert np.array_equal(limited, np.asarray([4, 8]))
    assert list(log.reason) == ["first_episode", "duplicate_same_episode", "new_60m_episode"]

    recovered_close = close.copy()
    recovered_close[4] = 101.0
    recovered, _ = limit_entries_by_episode(
        recovered_close, np.asarray([4, 6]), 3, episode_minutes=3
    )
    assert np.array_equal(recovered, np.asarray([4, 6]))
