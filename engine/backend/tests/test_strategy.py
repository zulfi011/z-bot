import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.strategy import validate_strategy


def _load(name: str) -> dict:
    candidates = [Path(__file__).resolve().parents[2] / name, Path("/app/config") / name]
    return json.loads(next(path for path in candidates if path.exists()).read_text())


STRATEGY = _load("sol_strategy.json")
ETH_STRATEGY = _load("eth_strategy.json")
BTC_STRATEGY = _load("btc_strategy.json")
AAVE_STRATEGY = _load("aave_strategy.json")
TRX_STRATEGY = _load("trx_strategy.json")


def test_repository_strategy_is_valid() -> None:
    strategy = validate_strategy(copy.deepcopy(STRATEGY))
    assert strategy["averages"]["signal_average_days"] == 12
    assert strategy["exit"]["maximum_hold_minutes"] is None
    assert "default_lot_size_usd" not in strategy["portfolio"]  # money is set in the dashboard, never in a strategy
    assert strategy["entry"]["blocked_entry_hours_utc"] == {"start": 6, "end": 12}


def test_eth_strategy_is_valid_and_distinct() -> None:
    strategy = validate_strategy(copy.deepcopy(ETH_STRATEGY))
    assert strategy["market"]["symbol"] == "ETHUSDT"
    assert strategy["market"]["signal_timeframe"] == "5m"
    assert strategy["averages"]["signal_average_days"] == 7
    assert strategy["exit"]["protective_stop_pct_from_entry_fill"] == 4.5
    assert strategy["exit"]["trailing_stop"] == {**strategy["exit"]["trailing_stop"],
                                                 "activation_pct_from_entry_fill": 1.315, "giveback_of_open_profit_pct": 30.0}
    assert strategy["strategy_id"] != STRATEGY["strategy_id"]
    assert strategy["entry"]["pullback_to_trend"]["ema_minutes"] == 1440
    assert strategy["entry"]["pullback_to_trend"]["dwell_minutes"] == 180
    assert strategy["entry"]["pullback_to_trend"]["requires_uptrend"] is True


def test_only_eth_has_the_pullback_entry() -> None:
    from app.core.strategy import load_strategies
    assert [symbol for symbol, s in load_strategies().items() if s["entry"].get("pullback_to_trend")] == ["ETHUSDT"]


@pytest.mark.parametrize("field,value", [("ema_minutes", 30), ("ema_minutes", 1440.5), ("dwell_minutes", 0),
                                         ("dwell_minutes", 5000)])
def test_a_broken_pullback_block_is_refused(field, value) -> None:
    strategy = copy.deepcopy(ETH_STRATEGY)
    strategy["entry"]["pullback_to_trend"][field] = value
    with pytest.raises(RuntimeError, match="pullback"):
        validate_strategy(strategy)


def test_btc_strategy_uses_the_30_day_filter() -> None:
    strategy = validate_strategy(copy.deepcopy(BTC_STRATEGY))
    assert strategy["market"]["symbol"] == "BTCUSDT"
    assert strategy["averages"]["signal_average_days"] == 5
    assert strategy["entry"]["touch_zone_pct"] == 0.2
    assert strategy["entry"]["trend_filter"]["type"] == "confirmation_close_above_average_30d"
    assert strategy["exit"]["protective_stop_pct_from_entry_fill"] == 3.0
    assert strategy["exit"]["trailing_stop"]["activation_pct_from_entry_fill"] == 1.257
    assert strategy["exit"]["trailing_stop"]["giveback_of_open_profit_pct"] == 14.0


@pytest.mark.parametrize("strategy,expected", [
    (AAVE_STRATEGY, ("AAVEUSDT", "3m", 10, 0.1, 4.0, 1.75, 20.0, False)),
])
def test_aave_and_link_strategies_match_their_research(strategy, expected) -> None:
    strategy = validate_strategy(copy.deepcopy(strategy))
    trail = strategy["exit"]["trailing_stop"]
    assert (strategy["market"]["symbol"], strategy["market"]["signal_timeframe"], strategy["averages"]["signal_average_days"],
            strategy["entry"]["touch_zone_pct"], strategy["exit"]["protective_stop_pct_from_entry_fill"],
            trail["activation_pct_from_entry_fill"], trail["giveback_of_open_profit_pct"],
            "trend_filter" in strategy["entry"]) == expected
    assert strategy["entry"]["blocked_entry_hours_utc"] == {"start": 6, "end": 12}


def test_every_coin_has_a_unique_strategy() -> None:
    ids = [s["strategy_id"] for s in (STRATEGY, ETH_STRATEGY, BTC_STRATEGY, AAVE_STRATEGY, TRX_STRATEGY)]
    assert len(set(ids)) == len(ids)


def test_trx_strategy_matches_its_research() -> None:
    strategy = validate_strategy(copy.deepcopy(TRX_STRATEGY))
    trail = strategy["exit"]["trailing_stop"]
    assert (strategy["market"]["symbol"], strategy["market"]["signal_timeframe"], strategy["averages"]["signal_average_days"],
            strategy["entry"]["touch_zone_pct"], strategy["exit"]["protective_stop_pct_from_entry_fill"],
            trail["activation_pct_from_entry_fill"], trail["giveback_of_open_profit_pct"]) == \
        ("TRXUSDT", "1m", 12, 0.1, 4.0, 1.245, 10.0)
    assert strategy["entry"]["trend_filter"]["maximum_above_average_pct"] == 10
    assert "blocked_entry_hours_utc" not in strategy["entry"]            # the TRX candidate trades all hours


