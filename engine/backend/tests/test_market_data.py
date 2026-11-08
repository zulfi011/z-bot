from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.market_data import Candle
from app.services.binance_market_data import BinanceMarketData


def test_rest_kline_maps_all_audit_fields() -> None:
    row = [
        1_700_000_040_000,
        "58.10",
        "58.50",
        "57.90",
        "58.30",
        "125.25",
        1_700_000_099_999,
        "7288.50",
        321,
        "60.00",
        "3500.00",
        "0",
    ]

    candle = BinanceMarketData._from_rest("solusdt", row)

    assert candle.symbol == "SOLUSDT"
    assert candle.close == Decimal("58.30")
    assert candle.quote_volume == Decimal("7288.50")
    assert candle.trade_count == 321
    assert candle.source == "binance_rest"
    candle.validate(datetime(2025, 1, 1, tzinfo=timezone.utc))


def test_websocket_parser_accepts_only_valid_closed_payload_data() -> None:
    payload = {
        "E": 1_700_000_100_010,
        "k": {
            "t": 1_700_000_040_000,
            "T": 1_700_000_099_999,
            "s": "SOLUSDT",
            "o": "58.10",
            "h": "58.50",
            "l": "57.90",
            "c": "58.30",
            "v": "125.25",
            "q": "7288.50",
            "n": 321,
        },
    }

    candle = BinanceMarketData._from_stream(payload)

    assert candle.source == "binance_websocket"
    assert candle.source_event_time is not None
    candle.validate(datetime(2025, 1, 1, tzinfo=timezone.utc))


def test_open_or_malformed_candle_is_rejected() -> None:
    open_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    candle = Candle(
        symbol="SOLUSDT",
        open_time=open_time,
        close_time=open_time + timedelta(minutes=1) - timedelta(milliseconds=1),
        open=Decimal("100"),
        high=Decimal("99"),
        low=Decimal("98"),
        close=Decimal("100"),
        volume=Decimal("1"),
        quote_volume=Decimal("100"),
        trade_count=1,
        source="test",
    )

    with pytest.raises(ValueError):
        candle.validate()


def test_live_gap_detection() -> None:
    from app.worker import needs_gap_repair

    last = datetime(2026, 9, 11, 2, 17, tzinfo=timezone.utc)
    assert needs_gap_repair(last, last + timedelta(minutes=1)) is False
    assert needs_gap_repair(last, last + timedelta(minutes=75)) is True
    assert needs_gap_repair(None, last) is False


def test_silent_stream_raises_so_the_worker_reconnects(monkeypatch) -> None:
    from threading import Event

    from app.services import binance_market_data as module

    class QuietSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def recv(self, timeout):
            raise TimeoutError

    ticks = iter(range(0, 1000, 5))
    monkeypatch.setattr(module, "connect", lambda *args, **kwargs: QuietSocket())
    client = module.BinanceMarketData("https://example", "wss://example/ws")
    with pytest.raises(module.StreamSilentError):
        next(client.stream_closed_klines_many(["SOLUSDT"], Event(), max_silence_seconds=130,
                                              clock=lambda: next(ticks)))


def test_reachability_reports_a_blocked_location(monkeypatch):
    from app.services import binance_reachability as reach
    answers = {reach.TRADING_API: (451, b'{"code":0,"msg":"Service unavailable from a restricted location"}'),
               reach.PUBLIC_IP: (200, b'{"ip":"203.0.113.9"}')}
    monkeypatch.setattr(reach, "_get", lambda url, timeout: answers[url])
    result = reach.check(force=True)
    assert result["state"] == "blocked" and result["status_code"] == 451 and result["public_ip"] == "203.0.113.9"
    answers[reach.TRADING_API] = (200, b'{"serverTime":1}')
    assert reach.check(force=True)["state"] == "reachable"
