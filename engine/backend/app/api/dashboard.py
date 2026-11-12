"""The dashboard read model: strategies, the whole-dashboard view, wallet history and the leaderboard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app.api.coin_view import _coin_view, _trade_stats
from app.api.common import (
    CHART_INTERVALS,
    EQUITY_PERIOD_DAYS,
    LEADERBOARD_PERIOD_DAYS,
    ZERO,
    _budget,
    _coin_symbol,
    _equity_bucket,
    _latest_snapshot,
    _prices,
    wallet,
)
from app.core.strategy import COIN_NAMES, load_strategies, load_strategy
from app.db.session import get_engine
from app.domain.execution import ExecutionConfig, FeeContext
from app.services.account import (
    affordable_lot,
    coin_label,
    read_pot,
    read_settings,
    read_trading_enabled,
    shadow_account,
    suggested_pot,
)
from app.services.monitoring_service import bnb_round_trip_usd

router = APIRouter()


@router.get("/strategy")
def strategy_documents() -> dict:
    return load_strategies()


@router.get("/strategy/{symbol}")
def strategy_document(symbol: str) -> dict:
    return load_strategy(_coin_symbol(symbol))


@router.get("/dashboard")
def dashboard(interval: str = Query(default="15m"), chart: str | None = Query(default=None)) -> dict:
    """One consistent read model for every dashboard page: the account plus one section per coin.

    `chart` names the coin whose price chart is on screen; the other coins are sent without one.
    """
    if interval not in CHART_INTERVALS:
        raise HTTPException(status_code=422, detail=f"Unsupported chart interval: {interval}")
    chart_symbol = chart.upper() if chart else None
    strategies = load_strategies()
    first = next(iter(strategies.values()))
    fee_symbol = first["market"]["fee_symbol"]
    now = datetime.now(timezone.utc)
    binance = wallet()
    usdt_free = Decimal(str(binance.get("usdt", {}).get("free", "0"))) if binance.get("connected") else ZERO
    bnb_free = Decimal(str(binance.get("bnb", {}).get("free", "0"))) if binance.get("connected") else ZERO
    with get_engine().begin() as connection:
        account = _latest_snapshot(connection)
        settings = read_settings(connection)
        shadow = shadow_account(connection, settings) if settings.get("trading_mode") != "live" else None
        if shadow:
            usdt_free = shadow["free"]  # shadow buys spend the pretend wallet
        open_rows = [dict(row) for row in connection.execute(
            text("SELECT * FROM positions WHERE status='open' ORDER BY entry_time")
        ).mappings().all()]
        bnb_market = connection.execute(
            text("SELECT open_time, close FROM candles_1m WHERE symbol=:s ORDER BY open_time DESC LIMIT 1"),
            {"s": fee_symbol},
        ).mappings().one_or_none()
        fee_context = FeeContext(bool(binance.get("bnb_fee_discount")), bnb_free,
                                 bnb_market["close"] if bnb_market else None)
        coins = {symbol: _coin_view(connection, strategy, usdt_free, open_rows, interval, now, fee_context,
                                    with_chart=symbol == chart_symbol)
                 for symbol, strategy in strategies.items()}
        execution_state = connection.execute(
            text("SELECT value FROM engine_state WHERE key='live_execution'")
        ).scalar_one_or_none() or {}
        monitor = connection.execute(
            text("SELECT value FROM engine_state WHERE key='monitoring'")
        ).scalar_one_or_none() or {}
        trades = [dict(row) for row in connection.execute(
            text("SELECT * FROM trades ORDER BY exit_time DESC LIMIT 25")
        ).mappings().all()]
        requests = [dict(row) for row in connection.execute(
            text("SELECT * FROM control_requests ORDER BY requested_at DESC LIMIT 25")
        ).mappings().all()]
        stats = _trade_stats(connection, None)
        budget = _budget(connection, usdt_free)
        if shadow:
            # Shadow mode: the money is the shadow wallet (free + what its open lots cost).
            budget["budget_usd"] = shadow["free"] + shadow["open_cost"]
            budget["left_usd"] = budget["budget_usd"] - budget["allocated_usd"]
        pot = read_pot(connection)
        bnb_usage = dict(connection.execute(
            text(
                """
                SELECT COALESCE(sum(fee_bnb), 0) AS bnb_spent, COALESCE(sum(fee_usd) FILTER (WHERE fee_asset='BNB'), 0) AS bnb_fees_usd,
                       COALESCE(sum(fee_usd) FILTER (WHERE fee_asset='USDT'), 0) AS usdt_fees_usd,
                       count(*) FILTER (WHERE fee_asset='BNB') AS bnb_fills, count(*) FILTER (WHERE fee_asset='USDT') AS usdt_fills
                FROM orders
                """
            )
        ).mappings().one())
        alerts = [dict(row) for row in connection.execute(
            text(
                """
                SELECT alert_key, severity, status, title, message, first_seen_at, last_seen_at, resolved_at
                FROM monitoring_alerts ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, last_seen_at DESC LIMIT 15
                """
            )
        ).mappings().all()]
        logs = [dict(row) for row in connection.execute(
            text("SELECT id, timestamp, level, component, event_type, details FROM system_events ORDER BY timestamp DESC LIMIT 30")
        ).mappings().all()]
    config = ExecutionConfig.from_strategy(first)
    # BNB coverage is measured on the largest lot any coin buys.
    lot_size = pot.lot_size_usd
    round_trip_usd = bnb_round_trip_usd(first, lot_size)
    bnb_price = bnb_market["close"] if bnb_market else None
    bnb_balance = bnb_free
    bnb_value = bnb_balance * bnb_price if bnb_price else ZERO
    ages = [coin["health"]["market_age_seconds"] for coin in coins.values()]
    positions = [position for coin in coins.values() for position in coin["positions"]]
    positions.sort(key=lambda position: position["entry_time"])
    return {
        "generated_at": now,
        "coin_order": list(coins),
        "coins": coins,
        "health": {
            "status": monitor.get("status", "starting"),
            "market_age_seconds": None if None in ages else max(ages),
            "coins_updated": {symbol: (execution_state.get(symbol) or {}).get("last_open_time")
                              for symbol in coins},
        },
        "account": account,
        "binance": {"connected": bool(binance.get("connected")), "message": binance.get("message"),
                    "usdt_free": usdt_free, "wallet_value_usdt": binance.get("total_value_usdt"),
                    "checks": binance.get("checks", [])},
        "trading": {"mode": settings.get("trading_mode", "shadow"),
                    "daily_loss_limit_usd": settings.get("daily_loss_limit_usd"),
                    "maximum_open_value_usd": settings.get("maximum_open_value_usd"),
                    "shadow_start_usd": settings.get("shadow_start_usd")},
        "shadow": ({key: str(value) for key, value in shadow.items()} if shadow else None),
        "money": {
            "usdt_free": usdt_free,
            "budget_usd": budget["budget_usd"],
            "left_to_allocate_usd": budget["left_usd"],
            "allocated_usd": budget["allocated_usd"],
            "pot": {"lots": pot.lots, "lot_size_usd": pot.lot_size_usd, "total_usd": pot.total_usd,
                    "open_lots": len(open_rows), "free_lots": max(0, pot.lots - len(open_rows)),
                    "next_lot_usd": (affordable_lot(pot.lot_size_usd, usdt_free)
                                     if len(open_rows) < pot.lots and pot.lot_size_usd > ZERO else None),
                    "coins_on": sum(1 for coin in coins.values() if coin["trading_enabled"])},
            "in_trades_usd": sum((Decimal(str(coin["money"]["open_cost_usd"])) for coin in coins.values()), ZERO),
            "suggested_pot": (lambda plan: {"lots": plan.lots, "lot_size_usd": plan.lot_size_usd} if plan else None)(
                suggested_pot(budget["budget_usd"], Decimal(str(first["portfolio"]["minimum_lot_size_usd"])))),
            "pot_set_by_user": bool(settings.get("pot_set_by_user")),
            "limits": {"minimum_lot_usd": first["portfolio"]["minimum_lot_size_usd"],
                       "maximum_lot_usd": first["portfolio"]["maximum_lot_size_usd"],
                       "maximum_lots": first["portfolio"]["maximum_lots_per_coin"]},
            "coins": [coin["money"] for coin in coins.values()],
        },
        "bnb": {
            "enabled": bool(binance.get("bnb_fee_discount")), "price": bnb_price, "balance": bnb_balance,
            "value_usd": bnb_value, "lot_size_usd": lot_size, "round_trip_fee_usd": round_trip_usd,
            "round_trip_fee_bnb": round_trip_usd / bnb_price if bnb_price else None,
            "round_trips_left": int(bnb_value / round_trip_usd) if round_trip_usd else None,
            "spent_bnb": bnb_usage["bnb_spent"], "bnb_fees_usd": bnb_usage["bnb_fees_usd"],
            "usdt_fees_usd": bnb_usage["usdt_fees_usd"], "bnb_fills": bnb_usage["bnb_fills"],
            "usdt_fills": bnb_usage["usdt_fills"],
            "saved_usd": bnb_usage["bnb_fees_usd"] * (config.usdt_fee_bps / config.bnb_fee_bps - 1),
            "updated_at": bnb_market["open_time"] if bnb_market else None,
        },
        "stats": stats,
        "positions": positions, "trades": trades, "requests": requests,
        "chart_interval": interval, "alerts": alerts, "logs": logs,
    }


@router.get("/equity-history")
def equity_history(period: str = Query(default="7d")) -> dict:
    """Wallet value and trading profit over time, from the per-minute snapshots."""
    now = datetime.now(timezone.utc)
    with get_engine().connect() as connection:
        first = connection.execute(text("SELECT min(timestamp) FROM account_snapshots")).scalar_one()
        if period == "all":
            start = first or now - timedelta(days=1)
        elif period in EQUITY_PERIOD_DAYS:
            start = now - timedelta(days=EQUITY_PERIOD_DAYS[period])
        else:
            raise HTTPException(status_code=422, detail=f"Unsupported period: {period}")
        bucket = _equity_bucket(now - max(start, first or start))
        rows = connection.execute(
            text(
                f"""
                SELECT date_bin(INTERVAL '{bucket}', timestamp, TIMESTAMPTZ '1970-01-01') AS timestamp,
                       (array_agg(wallet_value_usd ORDER BY timestamp DESC))[1] AS wallet_value_usd,
                       (array_agg(usdt_free ORDER BY timestamp DESC))[1] AS usdt_free,
                       (array_agg(open_position_value_usd ORDER BY timestamp DESC))[1] AS positions_usd,
                       (array_agg(bnb_value_usd ORDER BY timestamp DESC))[1] AS bnb_value_usd,
                       (array_agg(strategy_pnl_usd ORDER BY timestamp DESC))[1] AS strategy_pnl_usd,
                       (array_agg(realized_pnl_usd ORDER BY timestamp DESC))[1] AS realized_pnl_usd
                FROM account_snapshots WHERE timestamp BETWEEN :start AND :end GROUP BY 1 ORDER BY 1
                """
            ),
            {"start": start, "end": now},
        ).mappings().all()
    points = [dict(row) for row in rows]
    summary = None
    if points:
        pnl = [point["strategy_pnl_usd"] for point in points]
        summary = {"strategy_pnl_change_usd": pnl[-1] - pnl[0],
                   "high_value_usd": max(p["wallet_value_usd"] for p in points),
                   "low_value_usd": min(p["wallet_value_usd"] for p in points)}
    # The chart spans the whole range asked for, so a week with one day of history shows as the last day of a week.
    return {"period": period, "bucket": bucket, "start": start, "end": now, "points": points, "summary": summary}


@router.get("/leaderboard")
def leaderboard(period: str = Query(default="7d")) -> dict:
    """Coins ranked by what they actually made: closed trades plus open lots at today's price."""
    if period != "all" and period not in LEADERBOARD_PERIOD_DAYS:
        raise HTTPException(status_code=422, detail=f"Unsupported period: {period}")
    strategies = load_strategies()
    prices = _prices(list(strategies))
    now = datetime.now(timezone.utc)
    start = (datetime(2020, 1, 1, tzinfo=timezone.utc) if period == "all"
             else now - timedelta(days=LEADERBOARD_PERIOD_DAYS[period]))
    with get_engine().connect() as connection:
        trades = [dict(row) for row in connection.execute(
            text("""SELECT symbol, exit_time, net_pnl_usd FROM trades
                    WHERE exit_time >= :start ORDER BY exit_time"""),
            {"start": start},
        ).mappings().all()]
        open_rows = [dict(row) for row in connection.execute(
            text("SELECT symbol, quantity, allocation_usd FROM positions WHERE status='open'")
        ).mappings().all()]
        enabled_by_coin = {symbol: read_trading_enabled(connection, symbol) for symbol in strategies}
        pot = read_pot(connection)
    coins = []
    for symbol in strategies:
        enabled = enabled_by_coin[symbol]
        coin_trades = [row for row in trades if row["symbol"] == symbol]
        coin_open = [row for row in open_rows if row["symbol"] == symbol]
        realized = sum((row["net_pnl_usd"] for row in coin_trades), ZERO)
        unrealized = sum((row["quantity"] * prices.get(symbol, ZERO) - row["allocation_usd"] for row in coin_open), ZERO)
        # Coins share one pot, so each coin's return is measured against the whole pot it trades from.
        capital = pot.total_usd
        running = ZERO
        series = []
        for row in coin_trades:
            running += row["net_pnl_usd"]
            series.append({"t": row["exit_time"], "pnl_usd": running})
        coins.append({
            "symbol": symbol, "label": coin_label(symbol), "name": COIN_NAMES.get(symbol, coin_label(symbol)),
            "trading_enabled": enabled, "capital_usd": capital, "pnl_usd": realized + unrealized,
            "realized_usd": realized, "unrealized_usd": unrealized,
            "return_pct": (realized + unrealized) / capital * 100 if capital else ZERO,
            "trades": len(coin_trades), "wins": len([r for r in coin_trades if r["net_pnl_usd"] > 0]),
            "open_lots": len(coin_open), "series": series,
        })
    coins.sort(key=lambda coin: (coin["return_pct"], coin["pnl_usd"]), reverse=True)
    for rank, coin in enumerate(coins, start=1):
        coin["rank"] = rank
    return {"period": period, "start": start, "generated_at": now, "coins": coins}
