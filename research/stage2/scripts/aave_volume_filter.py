"""Does volume improve AAVE - taking a trade only when the market is busy (or only when it is quiet)?

Asked from scratch for AAVE, as it was for ETH, SOL, TRX and BTC (all rejected). The measure is always a RATIO:
how busy the hour before the buy was against AAVE's own normal hour.

  volume  base volume, AAVE traded, in the 60 minutes before the buy / its average hour over the prior 7 days
  quote   the same in USDT traded
  trades  the same in number of individual trades
  taker   the taker-buy share of that hour's volume (an absolute, 0-1)
  band    Mode C only: the breakout bar's volume / the average bar of the quiet band it broke out of

Every combination: 5 measures x both directions x every sensible threshold x what it gates (Mode C only, the dip
only, or both) x 3-6 shared lots, and as a SEPARATE sleeve of 1-2 lots doubling the signals the filter likes.
Judged against both controls at the same money - more shared lots and 3 bigger lots.
"""

from __future__ import annotations

import zipfile

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_adaptive_average as ad
import eth_regime as rg
import aave_settings_recheck as a
import sol_wide_stop as w
import trx_volume_filter as tvf
from sol_wide_stop import TRAINS, simulate

SYMBOL = "AAVEUSDT"
CORE, SLEEVE = {"dip", "breakout"}, {"wide dip", "wide breakout"}
RATIO_FLOORS = [0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
TAKER_FLOORS = [0.45, 0.48, 0.50, 0.52, 0.55, 0.60]


def load_raw_volume() -> pd.DataFrame:
    frame = pd.read_parquet(replay.RAW_DIR / SYMBOL / f"{SYMBOL}_1m.parquet", columns=tvf.COLUMNS)
    parts = []
    for path in sorted(replay.HOLDOUT_DIR.glob(f"{SYMBOL}-1m-*.zip")):
        with zipfile.ZipFile(path) as archive:
            with archive.open(archive.namelist()[0]) as handle:
                part = pd.read_csv(handle, header=None, usecols=[0, 1, 2, 3, 4, 5, 7, 8, 9])
        if not str(part.iloc[0, 0]).isdigit():
            part = part.iloc[1:]
        parts.append(part)
    extra = pd.concat(parts)
    extra.columns = tvf.COLUMNS
    stamps = extra.open_time.astype("int64")
    extra["open_time"] = pd.to_datetime(np.where(stamps > 10**14, stamps, stamps * 1000), unit="us", utc=True)
    for column in tvf.COLUMNS[1:]:
        extra[column] = extra[column].astype(float)
    frame = pd.concat([frame, extra]).drop_duplicates("open_time").sort_values("open_time")
    return frame.reset_index(drop=True)


def setup():
    raw = load_raw_volume()
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    return raw, live.regime_flags(raw)


def core_with_band(raw, frames, rule):
    """AAVE as deployed, with each Mode C lot carrying the band ratio of the break that bought it."""
    frame = frames[rule["minutes"]]
    trades = []
    for entry in ad.entries_for(raw, rule, frame, ad.average_by_bar(raw, frame, 10 * 1440)):
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"], None)
        trades.append({"entry": entry, "exit": exit_at, "price": price, "source": "dip", "why": why,
                       "band": np.nan})
    minutes = a.MODE_C["chart"]
    bucket = np.arange(len(raw)) // minutes
    g = pd.DataFrame({"bucket": bucket, "high": raw.high.to_numpy(float), "low": raw.low.to_numpy(float),
                      "close": raw.close.to_numpy(float), "volume": raw.volume.to_numpy(float),
                      "index": np.arange(len(raw))}).groupby("bucket").agg(
        high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"),
        index=("index", "last"), count=("index", "size"))
    g = g[g["count"] == minutes]
    high, low, close = g.high.to_numpy(), g.low.to_numpy(), g.close.to_numpy()
    last_minute, volume = g["index"].to_numpy(), g.volume.to_numpy()
    top = pd.Series(high).rolling(a.MODE_C["bars"]).max().to_numpy()
    bottom = pd.Series(low).rolling(a.MODE_C["bars"]).min().to_numpy()
    zone_top, zone_bottom = np.r_[np.nan, top[:-1]], np.r_[np.nan, bottom[:-1]]
    quiet = (zone_top / zone_bottom - 1) <= a.MODE_C["zone"] / 100
    broke = quiet & (close > zone_top)
    first = broke & ~np.r_[False, broke[:-1]]
    where = np.flatnonzero(first)
    check = last_minute[where] + a.MODE_C["wait"]
    keep = check < len(raw) - 1
    where, check = where[keep], check[keep]
    held = grid.CLOSE[check] > zone_top[where]
    where, entries = where[held], (check[held] + 1).astype(np.int64)
    band_avg = pd.Series(volume).rolling(a.MODE_C["bars"]).mean().to_numpy()
    ratios = volume[where] / np.r_[np.nan, band_avg[:-1]][where]
    hours = grid.TIMES[entries].hour
    allowed = ~((hours >= rule["blocked"][0]) & (hours < rule["blocked"][1])) if rule["blocked"] else np.ones(len(entries), bool)
    for entry, ratio, ok in zip(entries, ratios, allowed):
        if not ok:
            continue
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, a.MODE_C["arm"], a.MODE_C["giveback"], a.MODE_C["stop"], None)
        trades.append({"entry": entry, "exit": exit_at, "price": price, "source": "breakout", "why": why,
                       "band": ratio})
    return sorted(trades, key=lambda t: t["entry"])


