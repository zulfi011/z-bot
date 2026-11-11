import logging
import signal
import time
from datetime import datetime, timedelta, timezone
from threading import Event

from app.core import credentials
from app.core.settings import get_settings
from app.core.strategy import load_strategies
from app.db.session import get_engine
from app.services.binance_market_data import BinanceMarketData
from app.services.candle_repository import CandleRepository
from app.services.monitoring_service import MonitoringService
from app.services.binance_client import BinanceClient
from app.services.binance_exchange import BinanceExchange
from app.services.live_execution_service import LiveExecutionService, read_settings
from app.services.signal_repository import SignalRepository
from app.services.consolidation_service import ConsolidationService
from app.services.pullback_service import PullbackService
from app.services.signal_service import SignalService


ONE_MINUTE = timedelta(minutes=1)


def last_closed_open_time(now: datetime) -> datetime:
    return now.replace(second=0, microsecond=0) - ONE_MINUTE


def needs_gap_repair(last_stored: datetime | None, incoming_open_time: datetime) -> bool:
    """True when a live candle arrives after one or more missing minutes."""
    return last_stored is not None and incoming_open_time > last_stored + ONE_MINUTE


def backfill(client: BinanceMarketData, repository: CandleRepository, symbol: str,
             backfill_days: int, log: logging.Logger) -> int:
    now = datetime.now(timezone.utc)
    target = last_closed_open_time(now)
    latest = repository.last_open_time(symbol)
    missing = repository.earliest_missing_open_time(symbol, target) if latest else None
    cursor = missing or (latest + ONE_MINUTE if latest else target - timedelta(days=backfill_days) + ONE_MINUTE)
    inserted_total = 0
    while cursor <= target:
        candles = client.fetch_klines(symbol, cursor, target + ONE_MINUTE - timedelta(milliseconds=1))
        if not candles:
            break
        if candles[0].open_time != cursor:
            raise ValueError(f"Market-data gap for {symbol} at {cursor.isoformat()}")
        for previous, current in zip(candles, candles[1:]):
            if current.open_time != previous.open_time + ONE_MINUTE:
                raise ValueError(
                    f"Market-data gap for {symbol}: {previous.open_time.isoformat()} -> {current.open_time.isoformat()}"
                )
        inserted_total += repository.save_many(candles)
        cursor = candles[-1].open_time + ONE_MINUTE
    latest = repository.last_open_time(symbol)
    repository.record_state(
        f"market_data:{symbol}",
        {
            "status": "streaming" if latest and latest >= target else "catching_up",
            "symbol": symbol, "interval": "1m",
            "latest_closed_candle": latest.isoformat() if latest else None,
            "last_backfill_at": now.isoformat(), "backfill_inserted": inserted_total,
            "provider": "binance_spot_rest",
        },
    )
    log.info("Backfill complete: symbol=%s inserted=%d latest=%s", symbol, inserted_total, latest)
    return inserted_total


HEALTH_CHECK_SECONDS = 45


