"""Exact replay of the SOL, ETH (both live in the app) and BTC candidates on identical rules and windows."""

from __future__ import annotations

import copy
import json
from decimal import Decimal

import numpy as np
import pandas as pd

import run_eth_full_research as eth
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

RESULT_DIR = grid.ROOT / "results" / "coin_comparison_v1"
UTC = "UTC"
T = lambda value: pd.Timestamp(value, tz=UTC)  # noqa: E731
WINDOWS = {"full": (T("2024-10-01"), T("2026-08-01")), "earlier": (T("2024-10-01"), T("2025-09-01")),
           "later": (T("2025-09-01"), T("2026-08-01")), "unseen": (T("2026-08-01"), T("2026-09-10"))}
COSTS = {"normal 10/2": (10.0, 2.0), "BNB 7.5/2": (7.5, 2.0), "stress 15/5": (15.0, 5.0)}
CANDIDATES = {
    "SOL": {"symbol": "SOLUSDT", "signal_minutes": 3, "average_days": 12, "zone_pct": 0.5, "stop_pct": 2.0,
            "activation_pct": 1.251, "giveback_pct": 12.0, "trend": "none", "skip_06_12": True},
    "ETH": {"symbol": "ETHUSDT", "signal_minutes": 5, "average_days": 7, "zone_pct": 0.5, "stop_pct": 3.5,
            "activation_pct": 1.315, "giveback_pct": 30.0, "trend": "none", "skip_06_12": True},
    "BTC": {"symbol": "BTCUSDT", "signal_minutes": 5, "average_days": 5, "zone_pct": 0.2, "stop_pct": 3.0,
            "activation_pct": 1.257, "giveback_pct": 14.0, "trend": "above_30d", "skip_06_12": True},
}


def run(spec: dict) -> tuple[list[dict], pd.DataFrame]:
    symbol = spec["symbol"]
    raw = replay.load_raw(symbol, include_holdout=True)
    raw = raw[raw.open_time < T("2026-09-10")].reset_index(drop=True)
    grid.CLOSE = raw.close.to_numpy(float)
    times = pd.DatetimeIndex(raw.open_time)
    daily_decimal = replay.daily_averages(raw)
    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals) for d, vals in daily_decimal.items()}
    base = copy.deepcopy(json.loads(replay.STRATEGY_FILES[symbol].read_text()))
    base["market"]["signal_timeframe"] = f"{spec['signal_minutes']}m"
    base["averages"]["signal_average_days"] = spec["average_days"]
    base["entry"].update({"touch_zone_pct": spec["zone_pct"], "approach": "from_below"})
    base["entry"]["market_filter"]["type"] = "avoid_strong_bearish"
    base["exit"].update({"protective_stop_pct_from_entry_fill": spec["stop_pct"], "maximum_hold_minutes": 10**9})
    base["exit"]["trailing_stop"].update({"activation_pct_from_entry_fill": spec["activation_pct"],
                                          "giveback_of_open_profit_pct": spec["giveback_pct"]})
    base["portfolio"].update({"maximum_open_positions": 3, "initial_paper_equity_usd": 300.0})
    candles = replay.signal_candles(raw, spec["signal_minutes"], daily_decimal, signal_days=spec["average_days"])
    signals, _ = replay.generate_signals(base, candles)
    frame = pd.DataFrame({"entry_index": [times.searchsorted(pd.Timestamp(s["entry_time"])) for s in signals]})
    feats = eth.features(frame, spec["signal_minutes"], daily, times)
    keep = feats[spec["trend"]] & ~(feats["morning"] & spec["skip_06_12"])
    chosen = [s for s, k in zip(signals, keep) if k]
    allocate = lambda marked, cash: Decimal("100") if cash >= Decimal("100") else Decimal("0")  # noqa: E731
    rows, ledger = [], None
    for cost, (fee, slip) in COSTS.items():
        strategy = copy.deepcopy(base)
        strategy["execution_model"].update({"fee_bps_per_side": fee, "slippage_bps_per_side": slip})
        for window, (start, end) in WINDOWS.items():
            result = replay.replay_execution(strategy, raw, chosen, start, end, allocate=allocate)
            rows.append({"cost": cost, "window": window, **replay.summarize(result, initial=300.0)})
            if cost == "normal 10/2" and window == "full":
                ledger = result.trades
    return rows, ledger


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    tables, monthly = [], {}
    for name, spec in CANDIDATES.items():
        rows, ledger = run(spec)
        tables.append(pd.DataFrame(rows).assign(coin=name))
        monthly[name] = ledger.groupby(pd.to_datetime(ledger.exit_time).dt.strftime("%Y-%m")).net_pnl_usd.sum()
        print(f"done {name}", flush=True)
    table = pd.concat(tables)
    table.to_csv(RESULT_DIR / "comparison.csv", index=False)
    months = pd.DataFrame(monthly).fillna(0.0)
    months["all"] = months[list(CANDIDATES)].sum(axis=1)
    months.to_csv(RESULT_DIR / "monthly_pnl.csv")
    pd.set_option("display.width", 250)
    cols = ["trades", "win_rate_pct", "net_profit_usd", "return_pct", "max_drawdown_pct", "profit_factor",
            "average_winner_pct", "average_loser_pct", "fees_usd", "slippage_usd", "trades_per_month",
            "average_hold_hours", "lowest_equity_usd"]
    for cost in COSTS:
        print(f"\n== {cost}")
        print(table[table.cost == cost].set_index(["window", "coin"])[cols].sort_index().round(2).to_string())
    print("\nMONTHLY P&L (normal costs, by exit month)")
    print(months.round(2).to_string())
    print("\ncorrelations\n", months[list(CANDIDATES)].corr().round(2).to_string())
    for coin in CANDIDATES:
        print(coin, "losing months", int((months[coin] < 0).sum()), "of", len(months),
              "| best month", round(float(months[coin].max()), 2), "| share of profit in best month",
              round(float(months[coin].max() / months[coin].sum() * 100), 1), "%")
    for combo in (["SOL", "ETH"], ["SOL", "ETH", "BTC"]):
        total = months[combo].sum(axis=1).cumsum()
        print("+".join(combo), "worst cumulative dip", round(float((total - total.cummax()).min()), 2),
              "| losing months", int((months[combo].sum(axis=1) < 0).sum()))


if __name__ == "__main__":
    main()