def main() -> None:
    raw, bullish = setup()
    rule = live.load_rule(a.COIN)
    daily = replay.daily_averages(raw)
    frames = {}
    for minutes in (1, 3, 5, 15):
        frame = grid.signal_frame(raw, daily, minutes)
        for period in (7, 15, 30):
            frame[period] = np.array([np.nan if v is None else float(v) for v in frame[period]])
        frames[minutes] = frame
    trades = core_with_band(raw, frames, rule)
    ratios = tvf.minute_ratios(raw)
    pd.set_option("display.width", 265)

    dips = [t for t in trades if t["source"] == "dip"]
    breaks = [t for t in trades if t["source"] == "breakout"]
    print(f"AAVE candidates: {len(dips)} dips, {len(breaks)} Mode C breaks")
    print("\n=== how busy AAVE is when it buys (ratio to its own normal hour; taker is a 0-1 share)")
    described = {name: pd.Series([ratios[name][t["entry"]] for t in trades]) for name in ratios}
    described["band (Mode C)"] = pd.Series([t["band"] for t in breaks])
    print(pd.DataFrame(described).describe(percentiles=[.1, .25, .5, .75, .9]).round(3).to_string())

    print("\n=== does a busier hour pay better? (3 shared lots, by the hour-before volume ratio)")
    led = simulate(trades, [(3, CORE)], *research.WINDOWS["full"])["ledger"]
    led = led.assign(ratio=[ratios["volume"][e] for e in led.entry])
    buckets = pd.cut(led.ratio, [0, 0.75, 1.0, 1.5, 2.0, np.inf],
                     labels=["<0.75", "0.75-1.0", "1.0-1.5", "1.5-2.0", ">2.0"])
    print(pd.DataFrame([{"volume ratio": name, "trades": len(part),
                         "win%": round(100 * (part.pnl > 0).mean(), 1),
                         "total_pnl": round(part.pnl.sum(), 2), "avg_pnl": round(part.pnl.mean(), 3)}
                        for name, part in led.groupby(buckets, observed=True)]).set_index("volume ratio").to_string())

    base = tvf.score("AAVE as deployed, 3 x $100", trades, [(3, CORE)])
    controls = {"base": base}
    for n in (4, 5, 6):
        controls[f"{n} shared"] = tvf.score(f"{n} x $100 shared (control)", trades, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger {n}"] = tvf.score(f"3 x ${n * 100 / 3:.0f} (control)", trades, [(3, CORE)])
        w.LOT = 100.0
    print("\n=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    sets = {key: tvf.keep_if(trades, ratios, *key) for key in tvf.combinations()}
    print(f"\n=== 1. SHARED: {len(sets)} filters on AAVE's 3 deployed lots (best 8 by walk-forward)")
    rows = [tvf.score(f"{m} {d} {l:g}, {wh}", kept, [(3, CORE)]) for (m, d, l, wh), kept in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(8).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  beating no filter: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame)} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame)} on the full window, "
          f"{int((frame.unseen > base['unseen']).sum())}/{len(frame)} on the unseen holdout")

    print("\n=== 2. SEPARATE: the 3 core lots carry on, a sleeve doubles the signals the filter likes")
    sleeves = {key: sorted(trades + tvf.keep_if(trades, ratios, *key, tag="wide "), key=lambda t: t["entry"])
               for key in sets}
    for size in (1, 2):
        more, bigger = controls[f"{3 + size} shared"], controls[f"3 bigger {3 + size}"]
        rows2 = [tvf.score(f"{m} {d} {l:g}, {wh}", book, [(3, CORE), (size, SLEEVE)])
                 for (m, d, l, wh), book in sleeves.items()]
        part = pd.DataFrame(rows2).sort_values("walk_forward", ascending=False)
        print(f"\n  --- sleeve of {size} (${(3 + size) * 100}) against {3 + size} shared lots "
              f"(+${more['walk_forward']:.2f}) and 3 bigger lots (+${bigger['walk_forward']:.2f})")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating more lots: {int((part.walk_forward > more['walk_forward']).sum())}/{len(part)}; "
              f"beating bigger lots: {int((part.walk_forward > bigger['walk_forward']).sum())}/{len(part)}")

    print("\n=== 3. the honest test: the filter is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for label, use, pots, control_pots, control_lot in (
            ("shared, 3 lots", sets, [(3, CORE)], [(3, CORE)], 100.0),
            ("sleeve of 1 vs bigger lots", sleeves, [(3, CORE), (1, SLEEVE)], [(3, CORE)], 400 / 3),
            ("sleeve of 2 vs bigger lots", sleeves, [(3, CORE), (2, SLEEVE)], [(3, CORE)], 500 / 3)):
        w.LOT = control_lot
        control_w = {x: simulate(trades, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        w.LOT = 100.0
        scores = {k: {x: simulate(v, pots, *research.WINDOWS[x])["profit"] for x in windows} for k, v in use.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(use, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        print(f"\n  --- {label}")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    best fixed filter in hindsight {best[0]} {best[1]} {best[2]:g}, {best[3]}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")


if __name__ == "__main__":
    main()
