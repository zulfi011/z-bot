"""Does an ATR-scaled stop and trail beat ETH's flat percentages?

ETH risks a flat -4.5% on every dip lot and arms its trail at a flat +1.315%, no matter how violent the
market is that week. ATR (Average True Range) measures how far ETH actually travels in a normal day, so
the same -4.5% is a long way down in a calm week and ordinary noise in a wild one.

True Range of a day = the largest of:  high - low,  |high - previous close|,  |low - previous close|
ATR(14) = the average of the last 14 days' true ranges.  Expressed here as a PERCENTAGE of price, so
2024 and 2026 are comparable.

No lookahead: a day's ATR is built from completed UTC days only and becomes effective the next UTC day,
the same convention the daily averages already use.

Everything else is ETH as deployed: eth_7d_trend16h_breakout_v3, $300 as 3 x $100 lots, BNB fees.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import three_modes as tm

COIN, PERIOD = "eth", 14


def atr_percent(raw: pd.DataFrame, period: int = PERIOD) -> np.ndarray:
    """ATR as a % of price, per 1-minute row, from completed days only and effective the next day."""
    day = raw.open_time.dt.floor("D")
    daily = raw.groupby(day).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"),
                                 n=("close", "size"))
    daily = daily[daily.n == 1440]
    previous = daily.close.shift(1)
    true_range = pd.concat([daily.high - daily.low, (daily.high - previous).abs(),
                            (daily.low - previous).abs()], axis=1).max(axis=1)
    atr = true_range.rolling(period).mean() / daily.close * 100
    effective = pd.Series(atr.to_numpy(), index=daily.index + pd.Timedelta(days=1))
    return day.map(effective).to_numpy(float)


def build(raw, bullish, ema, mode_c_entries, atr, stop_k=None, arm_m=None, scale_sources=("dip", "breakout")):
    """Every candidate trade. stop_k / arm_m None means keep the deployed flat percentage."""
    rule = live.load_rule(COIN)
    trades = []

    def levels(entry, source, flat_stop, flat_arm):
        value = atr[entry]
        if not np.isfinite(value) or source not in scale_sources:
            return flat_stop, flat_arm
        return (flat_stop if stop_k is None else stop_k * value,
                flat_arm if arm_m is None else arm_m * value)

    for entry in live.live_entries(raw, rule):
        entry = int(entry)
        stop, arm = levels(entry, "dip", tm.DIP_STOP, rule["activation_pct"])
        line = ema if bullish[entry] else None
        out, price, _ = opt.trade(entry, arm, rule["giveback_pct"], stop, line)
        trades.append((entry, out, price, "dip"))
    for entry in mode_c_entries:
        entry = int(entry)
        stop, arm = levels(entry, "breakout", tm.MODE_C["stop"], tm.MODE_C["arm"])
        line = ema if bullish[entry] else None
        out, price, _ = opt.trade(entry, arm, tm.MODE_C["giveback"], stop, line)
        trades.append((entry, out, price, "breakout"))
    return sorted(trades, key=lambda row: row[0])


def mode_c_entries(raw):
    mc = tm.MODE_C
    high, low, open_, close, last_minute = v4.bars_for(raw, mc["chart"])
    entries = v4.entries_for(high, low, close, last_minute, mc["bars"], mc["zone"], mc["confirm"],
                             grid.CLOSE, len(raw))
    blocked = live.load_rule(COIN)["blocked"]
    hours = grid.TIMES[entries].hour
    return entries[~((hours >= blocked[0]) & (hours < blocked[1]))]


def main() -> None:
    raw = replay.load_raw("ETHUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=tm.EMA_HOURS * 60, adjust=False).mean().to_numpy()
    atr = atr_percent(raw)
    entries = mode_c_entries(raw)
    pd.set_option("display.width", 280)

    window = (grid.TIMES >= research.WINDOWS["full"][0]) & (grid.TIMES < research.WINDOWS["full"][1])
    series = pd.Series(atr[window]).dropna()
    print(f"=== ETH daily ATR({PERIOD}) as a % of price, over the full window")
    print(series.describe(percentiles=[.1, .25, .5, .75, .9]).round(2).to_string())
    print(f"\nThe deployed flat stop of -{tm.DIP_STOP}% equals {tm.DIP_STOP / series.median():.2f}x the median ATR,"
          f" but {tm.DIP_STOP / series.quantile(.9):.2f}x in the calmest... {tm.DIP_STOP / series.quantile(.1):.2f}x"
          f" in the wildest 10% of days.")

    base = tm.evaluate("flat -4.5% stop, +1.315% arm (deployed)", build(raw, bullish, ema, entries, atr))

    print("\n=== 1. ATR-scaled STOP (trail arm left flat)")
    rows = [base]
    for k in (0.75, 1.0, 1.25, 1.5, 1.75, 2.0):
        rows.append(tm.evaluate(f"stop = {k} x ATR", build(raw, bullish, ema, entries, atr, stop_k=k)))
    print(pd.DataFrame(rows).set_index("strategy").to_string())

    print("\n=== 2. ATR-scaled TRAIL ARM (stop left flat)")
    rows = [base]
    for m in (0.2, 0.3, 0.4, 0.5):
        rows.append(tm.evaluate(f"arm = {m} x ATR", build(raw, bullish, ema, entries, atr, arm_m=m)))
    print(pd.DataFrame(rows).set_index("strategy").to_string())

    print("\n=== 3. both scaled, around whatever looked best")
    rows = [base]
    for k in (1.25, 1.5):
        for m in (0.3, 0.4):
            rows.append(tm.evaluate(f"stop {k} x ATR, arm {m} x ATR",
                                    build(raw, bullish, ema, entries, atr, stop_k=k, arm_m=m)))
    print(pd.DataFrame(rows).set_index("strategy").to_string())

    print("\n=== 4. dip lots only (Mode C keeps its deployed -3.5% / +1.283%)")
    rows = [base]
    for k in (1.25, 1.5, 1.75):
        rows.append(tm.evaluate(f"dip stop = {k} x ATR",
                                build(raw, bullish, ema, entries, atr, stop_k=k, scale_sources=("dip",))))
    print(pd.DataFrame(rows).set_index("strategy").to_string())


if __name__ == "__main__":
    main()
