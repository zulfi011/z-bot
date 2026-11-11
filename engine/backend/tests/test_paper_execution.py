from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.paper_execution import (
    Candle,
    CoinAllocation,
    ExecutionConfig,
    FeeContext,
    Position,
    create_entry,
    evaluate_exit,
    fill_exit,
    manual_exit_signal,
    mark_account,
    uses_trend_exit,
)


UTC = timezone.utc
D = Decimal
NO_BNB = FeeContext(False, D("0"), D("600"))
WITH_BNB = FeeContext(True, D("1"), D("600"))




def config(hold=None) -> ExecutionConfig:
    return ExecutionConfig(
        usdt_fee_bps=D("10"), bnb_fee_bps=D("7.5"), slippage_bps=D("2"),
        stop_pct=D("2"), trail_activation_pct=D("1.251"), trail_giveback_pct=D("12"),
        maximum_hold_minutes=hold,
    )


def candle(minute: int, open_: str, high: str, low: str, close: str) -> Candle:
    return Candle(datetime(2026, 1, 1, 0, minute, tzinfo=UTC), D(open_), D(high), D(low), D(close))


def position(fee_asset="USDT") -> Position:
    return Position(
        position_id="p1", entry_time=datetime(2026, 1, 1, tzinfo=UTC), raw_entry_price=D("100"),
        entry_fill_price=D("100"), quantity=D("1"), allocation_usd=D("100"), entry_fee_usd=D("0.075"),
        entry_fee_asset=fee_asset,
    )


def test_usdt_entry_fee_comes_out_of_the_allocation() -> None:
    fill = create_entry(D("100"), D("100"), config(), NO_BNB)
    assert fill.fill_price == D("100.02")
    assert fill.fee.asset == "USDT"
    assert fill.notional_usd + fill.fee.usd == D("100")
    assert fill.fee.bnb == 0


def test_bnb_entry_buys_the_full_allocation_and_charges_the_wallet() -> None:
    fill = create_entry(D("100"), D("100"), config(), WITH_BNB)
    assert fill.fee.asset == "BNB"
    assert fill.notional_usd == D("100")
    assert fill.fee.usd == D("0.075")
    assert fill.fee.bnb == D("0.075") / D("600")


def test_bnb_fee_falls_back_to_usdt_when_wallet_is_short() -> None:
    fill = create_entry(D("100"), D("100"), config(), FeeContext(True, D("0.0000001"), D("600")))
    assert fill.fee.asset == "USDT"
    assert fill.fee.rate_bps == D("10")


def test_stop_wins_when_activation_and_stop_share_a_minute() -> None:
    lot = position()
    signal = evaluate_exit(lot, candle(0, "100", "102", "97", "100"), config())
    assert signal.reason == "ambiguous_stop"
    assert signal.raw_price == D("98")


def test_trail_needs_a_later_minute_and_uses_the_prior_peak() -> None:
    lot = position()
    assert evaluate_exit(lot, candle(0, "100", "102", "100.5", "101.5"), config()) is None
    assert lot.trailing_active and lot.peak_price == D("102")
    assert lot.trailing_started_at == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    signal = evaluate_exit(lot, candle(1, "101.9", "103", "101.7", "101.8"), config())
    assert signal.reason == "trailing_stop"
    assert signal.raw_price == D("101.76")      # 100 + 0.88 × 2


def test_gap_below_stop_fills_at_the_open() -> None:
    lot = position()
    signal = evaluate_exit(lot, candle(0, "95", "96", "94", "95"), config())
    assert signal.raw_price == D("95")


def test_no_time_exit() -> None:
    lot = position()
    for minute in range(59):
        assert evaluate_exit(lot, candle(minute, "100", "100.5", "99.5", "100"), config()) is None
    assert lot.bars_held == 59


