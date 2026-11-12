"""Should BTC get a Mode C break-out entry, the way SOL, ETH, AAVE and TRX have one?

BTC has only one way in - the dip to its 5-day average - so it sits idle whenever BTC never comes back down.
Mode C is the obvious gap: a quiet band of N bars no wider than X%, and the first bar that closes above the top
buys. Every other coin gained from it, but it has to be tuned from scratch here (BTC is far calmer than the
alts, so the bands tested are much tighter).

Every combination:
  chart    30 / 60 / 120-minute bars
  bars     12 / 24 / 40 of them make the band
  width    no wider than 0.5 / 1 / 1.5 / 2 / 2.5%
  wait     re-check 0 / 3 / 10 minutes after the break, then buy the next minute
  hours    obey BTC's 06:00-12:00 blocked window, or ignore it (on other coins Mode C keeps the blocked hours
           but never the downtrend filter, which is also skipped here)
  exit     "dip"     BTC's deployed numbers (stop -3%, arm +1.257%, giveback 14%)
           "mode c"  the shape the other coins use for breaks (stop -3%, arm +1.283%, giveback 22%)
           "wide"    the deployed trail with a -5% stop
  lots     SHARED with BTC's 3 deployed lots, or 1-3 lots of its own

Judged against both controls at the same money - more shared lots and 3 bigger lots - with the corrected window
engine, hourly mark-to-market drawdown and walk-forward selection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import eth_regime as rg
import btc_pullback as bp
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE, BREAK = {"dip"}, {"breakout"}
CHARTS = [30, 60, 120]
BARS = [12, 24, 40]
ZONES = [0.5, 1.0, 1.5, 2.0, 2.5]
WAITS = [0, 3, 10]
BLOCKED = [True, False]
EXITS = ["dip", "mode c", "wide"]
SIZES = [1, 2, 3]


def breaks_for(raw, rule, chart, bars, zone, wait, blocked, exit_style):
    high, low, open_, close, last_minute = v4.bars_for(raw, chart)
    entries = v4.entries_for(high, low, close, last_minute, bars, zone, wait, grid.CLOSE, len(raw))
    if blocked and rule["blocked"] and len(entries):
        hours = grid.TIMES[entries].hour
        entries = entries[~((hours >= rule["blocked"][0]) & (hours < rule["blocked"][1]))]
    arm, giveback, stop = {
        "dip": (rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"]),
        "mode c": (1.283, 22.0, 3.0),
        "wide": (rule["activation_pct"], rule["giveback_pct"], 5.0),
    }[exit_style]
    out = []
    for entry in entries:
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, arm, giveback, stop, None)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": "breakout", "why": why})
    return out


def name_of(key):
    chart, bars, zone, wait, blocked, exit_style = key
    return (f"{bars} x {chart}m bars <= {zone:g}%, wait {wait}m"
            f"{'' if blocked else ', all hours'}, exit {exit_style}")


def main() -> None:
    raw, bullish = bp.setup()
    rule = live.load_rule(bp.COIN)
    core = bp.dip_trades(raw, rule)
    pd.set_option("display.width", 275)

    base = vf.score("BTC as deployed, 3 x $100", core, [(3, CORE)])
    controls = {"base": base}
    for n in (4, 5, 6):
        controls[f"{n} shared"] = vf.score(f"{n} x $100 shared (control)", core, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger {n}"] = vf.score(f"3 x ${n * 100 / 3:.0f} (control)", core, [(3, CORE)])
        w.LOT = 100.0
    print("=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    keys = [(c, b, z, wt, bl, e) for c in CHARTS for b in BARS for z in ZONES for wt in WAITS
            for bl in BLOCKED for e in EXITS]
    sets = {key: breaks_for(raw, rule, *key) for key in keys}
    sets = {k: v for k, v in sets.items() if v}
    counts = pd.Series({k: len(v) for k, v in sets.items()})
    print(f"\nBTC: {len(core)} dip signals; {len(sets)} Mode C rules that fire; breaks per rule: median "
          f"{counts.median():.0f}, range {counts.min()}-{counts.max()}")

    print("\n=== 1. Mode C ALONE, on its own money (3 x $100) - best 8 by walk-forward")
    rows = [vf.score(name_of(k), v, [(3, BREAK)]) for k, v in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(8).to_string())
    print(f"  Mode C rules that made money alone: {int((frame.profit > 0).sum())}/{len(frame)}; "
          f"positive walk-forward: {int((frame.walk_forward > 0).sum())}/{len(frame)}")

    print("\n=== 2. SHARED: Mode C joins the dip on BTC's 3 deployed lots (best 10)")
    rows = [base] + [vf.score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE | BREAK)])
                     for k, v in sets.items()]
    frame2 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame2.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame2.set_index("setup").tail(3).to_string())
    print(f"  beating the dip alone: {int((frame2.walk_forward > base['walk_forward']).sum())}/{len(frame2) - 1} "
          f"on walk-forward, {int((frame2.profit > base['profit']).sum())}/{len(frame2) - 1} on the full window, "
          f"{int((frame2.unseen > base['unseen']).sum())}/{len(frame2) - 1} on the unseen holdout")

    print("\n=== 3. SEPARATE: the dip carries on, Mode C holds lots of its own")
    for size in SIZES:
        more, bigger = controls[f"{3 + size} shared"], controls[f"3 bigger {3 + size}"]
        rows3 = [vf.score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE), (size, BREAK)])
                 for k, v in sets.items()]
        part = pd.DataFrame(rows3).sort_values("walk_forward", ascending=False)
        print(f"\n  --- own {size} (${(3 + size) * 100}) against {3 + size} shared lots "
              f"(+${more['walk_forward']:.2f}) and 3 bigger lots (+${bigger['walk_forward']:.2f})")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating more lots: {int((part.walk_forward > more['walk_forward']).sum())}/{len(part)}; "
              f"beating bigger lots: {int((part.walk_forward > bigger['walk_forward']).sum())}/{len(part)}")

    print("\n=== 4. the honest test: the Mode C setting is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    books = {k: sorted(core + v, key=lambda t: t["entry"]) for k, v in sets.items()}
    for label, pots, control_pots, control_lot in (
            ("shared, 3 lots", [(3, CORE | BREAK)], [(3, CORE)], 100.0),
            ("own 1 vs bigger lots", [(3, CORE), (1, BREAK)], [(3, CORE)], 400 / 3),
            ("own 2 vs more lots", [(3, CORE), (2, BREAK)], [(5, CORE)], 100.0),
            ("own 2 vs bigger lots", [(3, CORE), (2, BREAK)], [(3, CORE)], 500 / 3)):
        w.LOT = control_lot
        control_w = {x: simulate(core, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        w.LOT = 100.0
        scores = {k: {x: simulate(v, pots, *research.WINDOWS[x])["profit"] for x in windows} for k, v in books.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(books, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        print(f"\n  --- {label}")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    best fixed setting in hindsight {name_of(best)}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")


if __name__ == "__main__":
    main()
