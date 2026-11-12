"""Does scaling out help SOL - selling part of a lot at a target and letting the rest run?

SOL sells a lot in one piece: the protective stop, the trailing giveback, or Mode A on the 8-hour line. Scaling
out splits that decision - take a fixed slice of the position off the table at a fixed gain, and leave the
remainder to the deployed rules (optionally with its stop pulled up to break even, so the rest is "free").

Every combination:
  slice     25% / 33% / 50% / 67% / 75% of the lot sold at the target
  target    +0.5 / 0.75 / 1 / 1.5 / 2 / 3 / 5% above the fill
  after     the remainder keeps its original stop, or moves it to break even once the slice is sold
  rest      the remainder exits "deployed" (Mode A in a clean uptrend, else the giveback), always Mode A,
            or always Mode B
  scope     the dip only, Mode C only, or both
  lots      SHARED - the deployed 3 lots scale out
            SEPARATE - the 3 core lots carry on untouched and a sleeve of 1-2 lots of their own takes the same
            signals and scales out, so the two styles run side by side

The slice is sold at the target price itself (a limit order that is filled, never better), the remainder keeps
the same trail and line it always had, and the slot is only free once the remainder has gone. Corrected window
engine: every lot is marked, and anything still open at a window's end is closed at that window's last price.
Selection is walk-forward - chosen on the six months before each window, never with hindsight.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import run_eth_full_research as research
import eth_regime as rg
import sol_pullback as sp
import sol_wide_stop as w
from sol_wide_stop import CORE, SLEEVE, TRAINS, simulate

SLICES = [0.25, 1 / 3, 0.5, 2 / 3, 0.75]
TARGETS = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0]
AFTER = ["keep stop", "break even"]
RESTS = ["deployed", "mode a", "mode b"]
SCOPES = ["dip", "mode c", "both"]
SIZES = [1, 2]


def base_exits(entries, source, rule, bullish, ema, rest):
    """Where each lot would leave with no scaling out at all, under one remainder rule."""
    arm, giveback, stop = ((rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"])
                           if source == "dip" else
                           (sp.MODE_C["arm"], sp.MODE_C["giveback"], sp.MODE_C["stop"]))
    out = {}
    for entry in entries:
        line = None if rest == "mode b" else (w.ema_line if False else None)
        out[entry] = None                                    # filled in by caller-supplied line below
    return arm, giveback, stop, out


def build_base(entries, source, rule, bullish, ema, rest):
    arm, giveback, stop = ((rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"])
                           if source == "dip" else
                           (sp.MODE_C["arm"], sp.MODE_C["giveback"], sp.MODE_C["stop"]))
    rows = {}
    for entry in entries:
        line = ema if (rest == "mode a" or (rest == "deployed" and bullish[entry])) else None
        rows[entry] = w.resolve(entry, arm, giveback, stop, line)
    return rows, stop


def scaled(entries, source, base, stop_pct, target, slice_pct, after):
    """The same lots, with `slice_pct` sold at +target% when it is reached before the lot would have left.

    Encoded as one row with an effective exit price, so the slot is only free when the remainder goes:
        effective price = slice x target price + (1 - slice) x remainder price
    """
    out = []
    for entry in entries:
        exit_at, price, why = base[entry]
        fill = w.grid.OPEN[entry] * (1 + w.grid.SLIP)
        level = fill * (1 + target / 100)
        hit = research.first_hit(entry, level, True)
        if hit < 0 or hit >= exit_at:
            out.append({"entry": entry, "exit": exit_at, "price": price, "source": source, "why": why})
            continue
        rest_exit, rest_price, rest_why = exit_at, price, why
        if after == "break even":
            low = w.grid.LOW[hit + 1:exit_at + 1]
            back = np.flatnonzero(low <= fill)
            if len(back):
                rest_exit = hit + 1 + int(back[0])
                rest_price = min(fill, float(w.grid.OPEN[rest_exit]))
                rest_why = 4                                  # stopped at break even after the slice
        out.append({"entry": entry, "exit": rest_exit, "source": source, "why": rest_why,
                    "price": slice_pct * level + (1 - slice_pct) * rest_price})
    return out


def name_of(key):
    slice_pct, target, after, rest, scope = key
    return f"{slice_pct * 100:.0f}% at +{target:g}%, {after}, rest {rest}, {scope}"


def main() -> None:
    raw, bullish, ema = sp.setup()
    rule, dips, breaks = w.signals(raw)
    pd.set_option("display.width", 265)
    bases = {rest: {source: build_base(entries, source, rule, bullish, ema, rest)
                    for source, entries in (("dip", dips), ("breakout", breaks))} for rest in RESTS}
    core = sorted([t for rest_source in bases["deployed"].values()
                   for entry, (exit_at, price, why) in [(e, v) for e, v in rest_source[0].items()]
                   for t in [{"entry": entry, "exit": exit_at, "price": price, "why": why,
                              "source": "dip" if rest_source is bases["deployed"]["dip"] else "breakout"}]],
                  key=lambda t: t["entry"])
    base = w.score("SOL as deployed, 3 x $100", core, [(3, CORE)])
    print(f"SOL: {len(dips)} dip signals, {len(breaks)} Mode C signals")
    print("\n=== 0. the control")
    print(pd.DataFrame([base, w.score("flat core 4", core, [(4, CORE)]),
                        w.score("flat core 5", core, [(5, CORE)])]).set_index("setup").to_string())

    keys = [(s, t, a, r, sc) for s in SLICES for t in TARGETS for a in AFTER for r in RESTS for sc in SCOPES]
    sets = {}
    for key in keys:
        slice_pct, target, after, rest, scope = key
        trades = []
        for source, entries in (("dip", dips), ("breakout", breaks)):
            takes = scope == "both" or (scope == "dip") == (source == "dip")
            rows, stop_pct = bases[rest if takes else "deployed"][source]
            if takes:
                trades += scaled(entries, source, rows, stop_pct, target, slice_pct, after)
            else:
                trades += [{"entry": e, "exit": v[0], "price": v[1], "why": v[2], "source": source}
                           for e, v in rows.items()]
        sets[key] = sorted(trades, key=lambda t: t["entry"])
    print(f"\n{len(sets)} scale-out rules")

    print("\n=== 1. SHARED: the deployed lots scale out (best 10 by walk-forward)")
    rows = [w.score(name_of(key), trades, [(3, CORE)]) for key, trades in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  rules beating no scaling: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame)} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame)} on the full window, "
          f"{int((frame['mtm_dd%'] > base['mtm_dd%']).sum())}/{len(frame)} on drawdown")

    print("\n=== 2. is there a plateau? full-window profit by slice and target (rest deployed, keep stop, both)")
    table = pd.DataFrame({f"+{t:g}%": {f"{s * 100:.0f}%":
                                       w.score("x", sets[(s, t, "keep stop", "deployed", "both")], [(3, CORE)])["profit"]
                                       for s in SLICES} for t in TARGETS})
    print(table.round(2).to_string())

    print("\n=== 3. SEPARATE: the core carries on, a scale-out sleeve of its own takes the same signals")
    sleeves = {key: sorted(core + [{**t, "source": f"wide {t['source']}"} for t in trades],
                           key=lambda t: t["entry"]) for key, trades in sets.items()}
    rows = [w.score(name_of(key) + " - sleeve 2", trades, [(3, CORE), (2, SLEEVE)])
            for key, trades in sleeves.items()]
    frame2 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    control5 = w.score("flat core 5 (control)", core, [(5, CORE)])
    print(frame2.set_index("setup").head(8).to_string())
    print(f"  beating flat core 5 (+${control5['walk_forward']:.2f}): "
          f"{int((frame2.walk_forward > control5['walk_forward']).sum())}/{len(frame2)} on walk-forward")

    print("\n=== 4. the honest test: the rule is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for label, use, pots, control_pots in (("shared, 3 lots", sets, [(3, CORE)], [(3, CORE)]),
                                           ("sleeve of 1", sleeves, [(3, CORE), (1, SLEEVE)], [(4, CORE)]),
                                           ("sleeve of 2", sleeves, [(3, CORE), (2, SLEEVE)], [(5, CORE)])):
        control_w = {x: simulate(core, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        scores = {key: {x: simulate(trades, pots, *research.WINDOWS[x])["profit"] for x in windows}
                  for key, trades in use.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(use, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        print(f"\n  --- {label}")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    best fixed rule in hindsight {name_of(best)}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")
        print(f"    it picked: {'; '.join(name_of(p) for p in picks)}")


if __name__ == "__main__":
    main()