def test_exit_pnl_counts_bnb_fees_at_usd_value() -> None:
    lot = position(fee_asset="BNB")
    signal = manual_exit_signal(lot, candle(5, "101", "101", "101", "101"), datetime(2026, 1, 1, 0, 5, 30, tzinfo=UTC))
    fill = fill_exit(lot, signal, config(), WITH_BNB)
    assert fill.fee.asset == "BNB"
    notional = D("101") * D("0.9998")
    assert fill.cash_in_usd == notional
    assert fill.net_pnl_usd == notional - D("100") - D("0.075") - notional * D("7.5") / D("10000")


def test_manual_close_waits_for_a_minute_that_ends_after_the_request() -> None:
    lot = position()
    assert manual_exit_signal(lot, candle(5, "1", "1", "1", "1"), datetime(2026, 1, 1, 0, 6, 10, tzinfo=UTC)) is None


def test_account_mark_separates_trading_results_from_flows() -> None:
    lot = position(fee_asset="BNB")
    mark = mark_account(cash=D("200"), positions=[lot], price=D("101"), bnb_balance=D("0.01"), bnb_price=D("600"),
                        realized_pnl=D("-2"), net_deposits=D("300"), initial_deposit=D("300"),
                        previous_peak=D("301"))
    assert mark.open_position_cost_usd == D("100.075")
    assert mark.unrealized_pnl_usd == D("0.925")
    assert mark.bnb_value_usd == D("6")
    assert mark.total_value_usd == D("307")
    assert mark.strategy_pnl_usd == D("-1.075")
    assert mark.performance_equity_usd == D("298.925")
    assert mark.drawdown_pct == (D("298.925") / D("301") - 1) * 100


def test_account_mark_values_each_coin_at_its_own_price() -> None:
    sol = position()
    eth = Position(position_id="eth", entry_time=sol.entry_time, raw_entry_price=D("2000"), entry_fill_price=D("2000"),
                   quantity=D("0.05"), allocation_usd=D("100"), entry_fee_usd=D("0.1"), symbol="ETHUSDT")
    mark = mark_account(cash=D("400"), positions=[sol, eth], price={"SOLUSDT": D("101"), "ETHUSDT": D("2100")},
                        bnb_balance=D("0"), bnb_price=None, realized_pnl=D("0"), net_deposits=D("600"),
                        initial_deposit=D("600"), previous_peak=D("600"))
    assert mark.open_position_value_usd == sol.quantity * D("101") + D("105")
    assert mark.total_value_usd == D("400") + mark.open_position_value_usd


# --------------------------------------------------------------- trend ride

def trend_config(ema_minutes=960, requires_uptrend=True, stop="4.5") -> ExecutionConfig:
    return ExecutionConfig(
        usdt_fee_bps=D("10"), bnb_fee_bps=D("7.5"), slippage_bps=D("2"),
        stop_pct=D(stop), trail_activation_pct=D("1.315"), trail_giveback_pct=D("30"),
        trend_exit_ema_minutes=ema_minutes, trend_exit_requires_uptrend=requires_uptrend,
    )


def trend_position(trend_ride=True) -> Position:
    lot = position()
    lot.trend_exit_active = trend_ride
    return lot


def test_trend_exit_needs_both_the_strategy_and_an_uptrend_entry():
    assert uses_trend_exit(trend_position(True), trend_config())
    assert not uses_trend_exit(trend_position(False), trend_config())
    # a strategy without the trend exit ignores the flag entirely
    assert not uses_trend_exit(trend_position(True), config())
    # and it can be applied to every lot when the strategy does not ask for an uptrend
    assert uses_trend_exit(trend_position(False), trend_config(requires_uptrend=False))


def test_trend_ride_holds_above_the_ema_and_sells_on_the_next_open():
    lot = trend_position()
    # arms at +1.315% (fill 100 -> 101.315); the arming minute itself never exits
    assert evaluate_exit(lot, candle(0, "100", "102", "99.9", "101.9"), trend_config(), D("101")) is None
    assert lot.trailing_active
    # well above the line: keep holding, and the giveback level (which would be ~101.4) is ignored
    assert evaluate_exit(lot, candle(1, "103", "106", "101.5", "105.5"), trend_config(), D("102")) is None
    assert lot.peak_price == D("106")
    # first close below the line only marks the lot; nothing is sold inside that minute
    assert evaluate_exit(lot, candle(2, "105", "105.5", "104", "104.2"), trend_config(), D("104.5")) is None
    assert lot.trend_exit_pending
    # the sale lands on the next minute's open
    signal = evaluate_exit(lot, candle(3, "104.1", "104.3", "103", "103.5"), trend_config(), D("104.4"))
    assert signal is not None
    assert (signal.reason, signal.raw_price) == ("trend_exit", D("104.1"))