def sync_account(execution: LiveExecutionService, monitoring: MonitoringService, log: logging.Logger,
                 symbol: str | None = None, health: dict | None = None) -> dict | None:
    """Advance trading, then run health checks so a failure shows up as an alert.

    Trading errors must not tear down the market-data stream. Six feeds deliver a candle every minute, and a full
    health scan per candle is wasted work on a small server, so it runs at most every HEALTH_CHECK_SECONDS — but
    always straight after a trading failure, which is exactly when an alert is needed.
    """
    failed = False
    try:
        return execution.synchronize(symbol)
    except Exception:
        failed = True
        log.exception("Trading could not advance")
        return None
    finally:
        due = failed or health is None or time.monotonic() - health.get("checked_at", 0.0) >= HEALTH_CHECK_SECONDS
        if due:
            if health is not None:
                health["checked_at"] = time.monotonic()
            try:
                monitoring.synchronize()
            except Exception:
                log.exception("Health checks failed")


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("z-bot-worker")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    engine = get_engine()
    strategies = load_strategies()
    fee_symbol = next(iter(strategies.values()))["market"]["fee_symbol"]
    backfill_days = {**{symbol: settings.market_data_backfill_days for symbol in strategies},
                     fee_symbol: settings.fee_asset_backfill_days}
    repository = CandleRepository(engine)
    signal_repository = SignalRepository(engine)
    signals = {symbol: SignalService(signal_repository, strategy) for symbol, strategy in strategies.items()}
    # Mode C runs beside the dip rule and writes the same kind of signal, for the coins whose strategy asks for it.
    breakouts = {symbol: service for symbol, service in
                 ((symbol, ConsolidationService(engine, strategy)) for symbol, strategy in strategies.items())
                 if service.enabled}
    # The pullback entry likewise, for the coins that have one.
    pullbacks = {symbol: service for symbol, service in
                 ((symbol, PullbackService(engine, strategy)) for symbol, strategy in strategies.items())
                 if service.enabled}
    client = BinanceClient(settings.binance_api_key, settings.binance_api_secret, settings.binance_api_url,
                           settings.binance_recv_window_ms, credentials=credentials.from_file)
    with engine.begin() as connection:
        mode = str(read_settings(connection).get("trading_mode", "shadow"))
    exchange = BinanceExchange(client, live=mode == "live")
    execution = LiveExecutionService(engine, strategies, exchange)
    monitoring = MonitoringService(engine, strategies, settings.market_data_stale_after_seconds,
                                   started_at=datetime.now(timezone.utc))
    client = BinanceMarketData(settings.binance_rest_url, settings.binance_websocket_url)
    health: dict = {"checked_at": 0.0}
    log.info("Starting trading worker: strategies=%s fee_symbol=%s",
             {symbol: strategy["strategy_id"] for symbol, strategy in strategies.items()}, fee_symbol)

    while not stop.is_set():
        try:
            for item, days in backfill_days.items():
                backfill(client, repository, item, days, log)
            # A first start downloads a month per coin, which takes minutes; by the end the first coins are minutes
            # old. A second pass only fetches those few minutes, so every coin is current before trading starts.
            for item, days in backfill_days.items():
                backfill(client, repository, item, days, log)
            # The "starting up" grace counts from here, once the prices are in, not from when the process began.
            monitoring.started_at = datetime.now(timezone.utc)
            for service in breakouts.values():
                service.synchronize()
            for service in pullbacks.values():
                service.synchronize()
            for service in signals.values():
                # Straight after the backfill: stored days may have changed, so the averages are recalculated.
                status = service.synchronize(recalculate_averages=True)
                log.info("Signal engine synchronized: symbol=%s candles=%d latest=%s", service.symbol,
                         status["candles_replayed"], status["latest_processed_candle"])
            account = sync_account(execution, monitoring, log, health=health)
            log.info("Trading synchronized: mode=%s open_positions=%s",
                     execution.trading_mode(), account["open_positions"] if account else "?")
            for candle in client.stream_closed_klines_many(list(backfill_days), stop):
                last_stored = repository.last_open_time(candle.symbol)
                gap = needs_gap_repair(last_stored, candle.open_time)
                if gap:
                    # The stream resumed after a pause (sleep, network stall) without an error.
                    missing = int((candle.open_time - last_stored) / ONE_MINUTE) - 1
                    log.warning("Gap before live candle: symbol=%s missing=%d; backfilling", candle.symbol, missing)
                    repository.record_event("WARNING", "market_data_gap_repaired",
                                            {"symbol": candle.symbol, "missing_candles": missing,
                                             "after": last_stored.isoformat()})
                    backfill(client, repository, candle.symbol, backfill_days[candle.symbol], log)
                    if candle.symbol in signals:
                        signals[candle.symbol].synchronize(recalculate_averages=True)
                        if candle.symbol in breakouts:
                            breakouts[candle.symbol].synchronize()
                        if candle.symbol in pullbacks:
                            pullbacks[candle.symbol].synchronize()
                saved = repository.save(candle)
                repository.record_state(
                    f"market_data:{candle.symbol}",
                    {
                        "status": "streaming", "symbol": candle.symbol, "interval": "1m",
                        "latest_closed_candle": candle.open_time.isoformat(),
                        "last_message_at": datetime.now(timezone.utc).isoformat(),
                        "last_source": candle.source, "inserted": saved,
                        "provider": "binance_spot_websocket",
                    },
                )
                service = signals.get(candle.symbol)
                if service is None or (not saved and not gap):
                    continue
                if candle.open_time.minute % service.timeframe_minutes == service.timeframe_minutes - 1:
                    service.synchronize()
                # Mode C is checked every minute: its wait ends on a particular minute, and the buy is the one
                # after it, so the signal has to be settled before the account advances past it.
                if candle.symbol in breakouts:
                    breakouts[candle.symbol].synchronize()
                # The pullback's buy is also the minute after its signal, so it is settled here too.
                if candle.symbol in pullbacks:
                    pullbacks[candle.symbol].synchronize()
                # The account advances only when every coin has this minute, so each coin's candle may move it.
                # The trading mode can change from the dashboard at any moment.
                exchange.live = execution.trading_mode() == "live"
                account = sync_account(execution, monitoring, log, candle.symbol, health=health)
                log.info("Closed candle stored: symbol=%s open_time=%s close=%s mode=%s open_positions=%s",
                         candle.symbol, candle.open_time.isoformat(), candle.close,
                         "live" if exchange.live else execution.trading_mode(),
                         account["open_positions"] if account else "?")
        except Exception as error:
            log.exception("Market-data cycle failed")
            try:
                for item in backfill_days:
                    repository.record_state(
                        f"market_data:{item}",
                        {"status": "reconnecting", "symbol": item, "interval": "1m", "error": str(error),
                         "failed_at": datetime.now(timezone.utc).isoformat(), "provider": "binance_spot"},
                    )
                repository.record_event("ERROR", "market_data_connection_failed", {"error": str(error)})
            except Exception:
                log.exception("Could not persist market-data failure")
        stop.wait(settings.market_data_reconnect_seconds)

    log.info("Worker stopped cleanly")


if __name__ == "__main__":
    main()
