"""Does volume improve ETH's Mode C? One filter, measured honestly.

Mode C buys the first 2-hour bar that closes above a 24-hour quiet band. This script asks whether that
break is worth taking only when it carries unusual participation.

The measure is a RATIO, not an absolute: the breakout bar's volume divided by the average volume of the
12 bars that formed the band. 1.0 means the break happened on a perfectly ordinary amount of trading;
2.0 means twice the band's usual. A ratio is the only fair way to compare 2024 volume with 2026 volume.

Four candidate measures, all known at the breakout bar's close (no lookahead - the buy lands 31 minutes
later):
    volume        base volume, ETH traded
    quote         quote volume, USDT traded
    trades        number of individual trades
    taker         taker-buy share of that bar's volume (who was the aggressor, not how much)

Everything else is ETH exactly as deployed: eth_7d_trend16h_breakout_v3, $300 as 3 x $100 lots, BNB fees.
"""

from __future__ import annotations

import zipfile

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
SYMBOL = "ETHUSDT"
COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "quote_volume",
           "number_of_trades", "taker_buy_base_volume"]


def load_raw_volume() -> pd.DataFrame:
    """Same rows as replay.load_raw, with the volume columns kept."""
    frame = pd.read_parquet(replay.RAW_DIR / SYMBOL / f"{SYMBOL}_1m.parquet", columns=COLUMNS)
    parts = []
    for path in sorted(replay.HOLDOUT_DIR.glob(f"{SYMBOL}-1m-*.zip")):
        with zipfile.ZipFile(path) as archive:
            with archive.open(archive.namelist()[0]) as handle:
                part = pd.read_csv(handle, header=None, usecols=[0, 1, 2, 3, 4, 5, 7, 8, 9])
        if not str(part.iloc[0, 0]).isdigit():
            part = part.iloc[1:]
        parts.append(part)
    extra = pd.concat(parts)
    extra.columns = COLUMNS
    stamps = extra.open_time.astype("int64")
    micros = np.where(stamps > 10**14, stamps, stamps * 1000)          # archives switched units in 2025
    extra["open_time"] = pd.to_datetime(micros, unit="us", utc=True)
    for column in COLUMNS[1:]:
        extra[column] = extra[column].astype(float)
    frame = pd.concat([frame, extra]).drop_duplicates("open_time").sort_values("open_time")
    return frame.reset_index(drop=True)


def bars_with_volume(raw: pd.DataFrame, minutes: int):
    """Whole TF-minute bars: the OHLC v4 uses, plus the four participation measures summed over the bar."""
    bucket = np.arange(len(raw)) // minutes
    frame = pd.DataFrame({"bucket": bucket, "high": raw.high.to_numpy(float), "low": raw.low.to_numpy(float),
                          "open": raw.open.to_numpy(float), "close": raw.close.to_numpy(float),
                          "volume": raw.volume.to_numpy(float), "quote": raw.quote_volume.to_numpy(float),
                          "trades": raw.number_of_trades.to_numpy(float),
                          "taker": raw.taker_buy_base_volume.to_numpy(float), "index": np.arange(len(raw))})
    g = frame.groupby("bucket").agg(high=("high", "max"), low=("low", "min"), open=("open", "first"),
                                    close=("close", "last"), volume=("volume", "sum"), quote=("quote", "sum"),
                                    trades=("trades", "sum"), taker=("taker", "sum"),
                                    index=("index", "last"), count=("index", "size"))
    g = g[g["count"] == minutes]
    measures = {"volume": g.volume.to_numpy(), "quote": g.quote.to_numpy(), "trades": g.trades.to_numpy(),
                "taker": (g.taker / g.volume).to_numpy()}
    return (g.high.to_numpy(), g.low.to_numpy(), g.open.to_numpy(), g.close.to_numpy(),
            g["index"].to_numpy(), measures)


def breakouts_with_ratio(high, low, close, last_minute, bars, zone, confirm, minute_close, minute_count, measures):
    """v4.entries_for, but it also hands back which bar broke out so the ratio can be attached."""
    top = pd.Series(high).rolling(bars).max().to_numpy()
    bottom = pd.Series(low).rolling(bars).min().to_numpy()
    zone_top = np.r_[np.nan, top[:-1]]
    zone_bottom = np.r_[np.nan, bottom[:-1]]
    quiet = (zone_top / zone_bottom - 1) <= zone / 100
    broke = quiet & (close > zone_top)
    first = broke & ~np.r_[False, broke[:-1]]
    where = np.flatnonzero(first)
    check = last_minute[where] + confirm
    valid = check < minute_count - 1
    where, check = where[valid], check[valid]
    held = minute_close[check] > zone_top[where]
    where, entries = where[held], (check[held] + 1).astype(np.int64)

    ratios = {}
    for name, series in measures.items():
        band = pd.Series(series).rolling(bars).mean().to_numpy()
        band_before = np.r_[np.nan, band[:-1]]                          # the band's own bars, not the break
        ratios[name] = (series[where] / band_before[where]) if name != "taker" else series[where]
    return entries, ratios


