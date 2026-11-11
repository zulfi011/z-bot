"""The breakout's rules, on hand-built bars where the right answer is obvious."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.consolidation import (
    ConsolidationConfig,
    build_bars,
    confirm,
    current_zone,
    find_breakouts,
    zone_before,
)

UTC = timezone.utc
D = Decimal
MINUTE = timedelta(minutes=1)
START = datetime(2026, 1, 1, tzinfo=UTC)


class Candle:
    def __init__(self, open_time, high, low, close):
        self.open_time, self.high, self.low, self.close = open_time, high, low, close


def config(chart=60, bars=3, width="2.5", wait=30, blocked=None) -> ConsolidationConfig:
    return ConsolidationConfig(chart_minutes=chart, zone_bars=bars, maximum_zone_pct=D(width),
                               confirmation_wait_minutes=wait, stop_pct=D("3.5"),
                               trail_activation_pct=D("1.283"), trail_giveback_pct=D("22"),
                               blocked_entry_hours=blocked)


def minutes(values, chart=60, start=START):
    """One candle a minute; `values` gives each bar's (high, low, close) repeated across the bar."""
    candles, at = [], start
    for high, low, close in values:
        for index in range(chart):
            last = index == chart - 1
            candles.append(Candle(at, D(str(high)), D(str(low)), D(str(close if last else (high + low) / 2))))
            at += MINUTE
    return candles


def test_a_bar_missing_a_minute_is_dropped_not_guessed():
    candles = minutes([(100, 99, 100), (101, 100, 101)], chart=60)
    del candles[70]                                       # one minute of the second bar never arrived
    bars = build_bars(candles, 60)
    assert len(bars) == 1 and bars[0].open_time == START


def test_bars_are_counted_from_the_epoch_so_they_never_drift():
    candles = minutes([(100, 99, 100)], chart=120, start=datetime(2026, 1, 1, 4, 0, tzinfo=UTC))
    bars = build_bars(candles, 120)
    assert bars[0].open_time == datetime(2026, 1, 1, 4, 0, tzinfo=UTC)
    assert bars[0].last_minute == datetime(2026, 1, 1, 5, 59, tzinfo=UTC)


def test_the_zone_is_measured_before_the_bar_that_breaks_it():
    bars = build_bars(minutes([(100, 99, 100), (101, 99, 100), (100, 98, 99), (110, 100, 109)]), 60)
    zone = zone_before(bars, 3, config())
    assert (zone.top, zone.bottom) == (D("101"), D("98"))   # the 110 high of the breaking bar is excluded
    assert zone.bars == 3


def test_a_band_that_is_too_wide_is_not_a_consolidation():
    calm = build_bars(minutes([(100, 99, 100), (101, 99, 100), (100, 98, 99)]), 60)
    _, quiet = current_zone(calm, config(width="4"))
    assert quiet is True
    _, quiet = current_zone(calm, config(width="2"))       # 101/98 - 1 = 3.06%, wider than 2%
    assert quiet is False


def test_only_the_first_break_of_each_quiet_stretch_counts():
    """A long move is one signal, not one per bar - otherwise a single rally would buy every lot at once."""
    # zone = top 100.5 / bottom 99 = 1.52% wide, comfortably inside the 2.5% limit
    bars = build_bars(minutes([(100, 99, 100), (100.5, 99, 100), (100.2, 99.2, 99.5),
                               (110, 100, 109), (120, 110, 119), (130, 120, 129)]), 60)
    breakouts = find_breakouts(bars, config())
    assert len(breakouts) == 1
    assert breakouts[0].broke_at == START + timedelta(hours=3)


