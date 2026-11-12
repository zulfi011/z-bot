"""Every live coin: does holding to an EMA beat the giveback trailing stop, and does a trend switch help?

Each coin keeps its OWN live rule exactly as deployed - its signal timeframe, average length, touch zone,
trend filter, blocked hours, stop and trailing settings. The only thing swapped is what happens after the
trailing stop arms:

  base                the deployed giveback (SOL 12%, ETH 30%, TRX 10%, AAVE 20%, BTC 14%)
  EMA {1..10}h        hold until a 1-minute close below that EMA
  EMA {..}h in uptrend  the EMA hold only when 7d > 15d > 30d, otherwise the deployed giveback

$300 as 3 x $100 lots, both fee levels. Usage: live_ema_hold_all.py [sol eth trx aave btc]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import sol_trend_ride as ride
import stage3_replay as replay

LIVE = Path(__file__).resolve().parents[3] / "engine"
HOURS = list(range(1, 11))
WF = ride.WF
EDGE = 1e-12


def load_rule(coin: str) -> dict:
    strategy = json.loads((LIVE / f"{coin}_strategy.json").read_text())
    entry, exit_ = strategy["entry"], strategy["exit"]
    blocked = entry.get("blocked_entry_hours_utc")
    trend = entry.get("trend_filter")
    return {"symbol": strategy["market"]["symbol"],
            "minutes": int(strategy["market"]["signal_timeframe"].rstrip("m")),
            "average_days": strategy["averages"]["signal_average_days"],
            "zone_pct": entry["touch_zone_pct"],
            "blocked": (blocked["start"], blocked["end"]) if blocked else None,
            "above_30d": trend is not None,
            "max_above_30d": (trend or {}).get("maximum_above_average_pct"),
            "stop_pct": exit_["protective_stop_pct_from_entry_fill"],
            "activation_pct": exit_["trailing_stop"]["activation_pct_from_entry_fill"],
            "giveback_pct": exit_["trailing_stop"]["giveback_of_open_profit_pct"]}


def live_entries(raw: pd.DataFrame, rule: dict) -> np.ndarray:
    """The deployed entry rule, including its trend filter and blocked hours."""
    daily = replay.daily_averages(raw)
    average_n = replay.daily_average_n(raw, rule["average_days"])
    frame = grid.signal_frame(raw, daily, rule["minutes"])
    for period in (7, 15, 30):
        frame[period] = np.array([np.nan if value is None else float(value) for value in frame[period]])
    days = frame["open_time"].floor("D")
    average = np.array([float(average_n[day]) if average_n.get(day) is not None else np.nan for day in days])
    zone = rule["zone_pct"] / 100
    high, low, close, open_ = frame["high"], frame["low"], frame["close"], frame["open"]
    a7, a15, a30 = frame[7], frame[15], frame[30]
    with np.errstate(invalid="ignore"):
        lower, upper = average * (1 - zone), average * (1 + zone)
        touched = np.isfinite(average) & (high >= lower * (1 - EDGE)) & (low <= upper * (1 + EDGE))
        prior_below = np.zeros(len(high), bool)
        prior_below[1:] = np.isfinite(average[:-1]) & (high[:-1] < lower[:-1] * (1 - EDGE))
        missing = ~(np.isfinite(a7) & np.isfinite(a15) & np.isfinite(a30))
        bearish = ~missing & (a7 < a15) & (a15 < a30)
    eligible = touched & ~np.r_[False, touched[:-1]] & prior_below & ~(bearish | missing)
    bullish_candle = close > open_
    steps = 30 // rule["minutes"]
    confirmations = []
    for origin in np.flatnonzero(eligible):
        for offset in range(steps + 1):
            index = origin + offset
            if index >= len(high):
                break
            if bullish_candle[index]:
                confirmations.append(index)
                break
            if not touched[index]:
                break
    confirmations = np.asarray(confirmations, dtype=np.int64)
    if rule["above_30d"] and len(confirmations):
        ceiling = a30[confirmations] * (1 + (rule["max_above_30d"] or 1e9) / 100)
        keep = (close[confirmations] > a30[confirmations]) & (close[confirmations] <= ceiling)
        confirmations = confirmations[keep]
    entries = frame["first_raw"] + (confirmations + 1) * rule["minutes"]
    entries = entries[entries < len(raw) - 1]
    if rule["blocked"]:
        hours = pd.DatetimeIndex(raw.open_time).hour.to_numpy()[entries]
        entries = entries[~((hours >= rule["blocked"][0]) & (hours < rule["blocked"][1]))]
    return entries


def regime_flags(raw: pd.DataFrame) -> np.ndarray:
    daily = replay.daily_averages(raw)
    days = raw.open_time.dt.floor("D")
    values = np.array([[np.nan if v is None else float(v) for v in daily.get(day, (None,) * 3)] for day in days])
    a7, a15, a30 = values[:, 0], values[:, 1], values[:, 2]
    with np.errstate(invalid="ignore"):
        return np.isfinite(a7) & np.isfinite(a15) & np.isfinite(a30) & (a7 > a15) & (a15 > a30)


def run_coin(coin: str) -> pd.DataFrame:
    rule = load_rule(coin)
    raw = replay.load_raw(rule["symbol"], include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = ride.SLIP
    ride.STOP_PCT = rule["stop_pct"]
    times = pd.DatetimeIndex(raw.open_time)
    entries = live_entries(raw, rule)
    bullish = regime_flags(raw)
    emas = {h: pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy() for h in HOURS}
    print(f"{coin.upper()}: {len(entries)} live signals, stop -{rule['stop_pct']}%, "
          f"arm +{rule['activation_pct']}%, giveback {rule['giveback_pct']}%, "
          f"{100 * bullish[entries].mean():.0f}% in a clean uptrend", flush=True)

    labels = ["base (deployed)"] + [f"EMA{h}h always" for h in HOURS] + [f"EMA{h}h in uptrend" for h in HOURS]
    cols = len(labels)
    idx = np.full((len(entries), cols), -1, dtype=np.int64)
    price = np.full((len(entries), cols), np.nan)
    code = np.zeros((len(entries), cols), dtype=np.int8)
    for row, entry in enumerate(entries):
        entry = int(entry)
        plain = ride.trade(entry, rule["activation_pct"], rule["giveback_pct"])
        by_hour = {h: ride.trade(entry, rule["activation_pct"], rule["giveback_pct"], ema=emas[h], ema_exit=True)
                   for h in HOURS}
        chosen = [plain] + [by_hour[h] for h in HOURS] + [by_hour[h] if bullish[entry] else plain for h in HOURS]
        for column, (out, exit_price, reason, _) in enumerate(chosen):
            if out < 0:
                continue
            idx[row, column], price[row, column] = out, exit_price
            code[row, column] = 2 if reason == "stop" else 1

    research.TABLE, research.COLS = (idx, price, code), cols
    research.LOT, research.LOTS, research.INITIAL = 100.0, 3, 300.0
    rows = []
    for fee_bps, fee_name in ((10.0, "USDT"), (7.5, "BNB")):
        grid.FEE = fee_bps / 10_000
        stats = {}
        for name, (start, end) in research.WINDOWS.items():
            mask = (times[entries] >= start) & (times[entries] < end)
            stats[name] = research.simulate(entries[mask], np.flatnonzero(mask))
        for column, label in enumerate(labels):
            full = {key: float(value[column]) for key, value in stats["full"].items()}
            wins, losses = full["wins"], full["trades"] - full["wins"]
            rows.append({"coin": coin.upper(), "exit": label, "fees": fee_name, "trades": int(full["trades"]),
                         "win_rate": round(100 * full["wins"] / max(full["trades"], 1)),
                         "avg_win": full["gross_win"] / wins if wins else 0.0,
                         "avg_loss": -full["gross_loss"] / losses if losses else 0.0,
                         "full": full["profit"], "earlier": float(stats["earlier"]["profit"][column]),
                         "later": float(stats["later"]["profit"][column]),
                         "unseen": float(stats["unseen"]["profit"][column]),
                         "walk_forward": sum(float(stats[w]["profit"][column]) for w in WF),
                         "wf_windows": f"{sum(float(stats[w]['profit'][column]) > 0 for w in WF)}/6",
                         "drawdown": full["dd"]})
    return pd.DataFrame(rows)


def main() -> None:
    coins = [c.lower() for c in sys.argv[1:]] or ["sol", "eth", "trx", "aave", "btc"]
    frames = [run_coin(coin) for coin in coins]
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(grid.ROOT / "results" / "live_ema_hold_all.csv", index=False)
    pd.set_option("display.width", 250)
    for coin in coins:
        block = out[(out.coin == coin.upper()) & (out.fees == "BNB")]
        print(f"\n=== {coin.upper()}, 3 x $100 lots, BNB fees")
        print(block.drop(columns=["coin", "fees"]).set_index("exit").round(2).to_string())


if __name__ == "__main__":
    main()