def build(raw, bullish, ema, mode_c_entries):
    """ETH as deployed - dip + Mode C, Mode A on both - with Mode C's entries supplied."""
    rule = live.load_rule(COIN)
    trades = []
    for entry in live.live_entries(raw, rule):
        entry = int(entry)
        line = ema if bullish[entry] else None
        out, price, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], tm.DIP_STOP, line)
        trades.append((entry, out, price, "dip"))
    for entry in mode_c_entries:
        entry = int(entry)
        line = ema if bullish[entry] else None
        out, price, _ = opt.trade(entry, tm.MODE_C["arm"], tm.MODE_C["giveback"], tm.MODE_C["stop"], line)
        trades.append((entry, out, price, "breakout"))
    return sorted(trades, key=lambda row: row[0])


def main() -> None:
    raw = load_raw_volume()
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=tm.EMA_HOURS * 60, adjust=False).mean().to_numpy()
    pd.set_option("display.width", 280)

    mc = tm.MODE_C
    high, low, open_, close, last_minute, measures = bars_with_volume(raw, mc["chart"])
    entries, ratios = breakouts_with_ratio(high, low, close, last_minute, mc["bars"], mc["zone"],
                                           mc["confirm"], grid.CLOSE, len(raw), measures)
    blocked = live.load_rule(COIN)["blocked"]
    if blocked:
        hours = grid.TIMES[entries].hour
        keep = ~((hours >= blocked[0]) & (hours < blocked[1]))
        entries = entries[keep]
        ratios = {name: value[keep] for name, value in ratios.items()}
    inside = (grid.TIMES[entries] >= research.WINDOWS["full"][0]) & (grid.TIMES[entries] < research.WINDOWS["full"][1])
    print(f"Mode C candidates: {len(entries)} total, {int(inside.sum())} inside the full window")
    print("\n=== what the breakout bar's volume looks like (ratio to the band's average bar)")
    print(pd.DataFrame(ratios).describe(percentiles=[.1, .25, .5, .75, .9]).round(3).to_string())

    print("\n=== does a busier break actually pay better? (Mode C alone, no dip competing for slots)")
    alone = [t for t in build(raw, bullish, ema, entries) if t[3] == "breakout"]
    ledger = tm.account(alone, *research.WINDOWS["full"], 7.5 / 10_000)["ledger"]
    taken = pd.Series(ratios["volume"], index=entries)
    rows = []
    if len(ledger):
        ledger = ledger.assign(ratio=ledger.entry.map(taken))
        buckets = pd.cut(ledger.ratio, [0, 1.0, 1.5, 2.0, 3.0, np.inf],
                         labels=["<1.0", "1.0-1.5", "1.5-2.0", "2.0-3.0", ">3.0"])
        for name, part in ledger.groupby(buckets, observed=True):
            rows.append({"volume ratio": name, "trades": len(part), "wins": int((part.pnl > 0).sum()),
                         "win_rate": round(100 * (part.pnl > 0).mean(), 1),
                         "total_pnl": round(part.pnl.sum(), 2), "avg_pnl": round(part.pnl.mean(), 2)})
    print(pd.DataFrame(rows).set_index("volume ratio").to_string())

    print("\n=== ETH as deployed, with a minimum volume ratio on Mode C ($300, 3 x $100, BNB fees)")
    table = [tm.evaluate("no filter (deployed today)", build(raw, bullish, ema, entries))]
    for floor in (1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5):
        kept = entries[ratios["volume"] >= floor]
        table.append(tm.evaluate(f"volume ratio >= {floor}", build(raw, bullish, ema, kept)))
    print(pd.DataFrame(table).set_index("strategy").to_string())

    print("\n=== the other three measures, at the same thresholds")
    variants = [tm.evaluate("no filter (deployed today)", build(raw, bullish, ema, entries))]
    for name, floors in (("quote", (1.25, 1.5, 2.0)), ("trades", (1.25, 1.5, 2.0)),
                         ("taker", (0.50, 0.55, 0.60))):
        for floor in floors:
            kept = entries[ratios[name] >= floor]
            variants.append(tm.evaluate(f"{name} >= {floor}", build(raw, bullish, ema, kept)))
    print(pd.DataFrame(variants).set_index("strategy").to_string())


if __name__ == "__main__":
    main()
