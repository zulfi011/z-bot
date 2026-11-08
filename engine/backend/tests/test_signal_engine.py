from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.signal_engine import SignalCandle, SignalEngine


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def bar(minutes, opened, high, low, close, average=100, regime=(100, 100, 100), start=START) -> SignalCandle:
    dec = lambda value: Decimal(str(value)) if value is not None else None  # noqa: E731
    return SignalCandle(
        open_time=start + timedelta(minutes=minutes),
        open=dec(opened), high=dec(high), low=dec(low), close=dec(close),
        signal_average=dec(average),
        average_7d=dec(regime[0]), average_15d=dec(regime[1]), average_30d=dec(regime[2]),
    )


def engine(blocked=None) -> SignalEngine:
    return SignalEngine("sol_12d", Decimal("0.5"), 30, blocked_entry_hours=blocked)


def test_first_touch_bullish_confirms_at_next_boundary() -> None:
    current = engine()
    current.process(bar(0, 99, 99.4, 98.5, 99))
    transition = current.process(bar(3, 99.5, 100.2, 99.4, 100))
    assert transition.episode.status == "pending_confirmation"
    assert transition.resolution.status == "confirmed"
    assert transition.resolution.entry_time == START + timedelta(minutes=6)


def test_touch_uses_the_signal_average_not_the_regime_averages() -> None:
    current = engine()
    current.process(bar(0, 110, 110.5, 109, 110, average=112, regime=(100, 100, 100)))
    transition = current.process(bar(3, 111, 112.3, 110.9, 112, average=112, regime=(100, 100, 100)))
    assert transition.episode.average_value == Decimal("112")
    assert transition.resolution.status == "confirmed"


def test_first_non_touch_bearish_candle_cancels() -> None:
    current = engine()
    current.process(bar(0, 99, 99.4, 98.5, 99))
    current.process(bar(3, 100, 100.2, 99.5, 99.8))
    transition = current.process(bar(6, 102, 102, 100.6, 101))
    assert transition.resolution.status == "cancelled_at_episode_exit"


def test_confirmation_includes_30_minute_boundary() -> None:
    current = engine()
    current.process(bar(0, 99, 99.4, 98.5, 99))
    current.process(bar(3, 100, 100.2, 99.5, 99.8))
    for minute in range(6, 33, 3):
        assert current.process(bar(minute, 100, 100.2, 99.5, 99.8)).resolution is None
    transition = current.process(bar(33, 99.8, 100.3, 99.5, 100.1))
    assert transition.resolution.status == "confirmed"
    assert transition.resolution.entry_time == START + timedelta(minutes=36)


def test_touch_not_from_below_is_only_observed() -> None:
    current = engine()
    current.process(bar(0, 100.2, 100.4, 100.1, 100.3))
    transition = current.process(bar(3, 100.3, 100.4, 99.9, 100.35))
    assert transition.episode is None
    current = engine()
    current.process(bar(0, 101, 101.5, 100.8, 101))
    transition = current.process(bar(3, 100.8, 100.9, 100.2, 100.6))
    assert transition.episode.status == "observed_not_from_below"
    assert transition.resolution is None


def test_bearish_and_missing_market_context_are_rejected() -> None:
    for regime in ((99, 100, 101), (None, 100, 101)):
        current = engine()
        current.process(bar(0, 98, 99.4, 98, 99, regime=regime))
        transition = current.process(bar(3, 99.5, 100.2, 99.4, 100, regime=regime))
        assert transition.episode.status == "rejected_market_regime"
        assert current.market_rejections == 1


def test_entry_inside_blocked_hours_is_skipped() -> None:
    start = datetime(2026, 1, 1, 5, 54, tzinfo=timezone.utc)
    current = engine(blocked=(6, 12))
    current.process(bar(0, 99, 99.4, 98.5, 99, start=start))
    transition = current.process(bar(3, 99.5, 100.2, 99.4, 100, start=start))
    # Confirmation candle opens 05:57, entry would be 06:00 → blocked.
    assert transition.resolution.status == "skipped_time_window"
    assert transition.resolution.entry_time is None


def test_entry_at_block_end_is_allowed() -> None:
    start = datetime(2026, 1, 1, 11, 54, tzinfo=timezone.utc)
    current = engine(blocked=(6, 12))
    current.process(bar(0, 99, 99.4, 98.5, 99, start=start))
    transition = current.process(bar(3, 99.5, 100.2, 99.4, 100, start=start))
    assert transition.resolution.status == "confirmed"
    assert transition.resolution.entry_time == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_consecutive_touch_candles_are_one_episode() -> None:
    current = engine()
    current.process(bar(0, 99, 99.4, 98.5, 99))
    current.process(bar(3, 100, 100.2, 99.5, 99.8))
    assert current.process(bar(6, 99.8, 100.1, 99.6, 99.7)).episode is None
    assert current.episodes_seen == 1


def test_signal_candle_gap_is_rejected() -> None:
    current = engine()
    current.process(bar(0, 99, 99.4, 98.5, 99))
    with pytest.raises(ValueError, match="grid contains a gap"):
        current.process(bar(6, 99, 99.4, 98.5, 99))


@pytest.mark.parametrize("average_30d,expected", [(99, "confirmed"), (100, "rejected_below_30d_average"),
                                                  (101, "rejected_below_30d_average")])
def test_close_above_30_day_filter(average_30d, expected) -> None:
    current = SignalEngine("btc_5d", Decimal("0.5"), 30, require_close_above_30d=True)
    current.process(bar(0, 99, 99.4, 98.5, 99, regime=(100, 100, average_30d)))
    transition = current.process(bar(3, 99.5, 100.2, 99.4, 100, regime=(100, 100, average_30d)))
    assert transition.resolution.status == expected
    assert (transition.resolution.entry_time is not None) == (expected == "confirmed")


@pytest.mark.parametrize("average_30d,expected", [
    (91, "confirmed"),                              # close 100 is 9.9% above: inside the cap
    (90, "rejected_too_far_above_30d_average"),     # 11.1% above: too stretched
    (101, "rejected_below_30d_average"),            # the floor still applies
])
def test_capped_30_day_filter(average_30d, expected) -> None:
    """TRX: buy only when the confirmation closes above the 30-day average, and by no more than 10%."""
    current = SignalEngine("trx_12d", Decimal("0.1"), 30, timeframe_minutes=1, require_close_above_30d=True,
                           maximum_above_30d_pct=Decimal("10"))
    current.process(bar(0, 99, 99.4, 98.5, 99, regime=(100, 100, average_30d)))
    transition = current.process(bar(1, 99.5, 100.2, 99.4, 100, regime=(100, 100, average_30d)))
    assert transition.resolution.status == expected


def test_coins_without_a_cap_are_unchanged() -> None:
    from app.domain.signal_engine import build_signal_engine, maximum_above_30d_pct
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    folder = root if (root / "btc_strategy.json").exists() else Path("/app/config")
    for name, cap in (("btc_strategy.json", None), ("trx_strategy.json", Decimal("10"))):
        strategy = json.loads((folder / name).read_text())
        assert maximum_above_30d_pct(strategy) == cap
        assert build_signal_engine(strategy).require_close_above_30d is True
