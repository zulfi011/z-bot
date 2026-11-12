"""Does pyramiding help TRX - adding lots to a lot that is already winning?

TRX is the awkward coin for this. ETH and SOL only add while price is above their trend line, which keeps the
add-on out of fading moves - but TRX has no trend exit at all (every EMA length made its core worse), so the
guard has to be chosen here rather than inherited.

Every combination:
  step     the gain that triggers an add: +0.25 / 0.5 / 0.75 / 1 / 1.5 / 2% above the parent's fill
           (TRX's own trail only arms at +1.245%, so the steps tested start well below it)
  adds     1, 2 or 3 adds per parent, in order
  parents  every open lot, only dip lots, or only Mode C lots
  guard    what must also be true to add: nothing, price above an 8-hour EMA, or above a 24-hour EMA
  exit     "with parent"  the add is sold the minute its parent is, at the same price (SOL's setting)
           "dip"          the add takes TRX's dip exit from its own fill (stop -4%, arm +1.245%, giveback 10%)
           "mode c"       the add takes Mode C's exit (stop -3%, arm +1.283%, giveback 22%)
           "line 8h"      the add is held against the 8-hour line once its trail arms (Mode A), stop -4%
  lots     SHARED with TRX's 3 deployed lots, or 1-3 lots of its own

An add only exists while its parent is open, and a pyramid lot is never itself a parent. TRX has no blocked
hours. Corrected window engine, hourly mark-to-market drawdown, walk-forward selection against the fair control:
the same money in more shared lots, because TRX's core scales with money.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import eth_regime as rg
import sol_wide_stop as w
import trx_modec_lots as ml
import trx_pullback as tp
from sol_wide_stop import TRAINS, simulate

CORE, PYRA = {"dip", "breakout"}, {"pyramid"}
STEPS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
LEVELS = [1, 2, 3]
SCOPES = ["all lots", "dip lots", "mode c lots"]
GUARDS = ["none", "above 8h", "above 24h"]
EXITS = ["with parent", "dip", "mode c", "line 8h"]
SIZES = [1, 2, 3]


def parents_of(core):
    return [{**trade, "key": index, "parent": None} for index, trade in enumerate(core)]


def adds_for(parents, rule, lines, step, levels, scope, guard, exit_style):
    line = lines.get(guard)
    exit_line = lines["above 8h"] if exit_style == "line 8h" else None
    arm, giveback, stop = {
        "dip": (rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"]),
        "mode c": (tp.MODE_C["arm"], tp.MODE_C["giveback"], tp.MODE_C["stop"]),
        "line 8h": (rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"]),
    }.get(exit_style, (rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"]))
    out = []
    for parent in parents:
        if scope == "dip lots" and parent["source"] != "dip":
            continue
        if scope == "mode c lots" and parent["source"] != "breakout":
            continue
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
                exit_at, price, why = w.resolve(entry, arm, giveback, stop, exit_line)
            out.append({"entry": entry, "exit": exit_at, "price": price, "source": "pyramid", "why": why,
                        "key": f"a{parent['key']}.{level}", "parent": parent["key"]})
            start = entry
    return out


def simulate_book(trades, pots, start, end):
    """simulate(), plus the rule that an add can only be bought while its parent is actually open."""
    alive, filtered = set(), []
    for trade in sorted(trades, key=lambda t: (t["entry"], t.get("parent") is not None)):
        if trade.get("parent") is None:
            filtered.append(trade)
    return simulate(trades, pots, start, end)


def score(label, trades, pots):
    runs = {x: simulate(trades, pots, *research.WINDOWS[x]) for x in ("full", "unseen", *rg.TESTS)}
    led = runs["full"]["ledger"]
    wf = [runs[x]["profit"] for x in rg.TESTS]
    adds = led[led.source == "pyramid"] if len(led) else led
    return {"setup": label, "money": int(runs["full"]["capital"]), "trades": len(led), "adds": len(adds),
            "adds_pnl": round(adds.pnl.sum(), 2) if len(adds) else 0.0,
            "add_win%": round(100 * (adds.pnl > 0).mean(), 1) if len(adds) else 0.0,
            "win%": round(100 * (led.pnl > 0).mean(), 1) if len(led) else 0.0,
            "profit": round(runs["full"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "windows": f"{sum(x > 0 for x in wf)}/6", "unseen": round(runs["unseen"]["profit"], 2),
            "mtm_dd%": round(runs["full"]["mtm_dd%"], 2)}


def name_of(key):
    step, levels, scope, guard, exit_style = key
    return f"+{step:g}% x{levels}, {scope}, guard {guard}, exit {exit_style}"


def main() -> None:
    raw, bullish = tp.setup()
    rule = live.load_rule(tp.COIN)
    core = sorted(ml.dip_trades(raw, rule) + ml.break_trades(raw, rule, 40, 2.0, 3, "mode c"),
                  key=lambda t: t["entry"])
    parents = parents_of(core)
    lines = {f"above {h}h": pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy()
             for h in (8, 24)}
    pd.set_option("display.width", 275)

    controls = {n: score(f"shared {n} lots (control)", core, [(n, CORE)]) for n in (3, 4, 5, 6)}
    print("=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    keys = [(s, l, sc, g, e) for s in STEPS for l in LEVELS for sc in SCOPES for g in GUARDS for e in EXITS]
    sets = {key: adds_for(parents, rule, lines, *key) for key in keys}
    sets = {k: v for k, v in sets.items() if v}
    counts = pd.Series({k: len(v) for k, v in sets.items()})
    print(f"\n{len(sets)} pyramid rules; adds offered: median {counts.median():.0f}, "
          f"range {counts.min()}-{counts.max()}")

    print("\n=== 1. SHARED: the adds compete for TRX's 3 deployed lots (best 10 by walk-forward)")
    rows = [controls[3]] + [score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE | PYRA)])
                            for k, v in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  beating no pyramid: {int((frame.walk_forward > controls[3]['walk_forward']).sum())}/{len(frame) - 1}"
          f" on walk-forward, {int((frame.profit > controls[3]['profit']).sum())}/{len(frame) - 1} on the full window")

    print("\n=== 2. SEPARATE: the core carries on, the adds hold lots of their own")
    for size in SIZES:
        control = controls[3 + size]
        rows = [score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE), (size, PYRA)])
                for k, v in sets.items()]
        part = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
        print(f"\n  --- own {size} (${(3 + size) * 100}) against {3 + size} shared lots "
              f"(+${control['walk_forward']:.2f}, {control['windows']}, {control['mtm_dd%']}%)")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating that control: {int((part.walk_forward > control['walk_forward']).sum())}/{len(part)} "
              f"on walk-forward, {int((part['mtm_dd%'] > control['mtm_dd%']).sum())}/{len(part)} on drawdown")

    print("\n=== 3. is there a plateau? walk-forward by step and adds (own 2, all lots, guard none, with parent)")
    table = pd.DataFrame({f"x{l}": {f"+{s:g}%":
                                    score("x", sorted(core + sets[(s, l, 'all lots', 'none', 'with parent')],
                                                      key=lambda t: t["entry"]), [(3, CORE), (2, PYRA)])["walk_forward"]
                                    for s in STEPS} for l in LEVELS})
    print(table.round(2).to_string())

    print("\n=== 4. the honest test: the pyramid rule is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for label, pots, control_pots in (("shared, 3 lots", [(3, CORE | PYRA)], [(3, CORE)]),
                                      ("own 1", [(3, CORE), (1, PYRA)], [(4, CORE)]),
                                      ("own 2", [(3, CORE), (2, PYRA)], [(5, CORE)]),
                                      ("own 3", [(3, CORE), (3, PYRA)], [(6, CORE)])):
        control_w = {x: simulate(core, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        scores = {k: {x: simulate(sorted(core + v, key=lambda t: t["entry"]), pots,
                                  *research.WINDOWS[x])["profit"] for x in windows} for k, v in sets.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(sets, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        print(f"\n  --- {label}")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    best fixed rule in hindsight {name_of(best)}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")


if __name__ == "__main__":
    main()
