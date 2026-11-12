"""All five coins as deployed today, measured the same way, so they can be ranked and money split.

Every earlier number was produced by a different script at a different time, on slightly different end dates and
(before the window leaks were fixed) a different engine. This runs each coin's DEPLOYED strategy through the one
corrected engine, over the same windows, with the same money, so the comparison is honest:

  SOL   dip at the 12-day average + Mode C, Mode A on the 8-hour line for lots opened in an uptrend
  ETH   dip at the 7-day average + Mode C + the pullback entry, Mode A on the 16-hour line
  TRX   dip at the 12-day average (30-day filter, +-0.1%) + Mode C, giveback trail only
  BTC   dip at the 5-day average only, giveback trail only
  AAVE  dip at the 10-day average + Mode C, giveback trail only, dip arm +1.75% as deployed 2026-09-25

3 x $100 each, BNB fees, the live buying rule, hourly mark-to-market drawdown, and the six walk-forward windows
plus the unseen Aug-Sep 2026 holdout. The pyramid add-ons ship switched off, so they are not included.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_adaptive_average as ad
import eth_pullback as pb
import eth_regime as rg
import sol_wide_stop as w
import three_modes as tm
import trx_pullback as tp
import trx_volume_filter as vf

CORE = {"dip", "breakout", "pullback"}
LOTS = [(3, CORE)]


def score(coin, trades, lots=LOTS):
    row = vf.score(coin, trades, lots)
    led = w.simulate(trades, lots, *research.WINDOWS["full"])["ledger"]
    holds = (led.exit - led.entry).median() / 60 if len(led) else 0
    return {**row, "per month": round(len(led) / 23, 1), "median hold h": round(holds, 1)}


def frame_for(raw, minutes):
    daily = replay.daily_averages(raw)
    frame = grid.signal_frame(raw, daily, minutes)
    for period in (7, 15, 30):
        frame[period] = np.array([np.nan if v is None else float(v) for v in frame[period]])
    return frame


def load(symbol):
    raw = replay.load_raw(symbol, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    return raw, live.regime_flags(raw)


def lots_for(entries, arm, giveback, stop, source, line=None, bullish=None):
    out = []
    for entry in entries:
        entry = int(entry)
        use = line if (line is not None and (bullish is None or bullish[entry])) else None
        exit_at, price, why = w.resolve(entry, arm, giveback, stop, use)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": source, "why": why})
    return out


def mode_c(raw, rule, chart, bars, zone, wait, arm, giveback, stop, line=None, bullish=None):
    high, low, open_, close, last_minute = v4.bars_for(raw, chart)
    entries = v4.entries_for(high, low, close, last_minute, bars, zone, wait, grid.CLOSE, len(raw))
    if rule["blocked"] and len(entries):
        hours = grid.TIMES[entries].hour
        entries = entries[~((hours >= rule["blocked"][0]) & (hours < rule["blocked"][1]))]
    return lots_for(entries, arm, giveback, stop, "breakout", line, bullish)


def sol():
    raw, bullish = load("SOLUSDT")
    rule = live.load_rule("sol")
    ema = pd.Series(grid.CLOSE).ewm(span=8 * 60, adjust=False).mean().to_numpy()
    trades = lots_for(live.live_entries(raw, rule), rule["activation_pct"], rule["giveback_pct"],
                      rule["stop_pct"], "dip", ema, bullish)
    trades += mode_c(raw, rule, 60, 24, 2.0, 0, 1.283, 22.0, 4.0, ema, bullish)
    return sorted(trades, key=lambda t: t["entry"])


def eth():
    raw, bullish = load("ETHUSDT")
    rule = live.load_rule("eth")
    ema = pd.Series(grid.CLOSE).ewm(span=16 * 60, adjust=False).mean().to_numpy()
    trades = lots_for(live.live_entries(raw, rule), rule["activation_pct"], rule["giveback_pct"],
                      tm.DIP_STOP, "dip", ema, bullish)
    trades += mode_c(raw, rule, 120, 12, 2.5, 30, 1.283, 22.0, 3.5, ema, bullish)
    pull = pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES, blocked=rule["blocked"])
    trades += lots_for(pull, rule["activation_pct"], rule["giveback_pct"], tm.DIP_STOP, "pullback", ema, bullish)
    return sorted(trades, key=lambda t: t["entry"])


def trx():
    raw, bullish = load("TRXUSDT")
    rule = live.load_rule("trx")
    trades = lots_for(live.live_entries(raw, rule), rule["activation_pct"], rule["giveback_pct"],
                      rule["stop_pct"], "dip")
    trades += mode_c(raw, rule, 60, 40, 2.0, 3, 1.283, 22.0, 3.0)
    return sorted(trades, key=lambda t: t["entry"])


def btc():
    raw, bullish = load("BTCUSDT")
    rule = live.load_rule("btc")
    return lots_for(live.live_entries(raw, rule), rule["activation_pct"], rule["giveback_pct"],
                    rule["stop_pct"], "dip")


def aave():
    raw, bullish = load("AAVEUSDT")
    rule = live.load_rule("aave")
    trades = lots_for(live.live_entries(raw, rule), rule["activation_pct"], rule["giveback_pct"],
                      rule["stop_pct"], "dip")
    trades += mode_c(raw, rule, 30, 24, 2.0, 60, 1.283, 22.0, 3.5)
    return sorted(trades, key=lambda t: t["entry"])


def market():
    """The price arrays the engine is currently pointed at - each coin has its own, so they must be swapped back."""
    return grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE, grid.TIMES


def point_at(saved):
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE, grid.TIMES = saved


def main() -> None:
    pd.set_option("display.width", 250)
    rows, books, markets = [], {}, {}
    for name, builder in (("TRX", trx), ("AAVE", aave), ("ETH", eth), ("SOL", sol), ("BTC", btc)):
        books[name] = builder()
        markets[name] = market()
        rows.append(score(name, books[name]))
        print(f"  {name}: {len(books[name])} candidate trades")
    table = pd.DataFrame(rows).set_index("setup").sort_values("walk_forward", ascending=False)
    print("\n=== every coin as deployed, 3 x $100, same engine and windows")
    print(table.to_string())

    print("\n=== what each coin earns per $100 of walk-forward profit, and per unit of drawdown")
    ranked = table.assign(per_100=(table.walk_forward / 3).round(2),
                          per_drawdown=(table.walk_forward / table["mtm_dd%"].abs()).round(1))
    print(ranked[["walk_forward", "windows", "per_100", "per_drawdown", "unseen", "mtm_dd%", "win%"]].to_string())

    print("\n=== and at more money, one coin at a time (bigger lots on the same 3 slots)")
    money = []
    for name in table.index:
        point_at(markets[name])
        for lot, label in ((100.0, "3 x $100"), (166.67, "3 x $167"), (200.0, "3 x $200")):
            w.LOT = lot
            money.append({**score(f"{name} {label}", books[name]), "coin": name})
        w.LOT = 100.0
    print(pd.DataFrame(money).set_index("setup")[["money", "trades", "profit", "walk_forward", "windows",
                                                  "unseen", "mtm_dd%"]].to_string())


if __name__ == "__main__":
    main()
