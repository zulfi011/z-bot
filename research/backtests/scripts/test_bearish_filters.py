"""Does a coin lose money at the start of downtrends, and would a faster downtrend filter help?

Usage: python test_bearish_filters.py [ETH|SOL|BTC|AAVE|LINK]   (default ETH)

Exact Stage 3 replay of the coin's live strategy (its candidate in compare_all_coins.CANDIDATES, $300 as $100 lots) with the app's own strong-bearish filter (7d < 15d < 30d) always on. Each variant adds
ONE extra rule that skips a buy. Every rule uses only what was known before the buy: daily averages of completed UTC
days (effective the next day) and the price at the confirming candle's close.
"""

from __future__ import annotations

import copy
import json
import sys
from decimal import Decimal

import numpy as np
import pandas as pd

import compare_all_coins as cmp
import run_eth_full_research as eth
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

COIN = (sys.argv[1] if len(sys.argv) > 1 else "ETH").upper()
RESULT_DIR = grid.ROOT / "results" / f"{COIN.lower()}_bearish_filters_v1"
SPEC = cmp.CANDIDATES[COIN]
END = cmp.T("2026-09-10")


def load(symbol: str):
    raw = replay.load_raw(symbol, include_holdout=True)
    raw = raw[raw.open_time < END].reset_index(drop=True)
    daily_decimal = replay.daily_averages(raw)
    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals) for d, vals in daily_decimal.items()}
    return raw, daily_decimal, daily


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    raw, daily_decimal, daily = load(SPEC["symbol"])
    btc_raw, _, btc_daily = load("BTCUSDT")
    grid.CLOSE = raw.close.to_numpy(float)
    times = pd.DatetimeIndex(raw.open_time)
    btc_close = pd.Series(btc_raw.close.to_numpy(float), index=pd.DatetimeIndex(btc_raw.open_time))

    base = copy.deepcopy(json.loads(replay.STRATEGY_FILES.get(SPEC["symbol"], replay.STRATEGY_FILES["ETHUSDT"]).read_text()))
    base["market"]["signal_timeframe"] = f"{SPEC['signal_minutes']}m"
    base["averages"]["signal_average_days"] = SPEC["average_days"]
    base["entry"].update({"touch_zone_pct": SPEC["zone_pct"], "approach": "from_below"})
    base["entry"]["market_filter"]["type"] = "avoid_strong_bearish"
    base["exit"].update({"protective_stop_pct_from_entry_fill": SPEC["stop_pct"], "maximum_hold_minutes": 10**9})
    base["exit"]["trailing_stop"].update({"activation_pct_from_entry_fill": SPEC["activation_pct"],
                                          "giveback_of_open_profit_pct": SPEC["giveback_pct"]})
    base["portfolio"].update({"maximum_open_positions": 3, "initial_paper_equity_usd": 300.0})
    candles = replay.signal_candles(raw, SPEC["signal_minutes"], daily_decimal, signal_days=SPEC["average_days"])
    signals, _ = replay.generate_signals(base, candles)

    entry = np.array([times.searchsorted(pd.Timestamp(s["entry_time"])) for s in signals])
    feats = eth.features(pd.DataFrame({"entry_index": entry}), SPEC["signal_minutes"], daily, times)
    live = feats[SPEC["trend"]] & ~(feats["morning"] & SPEC["skip_06_12"])   # the live strategy's own rules

    # What was known at the confirming candle: its close, and the averages in effect that day and three days before.
    confirm_index = entry - SPEC["signal_minutes"]
    confirm_time = times[confirm_index]
    day = confirm_time.floor("D")
    nan3 = (np.nan,) * 3
    a7, a15, a30 = (np.array([daily.get(d, nan3)[i] for d in day]) for i in range(3))
    a7_3ago = np.array([daily.get(d - pd.Timedelta(days=3), nan3)[0] for d in day])
    price = grid.CLOSE[entry - 1]
    b7, b15, b30 = (np.array([btc_daily.get(d, nan3)[i] for d in day]) for i in range(3))
    btc_price = btc_close.reindex(confirm_time + pd.Timedelta(minutes=SPEC["signal_minutes"] - 1)).to_numpy()

    early_bearish = a7 < a15                                        # the first sign: 7-day under 15-day
    rules = {
        "Now (only 7d<15d<30d)":            np.ones(len(entry), bool),
        "Skip if price < 7-day avg":        ~(price < a7),
        "Skip if 7-day avg < 15-day avg":   ~early_bearish,
        "Skip if 7-day avg falling (3 days)": ~(a7 < a7_3ago),
        "Skip if price < 30-day avg":       ~(price < a30),
        "Skip if BTC 7-day < 15-day":       ~(b7 < b15),
        "Skip if BTC price < 30-day avg":   ~(btc_price < b30),
    }

    allocate = lambda marked, cash: Decimal("100") if cash >= Decimal("100") else Decimal("0")  # noqa: E731
    rows, ledgers = [], {}
    for name, keep in rules.items():
        chosen = [s for s, k in zip(signals, live & keep) if k]
        for cost, (fee, slip) in cmp.COSTS.items():
            strategy = copy.deepcopy(base)
            strategy["execution_model"].update({"fee_bps_per_side": fee, "slippage_bps_per_side": slip})
            for window, (start, end) in cmp.WINDOWS.items():
                result = replay.replay_execution(strategy, raw, chosen, start, end, allocate=allocate)
                rows.append({"rule": name, "cost": cost, "window": window, **replay.summarize(result, initial=300.0)})
                if cost == "normal 10/2" and window == "full":
                    ledgers[name] = result.trades
        print("done", name, flush=True)
    table = pd.DataFrame(rows)
    table.to_csv(RESULT_DIR / "results.csv", index=False)

    # Where the current strategy's money goes: trades bought while 7d<15d (early downtrend) versus the rest.
    trades = ledgers["Now (only 7d<15d<30d)"].copy()
    trades_entry = pd.DatetimeIndex(pd.to_datetime(trades.entry_time, utc=True))
    trade_day = (trades_entry - pd.Timedelta(minutes=SPEC["signal_minutes"])).floor("D")
    t7 = np.array([daily.get(d, nan3)[0] for d in trade_day]); t15 = np.array([daily.get(d, nan3)[1] for d in trade_day])
    trades["early_downtrend"] = t7 < t15
    split = trades.groupby("early_downtrend").agg(trades=("net_pnl_usd", "size"), net_usd=("net_pnl_usd", "sum"),
                                                  win_rate=("net_pnl_usd", lambda p: (p > 0).mean() * 100))
    split.to_csv(RESULT_DIR / "trades_by_regime.csv")

    normal = table[table.cost == "normal 10/2"].pivot(index="rule", columns="window", values="net_profit_usd")
    stress = table[table.cost == "stress 15/5"].pivot(index="rule", columns="window", values="net_profit_usd")
    full = table[(table.cost == "normal 10/2") & (table.window == "full")].set_index("rule")
    summary = pd.DataFrame({
        "full": normal["full"], "earlier": normal["earlier"], "later": normal["later"], "unseen": normal["unseen"],
        "stress_later": stress["later"], "trades": full["trades"], "win_rate": full["win_rate_pct"],
        "max_dd_pct": full["max_drawdown_pct"], "profit_factor": full["profit_factor"],
    }).loc[list(rules)]
    summary.to_csv(RESULT_DIR / "summary.csv")
    pd.set_option("display.width", 220)
    print(summary.round(2).to_string())
    print(f"\nCurrent {COIN} trades by regime at the buy (True = 7-day avg below 15-day avg)")
    print(split.round(2).to_string())


if __name__ == "__main__":
    main()
