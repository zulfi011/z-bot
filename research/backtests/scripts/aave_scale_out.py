"""Does scaling out help AAVE - selling part of a lot at a target and letting the rest run?

AAVE sells a lot in one piece: the stop or the trailing giveback (it has no trend exit). Scaling out splits that:
take a fixed slice off at a fixed gain, and leave the rest to the deployed rules, optionally with its stop pulled
up to break even.

Every combination:
  slice   25 / 33 / 50 / 67 / 75% of the lot sold at the target
  target  +0.5 / 0.75 / 1 / 1.5 / 2 / 3 / 5% above the fill (AAVE's trail arms at +1.276%, so the lower targets
          sell before the trail has started)
  after   the remainder keeps its stop, or moves it to break even once the slice is sold
  rest    the remainder exits on its own way in's deployed numbers, or on the other way in's
  scope   the dip only, Mode C only, or both
  lots    SHARED - the deployed 3 lots scale out
          SEPARATE - a sleeve of 1-2 lots of its own takes the same signals and scales out

The slice is sold at the target price itself (a limit fill, never better) and the slot is only free once the
remainder has gone. Judged against both controls at the same money - more shared lots and 3 bigger lots.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_regime as rg
import aave_atr_stop as aatr
import aave_settings_recheck as a
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE, SLEEVE = {"dip", "breakout"}, {"wide dip", "wide breakout"}
SLICES = [0.25, 1 / 3, 0.5, 2 / 3, 0.75]
TARGETS = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0]
AFTER = ["keep stop", "break even"]
RESTS = ["deployed", "the other exit"]
SCOPES = ["dip", "mode c", "both"]


def base_rows(entries, rule, source, rest):
    own = ((rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"]) if source == "dip"
           else (a.MODE_C["arm"], a.MODE_C["giveback"], a.MODE_C["stop"]))
    other = ((a.MODE_C["arm"], a.MODE_C["giveback"], a.MODE_C["stop"]) if source == "dip"
             else (rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"]))
    arm, giveback, stop = own if rest == "deployed" else other
    return {entry: w.resolve(entry, arm, giveback, stop, None) for entry in entries}


def scaled(entries, source, base, target, slice_pct, after, tag=""):
    out = []
    for entry in entries:
        exit_at, price, why = base[entry]
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        level = fill * (1 + target / 100)
        hit = research.first_hit(entry, level, True)
        if hit < 0 or hit >= exit_at:
            out.append({"entry": entry, "exit": exit_at, "price": price, "source": f"{tag}{source}", "why": why})
            continue
        rest_exit, rest_price, rest_why = exit_at, price, why
        if after == "break even":
            back = np.flatnonzero(grid.LOW[hit + 1:exit_at + 1] <= fill)
            if len(back):
                rest_exit = hit + 1 + int(back[0])
                rest_price, rest_why = min(fill, float(grid.OPEN[rest_exit])), 4
        out.append({"entry": entry, "exit": rest_exit, "source": f"{tag}{source}", "why": rest_why,
                    "price": slice_pct * level + (1 - slice_pct) * rest_price})
    return out


def build(key, dips, breaks, bases, tag=""):
    slice_pct, target, after, rest, scope = key
    trades = []
    for entries, source in ((dips, "dip"), (breaks, "breakout")):
        takes = scope == "both" or (scope == "dip") == (source == "dip")
        base = bases[(rest if takes else "deployed", source)]
        if takes:
            trades += scaled(entries, source, base, target, slice_pct, after, tag)
        else:
            trades += [{"entry": e, "exit": v[0], "price": v[1], "why": v[2], "source": f"{tag}{source}"}
                       for e, v in base.items()]
    return sorted(trades, key=lambda t: t["entry"])


def name_of(key):
    slice_pct, target, after, rest, scope = key
    return f"{slice_pct * 100:.0f}% at +{target:g}%, {after}, rest {rest}, {scope}"


def main() -> None:
    raw, bullish = a.setup()
    rule = live.load_rule(a.COIN)
    daily = replay.daily_averages(raw)
    frames = {}
    for minutes in (1, 3, 5, 15):
        frame = grid.signal_frame(raw, daily, minutes)
        for period in (7, 15, 30):
            frame[period] = np.array([np.nan if v is None else float(v) for v in frame[period]])
        frames[minutes] = frame
    dips, breaks = aatr.signals(raw, frames, rule)
    bases = {(rest, source): base_rows(entries, rule, source, rest)
             for rest in RESTS for source, entries in (("dip", dips), ("breakout", breaks))}
    core = sorted([{"entry": e, "exit": v[0], "price": v[1], "why": v[2], "source": source}
                   for source in ("dip", "breakout") for e, v in bases[("deployed", source)].items()],
                  key=lambda t: t["entry"])
    pd.set_option("display.width", 270)

    base = vf.score("AAVE as deployed, 3 x $100", core, [(3, CORE)])
    controls = {"base": base}
    for n in (4, 5):
        controls[f"{n} shared"] = vf.score(f"{n} x $100 shared (control)", core, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger {n}"] = vf.score(f"3 x ${n * 100 / 3:.0f} (control)", core, [(3, CORE)])
        w.LOT = 100.0
    print("=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    keys = [(s, t, af, r, sc) for s in SLICES for t in TARGETS for af in AFTER for r in RESTS for sc in SCOPES]
    sets = {key: build(key, dips, breaks, bases) for key in keys}
    print(f"\n{len(sets)} scale-out rules")

    print("\n=== 1. SHARED: the deployed lots scale out (best 8 by walk-forward)")
    rows = [vf.score(name_of(k), v, [(3, CORE)]) for k, v in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(8).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  beating no scaling: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame)} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame)} on the full window")

    print("\n=== 2. the shape: full-window profit by slice and target (rest deployed, keep stop, both)")
    print(pd.DataFrame({f"+{t:g}%": {f"{s * 100:.0f}%":
                                     vf.score("x", sets[(s, t, "keep stop", "deployed", "both")], [(3, CORE)])["profit"]
                                     for s in SLICES} for t in TARGETS}).round(2).to_string())

    print("\n=== 3. SEPARATE: the core carries on, a scale-out sleeve takes the same signals")
    sleeves = {k: sorted(core + build(k, dips, breaks, bases, tag="wide "), key=lambda t: t["entry"]) for k in sets}
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
