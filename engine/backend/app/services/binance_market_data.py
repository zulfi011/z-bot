import json
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from websockets.sync.client import connect

from app.domain.market_data import Candle, utc_from_milliseconds


class StreamSilentError(ConnectionError):
    """The WebSocket is open but has stopped delivering closed candles."""


class BinanceMarketData:
    def __init__(self, rest_url: str, websocket_url: str, timeout_seconds: int = 15) -> None:
        self.rest_url = rest_url.rstrip("/")
        self.websocket_url = websocket_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def fetch_klines(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> list[Candle]:
        params = urlencode(
            {
                "symbol": symbol.upper(),
                "interval": "1m",
                "startTime": int(start_time.timestamp() * 1000),
                "endTime": int(end_time.timestamp() * 1000),
                "limit": min(limit, 1000),
            }
        )
        request = Request(
            f"{self.rest_url}/api/v3/klines?{params}",
            headers={"User-Agent": "z-bot/1.0"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.load(response)
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected Binance response: {payload!r}")

        now = datetime.now(timezone.utc)
        candles = [self._from_rest(symbol, row) for row in payload]
        closed = [candle for candle in candles if candle.close_time < now]
        for candle in closed:
            candle.validate(now)
        return closed

    def stream_closed_klines(self, symbol: str, stop) -> Iterator[Candle]:
        stream_url = f"{self.websocket_url}/{symbol.lower()}@kline_1m"
        with connect(stream_url, open_timeout=self.timeout_seconds, close_timeout=5) as websocket:
            while not stop.is_set():
                try:
                    payload = json.loads(websocket.recv(timeout=5))
                except TimeoutError:
                    continue
                kline = payload.get("k", {})
                if not kline.get("x"):
                    continue
                candle = self._from_stream(payload)
                candle.validate()
                yield candle

    def stream_closed_klines_many(self, symbols: list[str], stop, max_silence_seconds: float = 130,
                                  clock=time.monotonic) -> Iterator[Candle]:
        """Consume several one-minute feeds over Binance's combined stream.

        Raises StreamSilentError when no closed candle arrives for
        `max_silence_seconds`, so the caller reconnects and backfills instead of
        trusting a connection that survived a sleep or a network stall.
        """
        if not symbols:
            return
        streams = "/".join(f"{symbol.lower()}@kline_1m" for symbol in symbols)
        base_url = self.websocket_url[:-3] if self.websocket_url.endswith("/ws") else self.websocket_url
        stream_url = f"{base_url}/stream?streams={streams}"
        with connect(stream_url, open_timeout=self.timeout_seconds, close_timeout=5) as websocket:
            last_closed = clock()
            while not stop.is_set():
                if clock() - last_closed > max_silence_seconds:
                    raise StreamSilentError(f"No closed candle for {max_silence_seconds:.0f}s; reconnecting")
                try:
                    payload = json.loads(websocket.recv(timeout=5))
                except TimeoutError:
                    continue
                event = payload.get("data", payload)
                kline = event.get("k", {})
                if not kline.get("x"):
                    continue
                candle = self._from_stream(event)
                candle.validate()
                last_closed = clock()
                yield candle

    @staticmethod
    def _from_rest(symbol: str, row: list) -> Candle:
        if len(row) < 11:
            raise ValueError("Binance kline row is incomplete")
        return Candle(
            symbol=symbol.upper(),
            open_time=utc_from_milliseconds(int(row[0])),
            open=Decimal(str(row[1])),
            high=Decimal(str(row[2])),
            low=Decimal(str(row[3])),
            close=Decimal(str(row[4])),
            volume=Decimal(str(row[5])),
            close_time=utc_from_milliseconds(int(row[6])),
            quote_volume=Decimal(str(row[7])),
            trade_count=int(row[8]),
            source="binance_rest",
        )

    @staticmethod
    def _from_stream(payload: dict) -> Candle:
        kline = payload["k"]
        return Candle(
            symbol=str(kline["s"]).upper(),
            open_time=utc_from_milliseconds(int(kline["t"])),
            close_time=utc_from_milliseconds(int(kline["T"])),
            open=Decimal(str(kline["o"])),
            high=Decimal(str(kline["h"])),
            low=Decimal(str(kline["l"])),
            close=Decimal(str(kline["c"])),
            volume=Decimal(str(kline["v"])),
            quote_volume=Decimal(str(kline["q"])),
            trade_count=int(kline["n"]),
            source="binance_websocket",
            source_event_time=utc_from_milliseconds(int(payload["E"])),
        )