@pytest.mark.parametrize("path,value", [
    (("market", "symbol"), "DOGEUSDT"),
    (("entry", "trend_filter"), {"type": "moon_phase"}),
    (("entry", "trend_filter"), {"type": "confirmation_close_above_average_30d", "maximum_above_average_pct": -5}),
    (("averages", "signal_average_days"), 0),
    (("portfolio", "minimum_lot_size_usd"), 1),
    (("portfolio", "maximum_lots_per_coin"), 0),
])
def test_invalid_strategies_are_refused(path, value) -> None:
    strategy = copy.deepcopy(STRATEGY)
    target = strategy
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_strategy(strategy)


@pytest.mark.parametrize("pasted", [
    "postgresql://u:p@h:5432/db", ' "postgresql://u:p@h:5432/db" ', "DATABASE_URL=postgresql://u:p@h:5432/db\n",
    "postgres://u:p@h:5432/db",
])
def test_database_url_accepts_common_paste_mistakes(pasted) -> None:
    from app.core.settings import normalize_database_url
    assert normalize_database_url(pasted) == "postgresql+psycopg://u:p@h:5432/db"


def test_eth_strategy_carries_the_trend_exit() -> None:
    """The deployed ETH file must describe the trend ride, or the engine silently falls back to the giveback."""
    from app.domain.paper_execution import ExecutionConfig

    config = ExecutionConfig.from_strategy(copy.deepcopy(ETH_STRATEGY))
    assert config.trend_exit_ema_minutes == 960
    assert config.trend_exit_requires_uptrend is True
    assert config.stop_pct == Decimal("4.5")


def test_sol_carries_its_own_trend_exit_and_keeps_its_tight_stop() -> None:
    """SOL's line is 8 hours, not ETH's 16, and its -2% stop must not drift toward ETH's -4.5%:
    widening SOL's stop cost a third of its profit in the backtest."""
    from app.domain.paper_execution import ExecutionConfig

    config = ExecutionConfig.from_strategy(copy.deepcopy(STRATEGY))
    assert config.trend_exit_ema_minutes == 480
    assert config.trend_exit_requires_uptrend is True
    assert config.stop_pct == Decimal("2.0")
    assert config.trail_activation_pct == Decimal("1.251")
    assert config.trail_giveback_pct == Decimal("12.0")
    assert config.breakout_stop_pct == Decimal("4.0")


def test_only_the_tested_coins_use_the_trend_exit() -> None:
    """BTC, AAVE and TRX were tested and did not benefit, so their files must not carry it by accident.

    AAVE is the interesting one: on paper a trend exit added about $100, but a walk-forward selection test
    put its honest contribution at $2. It gets the quiet-band breakout and keeps its giveback exit.
    """
    from app.domain.paper_execution import ExecutionConfig

    for strategy in (BTC_STRATEGY, AAVE_STRATEGY, TRX_STRATEGY):
        assert ExecutionConfig.from_strategy(copy.deepcopy(strategy)).trend_exit_ema_minutes is None


def test_trx_keeps_its_deployed_exit_but_gains_breakout() -> None:
    """Every trend line tested made TRX worse, and an exit retune looked good only in hindsight, so the
    exit numbers must stay exactly as deployed. The quiet-band breakout is the whole change."""
    from app.domain.consolidation import ConsolidationConfig
    from app.domain.paper_execution import ExecutionConfig

    config = ExecutionConfig.from_strategy(copy.deepcopy(TRX_STRATEGY))
    assert config.trend_exit_ema_minutes is None
    assert config.stop_pct == Decimal("4.0")
    assert config.trail_activation_pct == Decimal("1.245")
    assert config.trail_giveback_pct == Decimal("10.0")
    assert config.breakout_stop_pct == Decimal("3.0")

    rule = ConsolidationConfig.from_strategy(copy.deepcopy(TRX_STRATEGY))
    assert (rule.chart_minutes, rule.zone_bars) == (60, 40)
    assert rule.maximum_zone_pct == Decimal("2.0")
    assert rule.confirmation_wait_minutes == 3
    assert rule.blocked_entry_hours is None          # TRX trades around the clock


def test_aave_keeps_its_giveback_exit_but_gains_breakout() -> None:
    from app.domain.consolidation import ConsolidationConfig
    from app.domain.paper_execution import ExecutionConfig

    config = ExecutionConfig.from_strategy(copy.deepcopy(AAVE_STRATEGY))
    assert config.trend_exit_ema_minutes is None
    assert config.stop_pct == Decimal("4.0")
    assert config.trail_giveback_pct == Decimal("20.0")
    assert config.breakout_stop_pct == Decimal("3.5")
    # a breakout lot still exits on the giveback, just with its own numbers
    assert config.for_source("breakout").trail_giveback_pct == Decimal("22.0")

    rule = ConsolidationConfig.from_strategy(copy.deepcopy(AAVE_STRATEGY))
    assert (rule.chart_minutes, rule.zone_bars) == (30, 24)
    assert rule.maximum_zone_pct == Decimal("2.0")
    assert rule.confirmation_wait_minutes == 60
