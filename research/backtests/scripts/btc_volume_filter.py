"""Does volume improve BTC - taking the dip only when the market is busy (or only when it is quiet)?

BTC has one way in, so there is no Mode C band ratio to test here; the measure is how busy the hour before the
buy was, against BTC's own normal hour:

  volume  base volume, BTC traded, in the 60 minutes before the buy / its average hour over the prior 7 days
  quote   the same in USDT traded
  trades  the same in number of individual trades
  taker   the taker-buy share of that hour's volume - who was the aggressor (an absolute, 0-1)

Every combination: 4 measures x both directions (only when busy / only when quiet) x every sensible threshold,
on 3 to 6 shared lots, and as a SEPARATE sleeve of 1-2 lots that buys a second lot on the signals the filter
likes. Judged against both controls at the same money - more shared lots and 3 bigger lots - with the corrected
window engine, hourly mark-to-market drawdown and walk-forward selection.
"""

from __future__ import annotations

import zipfile

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_regime as rg
import btc_pullback as bp
import sol_wide_stop as w
import trx_volume_filter as tvf
from sol_wide_stop import TRAINS, simulate

SYMBOL = "BTCUSDT"
CORE, SLEEVE = {"dip"}, {"wide dip"}
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


def keep_if(trades, ratios, measure, direction, level, tag=""):
    out = []
    for trade in trades:
        value = ratios[measure][trade["entry"]]
        if np.isnan(value):
            continue
        if (value >= level) if direction == "busy" else (value <= level):
            out.append({**trade, "source": f"{tag}{trade['source']}"} if tag else trade)
    return out


def combinations():
    for measure, levels in (("volume", RATIO_FLOORS), ("quote", RATIO_FLOORS), ("trades", RATIO_FLOORS),
                            ("taker", TAKER_FLOORS)):
        for direction in ("busy", "quiet"):
            for level in levels:
                yield measure, direction, level


def main() -> None:
    raw, bullish = setup()
    rule = live.load_rule(bp.COIN)
    core = bp.dip_trades(raw, rule)
    ratios = tvf.minute_ratios(raw)
    pd.set_option("display.width", 260)

    print(f"BTC: {len(core)} dip signals")
    print("\n=== how busy BTC is when it buys (ratio to its own normal hour; taker is a 0-1 share)")
    described = pd.DataFrame({name: pd.Series([ratios[name][t["entry"]] for t in core]) for name in ratios})
    print(described.describe(percentiles=[.1, .25, .5, .75, .9]).round(3).to_string())

    print("\n=== does a busier hour pay better? (3 shared lots, by the hour-before volume ratio)")
    led = simulate(core, [(3, CORE)], *research.WINDOWS["full"])["ledger"]
    led = led.assign(ratio=[ratios["volume"][e] for e in led.entry])
    buckets = pd.cut(led.ratio, [0, 0.75, 1.0, 1.5, 2.0, np.inf],
                     labels=["<0.75", "0.75-1.0", "1.0-1.5", "1.5-2.0", ">2.0"])
    print(pd.DataFrame([{"volume ratio": name, "trades": len(part),
                         "win%": round(100 * (part.pnl > 0).mean(), 1),
                         "total_pnl": round(part.pnl.sum(), 2), "avg_pnl": round(part.pnl.mean(), 3)}
                        for name, part in led.groupby(buckets, observed=True)]).set_index("volume ratio").to_string())

    base = tvf.score("BTC as deployed, 3 x $100", core, [(3, CORE)])
    controls = {"base": base}
    for n in (4, 5, 6):
        controls[f"{n} shared"] = tvf.score(f"{n} x $100 shared (control)", core, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger {n}"] = tvf.score(f"3 x ${n * 100 / 3:.0f} (control)", core, [(3, CORE)])
        w.LOT = 100.0
    print("\n=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    sets = {key: keep_if(core, ratios, *key) for key in combinations()}
    print(f"\n=== 1. SHARED: {len(sets)} filters on BTC's 3 deployed lots (best 8 by walk-forward)")
    rows = [tvf.score(f"{m} {d} {l:g}", kept, [(3, CORE)]) for (m, d, l), kept in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(8).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  beating no filter: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame)} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame)} on the full window, "
          f"{int((frame.unseen > base['unseen']).sum())}/{len(frame)} on the unseen holdout")

    print("\n=== 2. the best four filters at 4, 5 and 6 shared lots, against no filter at the same money")
    best_keys = [k for k, _ in sorted(zip(sets, rows), key=lambda item: -item[1]["walk_forward"])][:4]
    table = []
    for n in (4, 5, 6):
        table.append(controls[f"{n} shared"])
        for key in best_keys:
            table.append(tvf.score(f"{key[0]} {key[1]} {key[2]:g} — {n} lots", sets[key], [(n, CORE)]))
    print(pd.DataFrame(table).set_index("setup").to_string())

    print("\n=== 3. SEPARATE: the 3 core lots carry on, a sleeve doubles the signals the filter likes")
    sleeves = {key: sorted(core + keep_if(core, ratios, *key, tag="wide "), key=lambda t: t["entry"])
               for key in sets}
    for size in (1, 2):
        more, bigger = controls[f"{3 + size} shared"], controls[f"3 bigger {3 + size}"]
        rows3 = [tvf.score(f"{m} {d} {l:g}", book, [(3, CORE), (size, SLEEVE)])
                 for (m, d, l), book in sleeves.items()]
        part = pd.DataFrame(rows3).sort_values("walk_forward", ascending=False)
        print(f"\n  --- sleeve of {size} (${(3 + size) * 100}) against {3 + size} shared lots "
              f"(+${more['walk_forward']:.2f}) and 3 bigger lots (+${bigger['walk_forward']:.2f})")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating more lots: {int((part.walk_forward > more['walk_forward']).sum())}/{len(part)}; "
              f"beating bigger lots: {int((part.walk_forward > bigger['walk_forward']).sum())}/{len(part)}")

    print("\n=== 4. the honest test: the filter is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for label, use, pots, control_pots, control_lot in (
            ("shared, 3 lots", sets, [(3, CORE)], [(3, CORE)], 100.0),
            ("sleeve of 1 vs bigger lots", sleeves, [(3, CORE), (1, SLEEVE)], [(3, CORE)], 400 / 3),
            ("sleeve of 2 vs bigger lots", sleeves, [(3, CORE), (2, SLEEVE)], [(3, CORE)], 500 / 3)):
        w.LOT = control_lot
        control_w = {x: simulate(core, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        w.LOT = 100.0
        scores = {k: {x: simulate(v, pots, *research.WINDOWS[x])["profit"] for x in windows} for k, v in use.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(use, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        print(f"\n  --- {label}")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    best fixed filter in hindsight {best[0]} {best[1]} {best[2]:g}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")


if __name__ == "__main__":
    main()