def test_trend_ride_ignores_the_giveback_that_would_have_closed_trailing():
    # peak 102 after minute 0, so the trailing stop gives back 30% of (102 - 100) and exits at 101.4
    give_back_would_exit = candle(1, "105", "110", "101", "103")
    trailing = position()
    assert evaluate_exit(trailing, candle(0, "100", "102", "99.9", "101.9"), trend_config(), None) is None
    assert evaluate_exit(trailing, give_back_would_exit, trend_config(), D("90")).reason == "trailing_stop"
    trend_ride = trend_position()
    assert evaluate_exit(trend_ride, candle(0, "100", "102", "99.9", "101.9"), trend_config(), D("90")) is None
    # same minute, same prices: the trend ride stays in because the close is above the line
    assert evaluate_exit(trend_ride, give_back_would_exit, trend_config(), D("90")) is None


def test_the_protective_stop_still_wins_in_trend_ride_before_it_arms():
    """An unarmed trend-ride lot has only its -4.5% stop: the line is ignored until the trail arms."""
    lot = trend_position()
    # the high stays under the +1.315% arming level, so this lot has never armed
    signal = evaluate_exit(lot, candle(1, "101", "101.2", "95", "95.5"), trend_config(), D("101"))
    assert signal is not None and signal.reason == "protective_stop"


def test_an_armed_trend_ride_lot_cannot_finish_below_break_even():
    """Once armed the stop is lifted to the fill plus costs, so a round trip ends level, not negative."""
    lot = trend_position()
    assert evaluate_exit(lot, candle(0, "100", "102", "99.9", "101.9"), trend_config(), D("101")) is None
    signal = evaluate_exit(lot, candle(1, "101", "101.5", "95", "95.5"), trend_config(), D("101"))
    assert signal is not None
    assert signal.reason == "break_even", "the floor sits above the -4.5% stop, so it is hit first"
    floor = lot.entry_fill_price * (1 + trend_config().break_even_floor_pct / 100)
    assert signal.raw_price == floor


def test_a_pending_trend_exit_is_not_overridden_by_a_later_stop():
    """Once a minute has closed below the line the lot is sold at the next open, whatever that minute does."""
    lot = trend_position()
    evaluate_exit(lot, candle(0, "100", "102", "99.9", "101.9"), trend_config(), D("101"))
    evaluate_exit(lot, candle(1, "102", "103", "101.5", "101.6"), trend_config(), D("102"))
    assert lot.trend_exit_pending
    signal = evaluate_exit(lot, candle(2, "101.5", "101.5", "90", "91"), trend_config(), D("102"))
    assert (signal.reason, signal.raw_price) == ("trend_exit", D("101.5"))


def test_without_an_ema_a_trend_ride_lot_simply_holds():
    """A missing trend line must never sell a lot by accident - it just cannot trigger the trend exit."""
    lot = trend_position()
    assert evaluate_exit(lot, candle(0, "100", "102", "99.9", "101.9"), trend_config(), None) is None
    assert evaluate_exit(lot, candle(1, "101", "104", "100.5", "100.6"), trend_config(), None) is None
    assert not lot.trend_exit_pending


def test_trailing_is_unchanged_when_the_strategy_has_a_trend_exit():
    lot = position()
    assert evaluate_exit(lot, candle(0, "100", "102", "99.9", "101.9"), trend_config(), D("101")) is None
    assert lot.peak_price == D("102")
    # giveback 30% of (102 - 100.02) = 101.43
    signal = evaluate_exit(lot, candle(1, "101.9", "102", "101", "101.2"), trend_config(), D("101"))
    assert signal is not None and signal.reason == "trailing_stop"
