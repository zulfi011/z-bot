"""Does pyramiding help BTC - adding lots to a lot that is already winning?

BTC has one way in (the 5-day dip) and no trend line of its own, so - as on TRX - the guard that keeps the
add-on out of fading moves has to be chosen here rather than inherited.

Every combination:
  step     +0.25 / 0.5 / 0.75 / 1 / 1.5 / 2% above the parent's fill (BTC's own trail arms at +1.257%, so the
           steps tested straddle it)
  adds     1, 2 or 3 adds per parent, in order
  guard    nothing, price above an 8-hour EMA, or above a 24-hour EMA
  exit     "with parent"  sold the minute its parent is, at the same price (SOL's setting)
           "dip"          BTC's deployed numbers from its own fill (stop -3%, arm +1.257%, giveback 14%)
           "wide"         the same trail with a -5% stop
           "line 8h"      held against the 8-hour line once its trail arms (Mode A)
  lots     SHARED with BTC's 3 deployed lots, or 1-3 lots of its own

An add only exists while its parent is open and is never itself a parent. Judged against both controls at the
same money - more shared lots and 3 bigger lots - with the corrected window engine, hourly mark-to-market
drawdown and walk-forward selection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import eth_regime as rg
import btc_pullback as bp
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE, PYRA = {"dip"}, {"pyramid"}
STEPS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
LEVELS = [1, 2, 3]
GUARDS = ["none", "above 8h", "above 24h"]
EXITS = ["with parent", "dip", "wide", "line 8h"]
SIZES = [1, 2, 3]


def adds_for(parents, rule, lines, step, levels, guard, exit_style):
    line = lines.get(guard)
    exit_line = lines["above 8h"] if exit_style == "line 8h" else None
    stop = 5.0 if exit_style == "wide" else rule["stop_pct"]
    out = []
    for parent in parents:
        fill = grid.OPEN[parent["entry"]] * (1 + grid.SLIP)
        start, stop_at = parent["entry"] + 1, parent["exit"]
        for level in range(1, levels + 1):
            if start >= stop_at:
                break
            close = grid.CLOSE[start:stop_at]
            reached = close >= fill * (1 + level * step / 100)
            if line is not None:
                reached = reached & (close > line[start:stop_at])
            hit = np.flatnonzero(reached)
            if not len(hit):
                break
            entry = start + int(hit[0]) + 1
            if entry >= stop_at:
                break
            if exit_style == "with parent":
                exit_at, price, why = parent["exit"], parent["price"], 8
            else:
                exit_at, price, why = w.resolve(entry, rule["activation_pct"], rule["giveback_pct"], stop, exit_line)
            out.append({"entry": entry, "exit": exit_at, "price": price, "source": "pyramid", "why": why})
            start = entry
    return out


def name_of(key):
    step, levels, guard, exit_style = key
    return f"+{step:g}% x{levels}, guard {guard}, exit {exit_style}"


def main() -> None:
    raw, bullish = bp.setup()
    rule = live.load_rule(bp.COIN)
    core = bp.dip_trades(raw, rule)
    lines = {f"above {h}h": pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy() for h in (8, 24)}
    lines["line 8h"] = lines["above 8h"]
    pd.set_option("display.width", 265)

    base = vf.score("BTC as deployed, 3 x $100", core, [(3, CORE)])
    controls = {"base": base}
    for n in (4, 5, 6):
        controls[f"{n} shared"] = vf.score(f"{n} x $100 shared (control)", core, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger {n}"] = vf.score(f"3 x ${n * 100 / 3:.0f} (control)", core, [(3, CORE)])
        w.LOT = 100.0
    print("=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    keys = [(s, l, g, e) for s in STEPS for l in LEVELS for g in GUARDS for e in EXITS]
    sets = {key: adds_for(core, rule, lines, *key) for key in keys}
    sets = {k: v for k, v in sets.items() if v}
    counts = pd.Series({k: len(v) for k, v in sets.items()})
    print(f"\nBTC: {len(core)} parent lots; {len(sets)} pyramid rules; adds offered: median {counts.median():.0f}, "
          f"range {counts.min()}-{counts.max()}")

    print("\n=== 1. SHARED: the adds compete for BTC's 3 deployed lots (best 8 by walk-forward)")
    rows = [base] + [vf.score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE | PYRA)])
                     for k, v in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(8).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  beating no pyramid: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame) - 1} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame) - 1} on the full window, "
          f"{int((frame.unseen > base['unseen']).sum())}/{len(frame) - 1} on the unseen holdout")

    print("\n=== 2. the shape: walk-forward by step and adds (guard none, exit with parent, shared)")
    print(pd.DataFrame({f"x{l}": {f"+{s:g}%":
                                  vf.score("x", sorted(core + sets[(s, l, "none", "with parent")],
                                                       key=lambda t: t["entry"]), [(3, CORE | PYRA)])["walk_forward"]
                                  for s in STEPS} for l in LEVELS}).round(2).to_string())

    print("\n=== 3. SEPARATE: the core carries on, the adds hold lots of their own")
    for size in SIZES:
        more, bigger = controls[f"{3 + size} shared"], controls[f"3 bigger {3 + size}"]
        rows3 = [vf.score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE), (size, PYRA)])
                 for k, v in sets.items()]
        part = pd.DataFrame(rows3).sort_values("walk_forward", ascending=False)
        print(f"\n  --- own {size} (${(3 + size) * 100}) against {3 + size} shared lots "
              f"(+${more['walk_forward']:.2f}) and 3 bigger lots (+${bigger['walk_forward']:.2f})")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating more lots: {int((part.walk_forward > more['walk_forward']).sum())}/{len(part)}; "
              f"beating bigger lots: {int((part.walk_forward > bigger['walk_forward']).sum())}/{len(part)}")

    print("\n=== 4. the honest test: the pyramid rule is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    books = {k: sorted(core + v, key=lambda t: t["entry"]) for k, v in sets.items()}
    for label, pots, control_pots, control_lot in (
            ("shared, 3 lots", [(3, CORE | PYRA)], [(3, CORE)], 100.0),
            ("own 1 vs bigger lots", [(3, CORE), (1, PYRA)], [(3, CORE)], 400 / 3),
            ("own 2 vs more lots", [(3, CORE), (2, PYRA)], [(5, CORE)], 100.0),
            ("own 2 vs bigger lots", [(3, CORE), (2, PYRA)], [(3, CORE)], 500 / 3)):
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
        print(f"    best fixed rule in hindsight {name_of(best)}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")


if __name__ == "__main__":
    main()
