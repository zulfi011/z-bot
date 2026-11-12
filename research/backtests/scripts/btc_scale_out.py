"""Does scaling out help BTC - selling part of a lot at a target and letting the rest run?

BTC sells a lot in one piece: the -3% stop or the trailing giveback (it has no trend exit). Scaling out splits
that: take a fixed slice off at a fixed gain, and leave the rest to the deployed rules, optionally with its stop
pulled up to break even.

Every combination:
  slice   25 / 33 / 50 / 67 / 75% of the lot sold at the target
  target  +0.5 / 0.75 / 1 / 1.5 / 2 / 3 / 5% above the fill (BTC's trail only arms at +1.257%, so the lower
          targets sell before the trail has even started)
  after   the remainder keeps its -3% stop, or moves it to break even once the slice is sold
  rest    the remainder exits on BTC's deployed numbers, or with the -5% stop that its recheck liked
  lots    SHARED - the deployed 3 lots scale out
          SEPARATE - a sleeve of 1-2 lots of its own takes the same signals and scales out

The slice is sold at the target price itself (a limit fill, never better) and the slot is only free once the
remainder has gone. Judged against both controls at the same money - more shared lots and 3 bigger lots - with
the corrected window engine, hourly mark-to-market drawdown and walk-forward selection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import eth_regime as rg
import btc_pullback as bp
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE, SLEEVE = {"dip"}, {"wide dip"}
SLICES = [0.25, 1 / 3, 0.5, 2 / 3, 0.75]
TARGETS = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0]
AFTER = ["keep stop", "break even"]
RESTS = ["deployed", "stop -5%"]


def base_rows(entries, rule, rest):
    stop = rule["stop_pct"] if rest == "deployed" else 5.0
    return {entry: w.resolve(entry, rule["activation_pct"], rule["giveback_pct"], stop, None) for entry in entries}


def build(key, entries, bases, tag=""):
    slice_pct, target, after, rest = key
    base = bases[rest]
    out = []
    for entry in entries:
        exit_at, price, why = base[entry]
        fill = w.grid.OPEN[entry] * (1 + w.grid.SLIP)
        level = fill * (1 + target / 100)
        hit = research.first_hit(entry, level, True)
        if hit < 0 or hit >= exit_at:
            out.append({"entry": entry, "exit": exit_at, "price": price, "source": f"{tag}dip", "why": why})
            continue
        rest_exit, rest_price, rest_why = exit_at, price, why
        if after == "break even":
            back = np.flatnonzero(w.grid.LOW[hit + 1:exit_at + 1] <= fill)
            if len(back):
                rest_exit = hit + 1 + int(back[0])
                rest_price, rest_why = min(fill, float(w.grid.OPEN[rest_exit])), 4
        out.append({"entry": entry, "exit": rest_exit, "source": f"{tag}dip", "why": rest_why,
                    "price": slice_pct * level + (1 - slice_pct) * rest_price})
    return sorted(out, key=lambda t: t["entry"])


def name_of(key):
    slice_pct, target, after, rest = key
    return f"{slice_pct * 100:.0f}% at +{target:g}%, {after}, rest {rest}"


def main() -> None:
    raw, bullish = bp.setup()
    rule = live.load_rule(bp.COIN)
    entries = [t["entry"] for t in bp.dip_trades(raw, rule)]
    bases = {rest: base_rows(entries, rule, rest) for rest in RESTS}
    core = [{"entry": e, "exit": v[0], "price": v[1], "why": v[2], "source": "dip"}
            for e, v in bases["deployed"].items()]
    core.sort(key=lambda t: t["entry"])
    pd.set_option("display.width", 265)

    base = vf.score("BTC as deployed, 3 x $100", core, [(3, CORE)])
    controls = {"base": base}
    for n in (4, 5):
        controls[f"{n} shared"] = vf.score(f"{n} x $100 shared (control)", core, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger {n}"] = vf.score(f"3 x ${n * 100 / 3:.0f} (control)", core, [(3, CORE)])
        w.LOT = 100.0
    print("=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    keys = [(s, t, a, r) for s in SLICES for t in TARGETS for a in AFTER for r in RESTS]
    sets = {key: build(key, entries, bases) for key in keys}
    print(f"\n{len(sets)} scale-out rules")

    print("\n=== 1. SHARED: the deployed lots scale out (best 8 by walk-forward)")
    rows = [vf.score(name_of(k), v, [(3, CORE)]) for k, v in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(8).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  beating no scaling: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame)} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame)} on the full window, "
          f"{int((frame.unseen > base['unseen']).sum())}/{len(frame)} on the unseen holdout")

    print("\n=== 2. the shape: full-window profit by slice and target (rest deployed, keep stop)")
    print(pd.DataFrame({f"+{t:g}%": {f"{s * 100:.0f}%":
                                     vf.score("x", sets[(s, t, "keep stop", "deployed")], [(3, CORE)])["profit"]
                                     for s in SLICES} for t in TARGETS}).round(2).to_string())

    print("\n=== 3. SEPARATE: the core carries on, a scale-out sleeve takes the same signals")
    sleeves = {k: sorted(core + build(k, entries, bases, tag="wide "), key=lambda t: t["entry"]) for k in sets}
    for size in (1, 2):
        more, bigger = controls[f"{3 + size} shared"], controls[f"3 bigger {3 + size}"]
        rows3 = [vf.score(name_of(k), book, [(3, CORE), (size, SLEEVE)]) for k, book in sleeves.items()]
        part = pd.DataFrame(rows3).sort_values("walk_forward", ascending=False)
        print(f"\n  --- sleeve of {size} (${(3 + size) * 100}) against {3 + size} shared lots "
              f"(+${more['walk_forward']:.2f}) and 3 bigger lots (+${bigger['walk_forward']:.2f})")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating more lots: {int((part.walk_forward > more['walk_forward']).sum())}/{len(part)}; "
              f"beating bigger lots: {int((part.walk_forward > bigger['walk_forward']).sum())}/{len(part)}")

    print("\n=== 4. the honest test: the rule is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for label, books, pots, control_pots, control_lot in (
            ("shared, 3 lots", sets, [(3, CORE)], [(3, CORE)], 100.0),
            ("sleeve of 2 vs more lots", sleeves, [(3, CORE), (2, SLEEVE)], [(5, CORE)], 100.0),
            ("sleeve of 2 vs bigger lots", sleeves, [(3, CORE), (2, SLEEVE)], [(3, CORE)], 500 / 3)):
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
