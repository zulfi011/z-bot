import json
from functools import lru_cache
from pathlib import Path

from app.core.settings import get_settings


# Display order. Each coin: (settings attribute for its config path, repository file name).
COIN_CONFIGS = {
    "SOLUSDT": ("strategy_config_path", "sol_strategy.json"),
    "ETHUSDT": ("eth_strategy_config_path", "eth_strategy.json"),
    "BTCUSDT": ("btc_strategy_config_path", "btc_strategy.json"),
    "AAVEUSDT": ("aave_strategy_config_path", "aave_strategy.json"),
    "TRXUSDT": ("trx_strategy_config_path", "trx_strategy.json"),
}
SUPPORTED_SYMBOLS = tuple(COIN_CONFIGS)
COIN_NAMES = {"SOLUSDT": "Solana", "ETHUSDT": "Ethereum", "BTCUSDT": "Bitcoin", "AAVEUSDT": "Aave",
              "TRXUSDT": "Tron"}


def validate_strategy(strategy: dict) -> dict:
    required = {
        "schema_version", "strategy_id", "market", "averages",
        "entry", "exit", "portfolio", "execution_model", "evaluation",
    }
    missing = sorted(required - strategy.keys())
    if missing:
        raise RuntimeError(f"Strategy is missing keys: {missing}")
    if strategy["schema_version"] != 2:
        raise RuntimeError("A schema_version 2 strategy is required")
    if strategy["market"]["symbol"] not in SUPPORTED_SYMBOLS or strategy["market"]["fee_symbol"] != "BNBUSDT":
        raise RuntimeError(f"The bot runs {', '.join(SUPPORTED_SYMBOLS)} strategies with BNBUSDT fee pricing")
    if strategy["market"]["signal_timeframe"] not in {"1m", "3m", "5m"}:
        raise RuntimeError("Unsupported signal timeframe")
    days = strategy["averages"]["signal_average_days"]
    if not isinstance(days, int) or not 1 <= days <= 60:
        raise RuntimeError("Signal average must be a whole number of days between 1 and 60")
    portfolio = strategy["portfolio"]
    if not 5 <= portfolio["minimum_lot_size_usd"] <= portfolio["maximum_lot_size_usd"]:
        raise RuntimeError("Lot sizes must satisfy $5 <= minimum <= maximum")
    if not 1 <= portfolio["maximum_lots_per_coin"] <= 100:
        raise RuntimeError("The per-coin lot maximum must be between 1 and 100")
    trend = strategy["entry"].get("trend_filter")
    if trend and trend.get("type") != "confirmation_close_above_average_30d":
        raise RuntimeError("Unsupported trend filter")
    cap = (trend or {}).get("maximum_above_average_pct")
    if cap is not None and not (isinstance(cap, (int, float)) and 0 < cap <= 100):
        raise RuntimeError("maximum_above_average_pct must be a number between 0 and 100")
    hours = strategy["entry"].get("blocked_entry_hours_utc")
    if hours and not 0 <= hours["start"] < hours["end"] <= 24:
        raise RuntimeError("Blocked entry hours must satisfy 0 <= start < end <= 24")
    breakout = strategy["entry"].get("consolidation_breakout")
    if breakout:
        if breakout["chart_minutes"] % 1 or not 1 <= breakout["chart_minutes"] <= 1440:
            raise RuntimeError("The consolidation chart must be between 1 and 1440 minutes")
        if not 2 <= breakout["zone_bars"] <= 200:
            raise RuntimeError("A consolidation zone needs between 2 and 200 bars")
        if not 0 < breakout["maximum_zone_pct"] <= 20:
            raise RuntimeError("maximum_zone_pct must be a number between 0 and 20")
        if not 0 <= breakout["confirmation_wait_minutes"] <= 1440:
            raise RuntimeError("The consolidation wait must be between 0 and 1440 minutes")
        missing_exit = sorted({"protective_stop_pct_from_entry_fill", "activation_pct_from_entry_fill",
                               "giveback_of_open_profit_pct"} - (breakout.get("exit") or {}).keys())
        if missing_exit:
            raise RuntimeError(f"The consolidation entry is missing exit rules: {missing_exit}")
    pyramid = strategy["entry"].get("pyramid_add")
    if pyramid:
        step = pyramid.get("step_pct")
        if not isinstance(step, (int, float)) or not 0 < step <= 50:
            raise RuntimeError("The pyramid step must be a percentage between 0 and 50")
        if not isinstance(pyramid.get("maximum_adds"), int) or not 1 <= pyramid["maximum_adds"] <= 10:
            raise RuntimeError("A pyramid may add between 1 and 10 lots to a parent")
        if pyramid.get("add_exit", "own") not in {"own", "with_parent"}:
            raise RuntimeError("A pyramid add either exits on its own or with_parent")
        if not (strategy["exit"].get("trend_exit") or {}).get("ema_minutes"):
            raise RuntimeError("The pyramid add-on needs a trend exit: it only adds above the line")
    pullback = strategy["entry"].get("pullback_to_trend")
    if pullback:
        if not isinstance(pullback.get("ema_minutes"), int) or not 60 <= pullback["ema_minutes"] <= 10080:
            raise RuntimeError("The pullback line must be a whole number of minutes between 60 and 10080")
        if not isinstance(pullback.get("dwell_minutes"), int) or not 1 <= pullback["dwell_minutes"] <= 1440:
            raise RuntimeError("The pullback dwell must be a whole number of minutes between 1 and 1440")
    return strategy


def _path(configured: Path, filename: str) -> Path:
    if configured.exists():
        return configured
    # Local development: fall back to the repository copy.
    return Path(__file__).resolve().parents[3] / filename


@lru_cache
def load_strategies() -> dict[str, dict]:
    """All coin strategies keyed by symbol, in display order."""
    settings = get_settings()
    strategies = [validate_strategy(json.loads(_path(getattr(settings, attribute), filename).read_text()))
                  for attribute, filename in COIN_CONFIGS.values()]
    by_symbol = {strategy["market"]["symbol"]: strategy for strategy in strategies}
    if list(by_symbol) != list(SUPPORTED_SYMBOLS):
        raise RuntimeError(f"Expected one strategy each for {', '.join(SUPPORTED_SYMBOLS)}, in that order")
    if len({strategy["strategy_id"] for strategy in strategies}) != len(strategies):
        raise RuntimeError("Strategy ids must be unique")
    return by_symbol


def load_strategy(symbol: str = "SOLUSDT") -> dict:
    try:
        return load_strategies()[symbol.upper()]
    except KeyError as error:
        raise ValueError(f"Unsupported coin: {symbol}") from error
