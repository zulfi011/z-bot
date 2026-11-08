"""The shadow wallet: a starting amount the user sets, plus the results of shadow trades only."""

from decimal import Decimal
from unittest.mock import MagicMock

from app.services import live_execution_service as service


def connection(realized: str, open_rows: list[dict]) -> MagicMock:
    conn = MagicMock()
    conn.execute.return_value.scalar_one.return_value = Decimal(realized)
    conn.execute.return_value.mappings.return_value.all.return_value = open_rows
    return conn


def test_no_starting_amount_means_no_shadow_wallet():
    assert service.shadow_account(connection("0", []), {"shadow_start_usd": "0"}) is None
    assert service.shadow_account(connection("0", []), {}) is None


def test_wallet_is_start_plus_closed_results_plus_open_lots_at_market(monkeypatch):
    monkeypatch.setattr(service, "latest_price", lambda conn, symbol: Decimal("110"))
    rows = [{"symbol": "SOLUSDT", "quantity": Decimal("1"), "allocation_usd": Decimal("100")}]
    shadow = service.shadow_account(connection("-5", rows), {"shadow_start_usd": "500"})
    assert shadow["free"] == Decimal("395")        # 500 - 5 lost - 100 in the open lot
    assert shadow["open_value"] == Decimal("110")
    assert shadow["wallet"] == Decimal("505")      # 395 free + 110 lot
    assert shadow["pnl"] == Decimal("5")           # -5 closed + 10 open


def test_shadow_buys_stop_when_the_pretend_money_runs_out():
    assert service.affordable_lot(Decimal("100"), Decimal("0")) is None


def test_growth_plan_works_for_any_amount():
    plan = lambda value: (lambda p: (p.lots, p.lot_size_usd) if p else None)(service.suggested_pot(Decimal(value)))
    assert plan("20") is None                      # 3 lots would be under the $10 minimum
    assert plan("30") == (3, Decimal("10"))
    assert plan("250") == (3, Decimal("83"))       # below $300: 3 equal whole-dollar lots
    assert plan("300") == (3, Decimal("100"))      # the tested plan from here
    assert plan("499") == (4, Decimal("100"))
    assert plan("500") == (5, Decimal("100"))
    assert plan("1000") == (5, Decimal("200"))
    assert plan("1099") == (5, Decimal("200"))
    assert plan("10000") == (5, Decimal("2000"))
    for value in ("30", "250", "300", "777", "1000", "123456"):
        lots, lot = plan(value)
        assert lots * lot <= Decimal(value)        # never suggests more than the money there is