def test_a_break_is_bought_only_if_it_holds_through_the_wait():
    bars = build_bars(minutes([(100, 99, 100), (100.5, 99, 100), (100.2, 99.2, 99.5), (110, 100, 109)]), 60)
    breakout = find_breakouts(bars, config())[0]
    assert breakout.confirm_at == breakout.broke_at + timedelta(minutes=59 + 30)

    still_up = {breakout.confirm_at: D("108")}             # above the 100.5 zone top
    assert confirm(breakout, still_up) == ("confirmed", breakout.confirm_at + MINUTE)

    fell_back = {breakout.confirm_at: D("100")}            # back inside the zone
    assert confirm(breakout, fell_back) == ("failed", None)

    assert confirm(breakout, {}) == ("pending", None)      # that minute has not arrived yet


def test_the_closed_hours_apply_to_breakout_too():
    """The quiet-band breakout must obey the same 06-12 UTC rule as the dip entry, or the two disagree about when to trade."""
    rule = config(blocked=(6, 12))
    assert rule.blocked(datetime(2026, 1, 1, 6, 0, tzinfo=UTC))
    assert rule.blocked(datetime(2026, 1, 1, 11, 59, tzinfo=UTC))
    assert not rule.blocked(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    assert not rule.blocked(datetime(2026, 1, 1, 5, 59, tzinfo=UTC))
    assert not config().blocked(datetime(2026, 1, 1, 6, 0, tzinfo=UTC))


def test_too_little_history_is_never_a_signal():
    bars = build_bars(minutes([(100, 99, 100), (110, 100, 109)]), 60)
    assert zone_before(bars, 1, config()) is None
    assert find_breakouts(bars, config()) == []


def test_the_eth_strategy_file_describes_breakout():
    import copy
    from tests.test_strategy import ETH_STRATEGY

    rule = ConsolidationConfig.from_strategy(copy.deepcopy(ETH_STRATEGY))
    assert (rule.chart_minutes, rule.zone_bars) == (120, 12)
    assert rule.maximum_zone_pct == D("2.5")
    assert rule.confirmation_wait_minutes == 30
    assert rule.stop_pct == D("3.5")
    assert rule.blocked_entry_hours == (6, 12)


def test_the_sol_strategy_file_describes_its_own_breakout():
    """SOL breaks out of a 1-hour chart with no confirmation wait; ETH uses a 2-hour chart and waits 30 minutes."""
    import copy
    from tests.test_strategy import STRATEGY

    rule = ConsolidationConfig.from_strategy(copy.deepcopy(STRATEGY))
    assert (rule.chart_minutes, rule.zone_bars) == (60, 24)
    assert rule.maximum_zone_pct == D("2.0")
    assert rule.confirmation_wait_minutes == 0
    assert rule.stop_pct == D("4.0")
    assert rule.blocked_entry_hours == (6, 12)


def test_a_zero_wait_buys_the_very_next_minute():
    """SOL waits nothing after the break, so the confirmation minute and the buy are adjacent - the exact
    edge case where an off-by-one would hide."""
    rule = config(chart=60, bars=3, wait=0)
    bars = build_bars(minutes([(100, 99, 100), (100.5, 99, 100), (100.2, 99.2, 99.5), (110, 100, 109)]), 60)
    breakout = find_breakouts(bars, rule)[0]
    assert breakout.confirm_at == breakout.broke_at + timedelta(minutes=59)      # the breaking bar's last minute
    state, entry = confirm(breakout, {breakout.confirm_at: D("109")})
    assert state == "confirmed"
    assert entry == breakout.confirm_at + timedelta(minutes=1)


def test_btc_has_no_breakout():
    """BTC's own grid produced a rule so fragile that one step in any direction lost money, so it gets none."""
    import copy
    from tests.test_strategy import BTC_STRATEGY

    assert ConsolidationConfig.from_strategy(copy.deepcopy(BTC_STRATEGY)) is None


def test_a_coin_with_no_blocked_hours_trades_breakout_around_the_clock():
    rule = config(blocked=None)
    for hour in (0, 6, 9, 11, 23):
        assert not rule.blocked(datetime(2026, 1, 1, hour, tzinfo=UTC))
