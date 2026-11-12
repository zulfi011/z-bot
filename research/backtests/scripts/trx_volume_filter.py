"""Does volume improve TRX - taking a trade only when the market is busy (or only when it is quiet)?

Asked from scratch for TRX, as it was for ETH (rejected) and SOL (rejected). The measure is always a RATIO: how
busy the hour before the buy was against TRX's own normal hour, so 2024 and 2026 compare.

  volume  base volume, TRX traded, in the 60 minutes before the buy / its average hour over the prior 7 days
  quote   the same in USDT traded
  trades  the same in number of individual trades
  taker   the taker-buy share of that hour's volume - who was the aggressor (an absolute, 0-1)
  band    Mode C only: the breakout bar's volume / the average bar of the quiet band it broke out of

Every combination: 5 measures x both directions (only when busy / only when quiet) x every sensible threshold x
what it gates (Mode C only, the dip only, or both) x 3-6 shared lots, and a SEPARATE version where the deployed
3 lots carry on untouched and a sleeve of 1-2 lots buys a SECOND lot on the signals the filter likes - so the
filter never removes a trade, it doubles down on one.

Corrected window engine, hourly mark-to-market drawdown, walk-forward selection. TRX has no blocked hours.
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
import eth_regime as rg
import sol_wide_stop as w
import trx_pullback as tp
from sol_wide_stop import TRAINS, simulate

SYMBOL = "TRXUSDT"
COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "quote_volume",
           "number_of_trades", "taker_buy_base_volume"]
CORE, SLEEVE = {"dip", "breakout"}, {"wide dip", "wide breakout"}
HOUR, NORMAL = 60, 7 * 1440
RATIO_FLOORS = [0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
TAKER_FLOORS = [0.45, 0.48, 0.50, 0.52, 0.55, 0.60]


def load_raw_volume() -> pd.DataFrame:
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
    extra["open_time"] = pd.to_datetime(np.where(stamps > 10**14, stamps, stamps * 1000), unit="us", utc=True)
    for column in COLUMNS[1:]:
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


def minute_ratios(raw):
    out = {}
    for name, column in (("volume", "volume"), ("quote", "quote_volume"), ("trades", "number_of_trades")):
        series = pd.Series(raw[column].to_numpy(float))
        recent = series.rolling(HOUR).sum().shift(1)
        normal = series.rolling(NORMAL).mean().shift(1) * HOUR
        out[name] = (recent / normal).to_numpy()
    volume = pd.Series(raw.volume.to_numpy(float)).rolling(HOUR).sum().shift(1)
    taker = pd.Series(raw.taker_buy_base_volume.to_numpy(float)).rolling(HOUR).sum().shift(1)
    out["taker"] = (taker / volume).to_numpy()
    return out


def core_with_band(raw, rule):
    """TRX as deployed, with each Mode C lot carrying the band ratio of the break that bought it."""
    trades = []
    for entry in live.live_entries(raw, rule):
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"], None)
        trades.append({"entry": entry, "exit": exit_at, "price": price, "source": "dip", "why": why,
                       "band": np.nan})
    minutes = tp.MODE_C["chart"]
    bucket = np.arange(len(raw)) // minutes
    frame = pd.DataFrame({"bucket": bucket, "high": raw.high.to_numpy(float), "low": raw.low.to_numpy(float),
                          "close": raw.close.to_numpy(float), "volume": raw.volume.to_numpy(float),
                          "index": np.arange(len(raw))})
    g = frame.groupby("bucket").agg(high=("high", "max"), low=("low", "min"), close=("close", "last"),
                                    volume=("volume", "sum"), index=("index", "last"), count=("index", "size"))
    g = g[g["count"] == minutes]
    high, low, close = g.high.to_numpy(), g.low.to_numpy(), g.close.to_numpy()
    last_minute, volume = g["index"].to_numpy(), g.volume.to_numpy()
    top = pd.Series(high).rolling(tp.MODE_C["bars"]).max().to_numpy()
    bottom = pd.Series(low).rolling(tp.MODE_C["bars"]).min().to_numpy()
    zone_top, zone_bottom = np.r_[np.nan, top[:-1]], np.r_[np.nan, bottom[:-1]]
    quiet = (zone_top / zone_bottom - 1) <= tp.MODE_C["zone"] / 100
    broke = quiet & (close > zone_top)
    first = broke & ~np.r_[False, broke[:-1]]
    where = np.flatnonzero(first)
    check = last_minute[where] + tp.MODE_C["confirm"]
    keep = check < len(raw) - 1
    where, check = where[keep], check[keep]
    held = grid.CLOSE[check] > zone_top[where]
    where, entries = where[held], (check[held] + 1).astype(np.int64)
    band_avg = pd.Series(volume).rolling(tp.MODE_C["bars"]).mean().to_numpy()
    ratios = volume[where] / np.r_[np.nan, band_avg[:-1]][where]
    for entry, ratio in zip(entries, ratios):
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, tp.MODE_C["arm"], tp.MODE_C["giveback"], tp.MODE_C["stop"], None)
        trades.append({"entry": entry, "exit": exit_at, "price": price, "source": "breakout", "why": why,
                       "band": ratio})
    return sorted(trades, key=lambda t: t["entry"])


def keep_if(trades, ratios, measure, direction, level, which, tag=""):
    out = []
    for trade in trades:
        gated = which == "both" or (which == "dip") == (trade["source"] == "dip")
        if not gated:
            if not tag:
                out.append(trade)
            continue
        value = trade["band"] if measure == "band" else ratios[measure][trade["entry"]]
        if np.isnan(value):
            continue
        if (value >= level) if direction == "busy" else (value <= level):
            out.append({**trade, "source": f"{tag}{trade['source']}"} if tag else trade)
    return out


def combinations():
    for measure, levels in (("volume", RATIO_FLOORS), ("quote", RATIO_FLOORS), ("trades", RATIO_FLOORS),
                            ("band", RATIO_FLOORS), ("taker", TAKER_FLOORS)):
        for direction in ("busy", "quiet"):
            for level in levels:
                for which in (("mode c",) if measure == "band" else ("mode c", "dip", "both")):
                    yield measure, direction, level, which


def score(label, trades, pots):
    runs = {x: simulate(trades, pots, *research.WINDOWS[x]) for x in ("full", "unseen", *rg.TESTS)}
    led = runs["full"]["ledger"]
    wf = [runs[x]["profit"] for x in rg.TESTS]
    return {"setup": label, "money": int(runs["full"]["capital"]), "trades": len(led),
            "win%": round(100 * (led.pnl > 0).mean(), 1) if len(led) else 0.0,
            "profit": round(runs["full"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "windows": f"{sum(x > 0 for x in wf)}/6", "unseen": round(runs["unseen"]["profit"], 2),
            "mtm_dd%": round(runs["full"]["mtm_dd%"], 2)}


def main() -> None:
    raw, bullish = setup()
    rule = live.load_rule(tp.COIN)
    trades = core_with_band(raw, rule)
    ratios = minute_ratios(raw)
    pd.set_option("display.width", 265)

    dips = [t for t in trades if t["source"] == "dip"]
    breaks = [t for t in trades if t["source"] == "breakout"]
    print(f"TRX candidates: {len(dips)} dips, {len(breaks)} Mode C breaks")
    print("\n=== how busy TRX is when it buys (ratio to its own normal hour; taker is a 0-1 share)")
    described = {name: pd.Series([ratios[name][t["entry"]] for t in trades]) for name in ratios}
    described["band (Mode C)"] = pd.Series([t["band"] for t in breaks])
    print(pd.DataFrame(described).describe(percentiles=[.1, .25, .5, .75, .9]).round(3).to_string())

    print("\n=== does a busier hour pay better? (every lot, 3 shared lots, by the hour-before volume ratio)")
    led = simulate(trades, [(3, CORE)], *research.WINDOWS["full"])["ledger"]
    led = led.assign(ratio=[ratios["volume"][e] for e in led.entry])
    buckets = pd.cut(led.ratio, [0, 0.75, 1.0, 1.5, 2.0, np.inf], labels=["<0.75", "0.75-1.0", "1.0-1.5", "1.5-2.0", ">2.0"])
    print(pd.DataFrame([{"volume ratio": name, "trades": len(part),
                         "win%": round(100 * (part.pnl > 0).mean(), 1),
                         "total_pnl": round(part.pnl.sum(), 2), "avg_pnl": round(part.pnl.mean(), 3)}
                        for name, part in led.groupby(buckets, observed=True)]).set_index("volume ratio").to_string())

    controls = {n: score(f"shared {n} lots (control)", trades, [(n, CORE)]) for n in (3, 4, 5, 6)}
    print("\n=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    sets = {key: keep_if(trades, ratios, *key) for key in combinations()}
    print(f"\n=== 1. SHARED: {len(sets)} filters on TRX's 3 deployed lots (best 10 by walk-forward)")
    rows = [score(f"{m} {d} {l:g}, {wh}", kept, [(3, CORE)]) for (m, d, l, wh), kept in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    base = controls[3]
    print(f"  beating no filter: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame)} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame)} on the full window")

    print("\n=== 2. the best four filters at 4, 5 and 6 shared lots, against no filter at the same money")
    best_keys = [k for k, _ in sorted(zip(sets, rows), key=lambda item: -item[1]["walk_forward"])][:4]
    table = []
    for n in (4, 5, 6):
        table.append(controls[n])
        for key in best_keys:
            m, d, l, wh = key
            table.append(score(f"{m} {d} {l:g}, {wh} — {n} lots", sets[key], [(n, CORE)]))
    print(pd.DataFrame(table).set_index("setup").to_string())

    print("\n=== 3. SEPARATE: the 3 core lots carry on, a sleeve doubles the signals the filter likes")
    sleeves = {key: sorted(trades + keep_if(trades, ratios, *key, tag="wide "), key=lambda t: t["entry"])
               for key in sets}
    for size in (1, 2):
        control = controls[3 + size]
        rows2 = [score(f"{m} {d} {l:g}, {wh}", book, [(3, CORE), (size, SLEEVE)])
                 for (m, d, l, wh), book in sleeves.items()]
        part = pd.DataFrame(rows2).sort_values("walk_forward", ascending=False)
        print(f"\n  --- sleeve of {size} (${(3 + size) * 100}) against {3 + size} shared lots "
              f"(+${control['walk_forward']:.2f}, {control['windows']}, {control['mtm_dd%']}%)")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating that control: {int((part.walk_forward > control['walk_forward']).sum())}/{len(part)}")

    print("\n=== 4. the honest test: the filter is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for label, use, pots, control_pots in (("shared, 3 lots", sets, [(3, CORE)], [(3, CORE)]),
                                           ("sleeve of 1", sleeves, [(3, CORE), (1, SLEEVE)], [(4, CORE)]),
                                           ("sleeve of 2", sleeves, [(3, CORE), (2, SLEEVE)], [(5, CORE)])):
        control_w = {x: simulate(trades, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
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
