"""Does knowing what BTC is doing improve ETH?

Every ETH rule we have reads only ETH's own chart. BTC leads this market and ETH is a high-beta follower,
so BTC's state is information ETH's own price has not already used. Two kinds of gate, both daily and both
built from completed UTC days only, effective the next day (the convention the averages already use):

  BTC regime      is BTC itself healthy?   close > its 30d average / not stacked bearish 7d<15d<30d
  ETH/BTC ratio   is ETH outperforming?    the ratio above its own 7d or 30d average

Each gate is tried on the dip entry, on Mode C, and on both. Everything else is ETH exactly as deployed.
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

COIN = "eth"


def daily_closes(raw: pd.DataFrame) -> pd.Series:
    day = raw.open_time.dt.floor("D")
    grouped = raw.groupby(day).agg(close=("close", "last"), n=("close", "size"))
    return grouped[grouped.n == 1440].close


def gates(eth_raw: pd.DataFrame, btc_raw: pd.DataFrame) -> dict[str, np.ndarray]:
    """One boolean per ETH minute per gate, from the previous day's completed data."""
    eth, btc = daily_closes(eth_raw), daily_closes(btc_raw)
    common = eth.index.intersection(btc.index)
    eth, btc = eth.loc[common], btc.loc[common]
    ratio = eth / btc

    frame = pd.DataFrame({
        "btc_above_30d": btc > btc.rolling(30).mean(),
        "btc_not_bearish": ~((btc.rolling(7).mean() < btc.rolling(15).mean())
                             & (btc.rolling(15).mean() < btc.rolling(30).mean())),
        "ratio_above_30d": ratio > ratio.rolling(30).mean(),
        "ratio_above_7d": ratio > ratio.rolling(7).mean(),
    })
    frame = frame[frame.index.isin(common[29:])]                  # only once every average exists
    frame.index = frame.index + pd.Timedelta(days=1)              # effective the next UTC day
    day = eth_raw.open_time.dt.floor("D")
    return {name: day.map(frame[name]).fillna(False).to_numpy(bool) for name in frame.columns}


def build(raw, bullish, ema, mode_c, gate=None, scope=()):
    """ETH as deployed, with `gate` required at entry for the sources named in `scope`."""
    rule = live.load_rule(COIN)
    trades = []
    for entry in live.live_entries(raw, rule):
        entry = int(entry)
        if "dip" in scope and gate is not None and not gate[entry]:
            continue
        line = ema if bullish[entry] else None
        out, price, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], tm.DIP_STOP, line)
        trades.append((entry, out, price, "dip"))
    for entry in mode_c:
        entry = int(entry)
        if "breakout" in scope and gate is not None and not gate[entry]:
            continue
        line = ema if bullish[entry] else None
        out, price, _ = opt.trade(entry, tm.MODE_C["arm"], tm.MODE_C["giveback"], tm.MODE_C["stop"], line)
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
    btc = replay.load_raw("BTCUSDT", include_holdout=True)
    btc = btc[btc.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=tm.EMA_HOURS * 60, adjust=False).mean().to_numpy()
    entries = mode_c_entries(raw)
    all_gates = gates(raw, btc)
    pd.set_option("display.width", 280)

    window = (grid.TIMES >= research.WINDOWS["full"][0]) & (grid.TIMES < research.WINDOWS["full"][1])
    print("=== how often each gate is open, across the full window")
    for name, value in all_gates.items():
        print(f"  {name:<18} {100 * value[window].mean():5.1f}% of minutes")

    base = tm.evaluate("no BTC gate (deployed today)", build(raw, bullish, ema, entries))
    for scope, title in ((("dip", "breakout"), "both entries"), (("dip",), "the dip entry only"),
                         (("breakout",), "Mode C only")):
        print(f"\n=== gate applied to {title}")
        rows = [base]
        for name, value in all_gates.items():
            rows.append(tm.evaluate(name, build(raw, bullish, ema, entries, gate=value, scope=scope)))
        print(pd.DataFrame(rows).set_index("strategy").to_string())


if __name__ == "__main__":
    main()
