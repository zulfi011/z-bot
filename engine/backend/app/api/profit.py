"""Profit summaries and the closed-trade list and CSV export."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import text

from app.api.common import ZERO, _prices
from app.core.strategy import load_strategies
from app.db.session import get_engine
from app.services.account import coin_label

router = APIRouter()


PROFIT_PERIODS = {"24h": 1, "7d": 7, "15d": 15, "30d": 30, "90d": 90}


def _profit_window(period: str, start: datetime | None, end: datetime | None) -> tuple[datetime, datetime, str]:
    now = datetime.now(timezone.utc)
    if period == "custom":
        if not start or not end:
            raise HTTPException(status_code=422, detail="A custom range needs a start and an end date")
        return start, end, "custom"
    if period == "mtd":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now, period
    if period == "all":
        return datetime(2020, 1, 1, tzinfo=timezone.utc), now, period
    if period not in PROFIT_PERIODS:
        raise HTTPException(status_code=422, detail=f"Unsupported period: {period}")
    return now - timedelta(days=PROFIT_PERIODS[period]), now, period


def _profit_rows(connection, start: datetime, end: datetime) -> list[dict]:
    return [dict(row) for row in connection.execute(
        text("SELECT * FROM trades WHERE exit_time >= :start AND exit_time <= :end ORDER BY exit_time"),
        {"start": start, "end": end},
    ).mappings().all()]


def _summarize(rows: list[dict]) -> dict:
    """Costs are already inside net_pnl_usd; gross adds them back so both views are available."""
    fees = sum((row["entry_fee_usd"] + row["exit_fee_usd"] for row in rows), ZERO)
    bnb_fees = sum((row["bnb_fees_usd"] for row in rows), ZERO)
    net = sum((row["net_pnl_usd"] for row in rows), ZERO)
    wins = [row for row in rows if row["net_pnl_usd"] > 0]
    losses = [row for row in rows if row["net_pnl_usd"] < 0]
    won = sum((row["net_pnl_usd"] for row in wins), ZERO)
    lost = -sum((row["net_pnl_usd"] for row in losses), ZERO)
    traded = sum((row["allocation_usd"] for row in rows), ZERO)
    return {
        "trades": len(rows), "wins": len(wins), "losses": len(losses),
        "win_rate_pct": len(wins) / len(rows) * 100 if rows else None,
        "gross_pnl_usd": net + fees, "fees_usd": fees, "fees_in_bnb_usd": bnb_fees,
        "fees_in_usdt_usd": fees - bnb_fees, "net_pnl_usd": net,
        "won_usd": won, "lost_usd": lost, "profit_factor": won / lost if lost else None,
        "average_win_usd": won / len(wins) if wins else None,
        "average_loss_usd": -lost / len(losses) if losses else None,
        "best_usd": max((row["net_pnl_usd"] for row in rows), default=None),
        "worst_usd": min((row["net_pnl_usd"] for row in rows), default=None),
        "traded_value_usd": traded,
        "return_on_traded_pct": net / traded * 100 if traded else None,
        "average_hold_minutes": sum((row["duration_minutes"] for row in rows), 0) / len(rows) if rows else None,
    }


@router.get("/profit")
def profit(period: str = Query(default="7d"), start: datetime | None = None, end: datetime | None = None) -> dict:
    """Money made in a period, after every cost, with a per-coin and per-day breakdown."""
    window_start, window_end, name = _profit_window(period, start, end)
    strategies = load_strategies()
    prices = _prices(list(strategies) + ["BNBUSDT"])
    with get_engine().connect() as connection:
        rows = _profit_rows(connection, window_start, window_end)
        open_rows = [dict(row) for row in connection.execute(
            text("SELECT symbol, quantity, allocation_usd, entry_time FROM positions WHERE status='open'")
        ).mappings().all()]
        bnb_spent = connection.execute(
            text("""SELECT COALESCE(sum(fee_asset_quantity),0) FROM orders
                    WHERE fee_asset='BNB' AND requested_at >= :start AND requested_at <= :end"""),
            {"start": window_start, "end": window_end},
        ).scalar_one()
    open_value = sum((row["quantity"] * prices.get(row["symbol"], ZERO) for row in open_rows), ZERO)
    open_cost = sum((row["allocation_usd"] for row in open_rows), ZERO)
    by_coin = []
    for symbol in strategies:
        coin_rows = [row for row in rows if row["symbol"] == symbol]
        coin_open = [row for row in open_rows if row["symbol"] == symbol]
        unrealized = sum((row["quantity"] * prices.get(symbol, ZERO) - row["allocation_usd"] for row in coin_open), ZERO)
        by_coin.append({"symbol": symbol, "label": coin_label(symbol), "open_lots": len(coin_open),
                        "unrealized_pnl_usd": unrealized, **_summarize(coin_rows)})
    by_coin.sort(key=lambda coin: coin["net_pnl_usd"], reverse=True)
    days: dict[str, dict] = {}
    for row in rows:
        day = row["exit_time"].date().isoformat()
        bucket = days.setdefault(day, {"date": day, "net_pnl_usd": ZERO, "trades": 0})
        bucket["net_pnl_usd"] += row["net_pnl_usd"]
        bucket["trades"] += 1
    running = ZERO
    daily = []
    for day in sorted(days):
        running += days[day]["net_pnl_usd"]
        daily.append({**days[day], "cumulative_usd": running})
    return {
        "period": name, "start": window_start, "end": window_end,
        "summary": {**_summarize(rows), "bnb_spent": bnb_spent,
                    "unrealized_pnl_usd": open_value - open_cost, "open_lots": len(open_rows),
                    "open_value_usd": open_value},
        "coins": by_coin, "daily": daily,
    }


@router.get("/profit/trades.csv")
def profit_trades_csv(period: str = Query(default="30d"), start: datetime | None = None,
                      end: datetime | None = None) -> Response:
    """The same trades as a spreadsheet file."""
    window_start, window_end, _ = _profit_window(period, start, end)
    with get_engine().connect() as connection:
        rows = _profit_rows(connection, window_start, window_end)
    columns = ["exit_time", "symbol", "entry_time", "entry_source", "quantity", "allocation_usd",
               "entry_fill_price", "exit_fill_price", "entry_fee_usd", "exit_fee_usd", "bnb_fees_usd",
               "exit_reason", "duration_minutes", "net_return_pct", "net_pnl_usd"]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row[column] for column in columns])
    return Response(buffer.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="trades-{window_start:%Y%m%d}-{window_end:%Y%m%d}.csv"'})


@router.get("/trades")
def all_trades(limit: int = Query(default=200, ge=1, le=5000)) -> dict:
    with get_engine().connect() as connection:
        rows = connection.execute(text("SELECT * FROM trades ORDER BY exit_time DESC LIMIT :l"), {"l": limit}).mappings().all()
    return {"trades": [dict(row) for row in rows]}
