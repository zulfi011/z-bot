"""Should TRX's Mode C break have lots of its own, instead of sharing the dip's three?

Today the dip and Mode C compete for the same 3 lots, first come first served. Mode C fires about 100 times in
two years against the dip's 138, so the two really do take slots from each other. This asks whether separating
them pays - and, because TRX's core scales with money ([[trx-pullback-rejected]]), it is judged against the only
fair control: the same money spread over more SHARED lots.

Every combination:
  bars      the quiet band is 24 / 40 (deployed) / 60 hourly bars long
  zone      no wider than 1.5 / 2.0 (deployed) / 2.5%
  confirm   the re-check after the break: 0 / 3 (deployed) / 10 minutes
  exit      Mode C's own numbers (stop -3%, arm +1.283%, giveback 22%) or the dip's (-4%, +1.245%, 10%)
  lots      SHARED (as deployed) or Mode C on 1-3 lots of its own beside the dip's 3

Corrected window engine, hourly mark-to-market drawdown, walk-forward selection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import eth_regime as rg
import sol_wide_stop as w
import trx_pullback as tp
from sol_wide_stop import TRAINS, simulate

DIP, BREAK = {"dip"}, {"breakout"}
BOTH = DIP | BREAK
BARS = [24, 40, 60]
ZONES = [1.5, 2.0, 2.5]
CONFIRMS = [0, 3, 10]
EXITS = ["mode c", "dip"]
SIZES = [1, 2, 3]
DEPLOYED = (40, 2.0, 3, "mode c")


def dip_trades(raw, rule):
    out = []
    for entry in live.live_entries(raw, rule):
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"], None)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": "dip", "why": why})
    return out


def break_trades(raw, rule, bars, zone, confirm, exit_style):
    high, low, open_, close, last_minute = v4.bars_for(raw, tp.MODE_C["chart"])
    entries = v4.entries_for(high, low, close, last_minute, bars, zone, confirm, grid.CLOSE, len(raw))
    arm, giveback, stop = ((tp.MODE_C["arm"], tp.MODE_C["giveback"], tp.MODE_C["stop"]) if exit_style == "mode c"
                           else (rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"]))
    out = []
    for entry in entries:
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, arm, giveback, stop, None)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": "breakout", "why": why})
    return out


def score(label, trades, pots):
    runs = {x: simulate(trades, pots, *research.WINDOWS[x]) for x in ("full", "unseen", *rg.TESTS)}
    led = runs["full"]["ledger"]
    wf = [runs[x]["profit"] for x in rg.TESTS]
    breaks = led[led.source == "breakout"] if len(led) else led
    dips = led[led.source == "dip"] if len(led) else led
    return {"setup": label, "money": int(runs["full"]["capital"]), "dips": len(dips), "breaks": len(breaks),
            "dip_pnl": round(dips.pnl.sum(), 2) if len(dips) else 0.0,
            "break_pnl": round(breaks.pnl.sum(), 2) if len(breaks) else 0.0,
            "win%": round(100 * (led.pnl > 0).mean(), 1) if len(led) else 0.0,
            "profit": round(runs["full"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "windows": f"{sum(x > 0 for x in wf)}/6", "unseen": round(runs["unseen"]["profit"], 2),
            "mtm_dd%": round(runs["full"]["mtm_dd%"], 2)}


def name_of(key):
    bars, zone, confirm, exit_style = key
    tag = " (deployed)" if key == DEPLOYED else ""
    return f"{bars} bars <= {zone:g}%, wait {confirm}m, exit {exit_style}{tag}"


def main() -> None:
    raw, bullish = tp.setup()
    rule = live.load_rule(tp.COIN)
    dips = dip_trades(raw, rule)
    pd.set_option("display.width", 270)

    sets = {(b, z, c, e): break_trades(raw, rule, b, z, c, e)
            for b in BARS for z in ZONES for c in CONFIRMS for e in EXITS}
    deployed_book = sorted(dips + sets[DEPLOYED], key=lambda t: t["entry"])
    print(f"TRX: {len(dips)} dip signals; Mode C signals by setting: "
          f"{ {f'{b}b/{z:g}%/{c}m': len(sets[(b, z, c, 'mode c')]) for b in BARS for z in (2.0,) for c in (3,)} }")

    print("\n=== 0. the controls: everything shared, on 3 to 7 lots")
    controls = {n: score(f"shared {n} lots (control)", deployed_book, [(n, BOTH)]) for n in (3, 4, 5, 6, 7)}
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())
    print("\n  and the dip alone, so Mode C's real contribution is visible")
    print(pd.DataFrame([score("dip only, 3 lots", dips, [(3, DIP)]),
                        score("dip only, 4 lots", dips, [(4, DIP)])]).set_index("setup").to_string())

    print("\n=== 1. Mode C on lots of its own, deployed settings, against the same money shared")
    rows = []
    for size in SIZES:
        rows.append(controls[3 + size])
        rows.append(score(f"dip 3 + Mode C own {size}", deployed_book, [(3, DIP), (size, BREAK)]))
    print(pd.DataFrame(rows).set_index("setup").to_string())

    print("\n=== 2. every Mode C setting, on 2 lots of its own (best 10 by walk-forward)")
    rows = [score(name_of(key), sorted(dips + trades, key=lambda t: t["entry"]), [(3, DIP), (2, BREAK)])
            for key, trades in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(10).to_string())
    print(f"  beating shared 5 lots (+${controls[5]['walk_forward']:.2f}): "
          f"{int((frame.walk_forward > controls[5]['walk_forward']).sum())}/{len(frame)}")

    print("\n=== 3. every Mode C setting, SHARED on the 3 deployed lots (best 6)")
    rows = [score(name_of(key), sorted(dips + trades, key=lambda t: t["entry"]), [(3, BOTH)])
            for key, trades in sets.items()]
    frame3 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame3.set_index("setup").head(6).to_string())
    print(f"  beating the deployed settings (+${controls[3]['walk_forward']:.2f}): "
          f"{int((frame3.walk_forward > controls[3]['walk_forward']).sum())}/{len(frame3)}")

    print("\n=== 4. the honest test: the Mode C setting is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for label, pots, control_pots in (("shared, 3 lots", [(3, BOTH)], [(3, BOTH)]),
                                      ("own 1", [(3, DIP), (1, BREAK)], [(4, BOTH)]),
                                      ("own 2", [(3, DIP), (2, BREAK)], [(5, BOTH)]),
                                      ("own 3", [(3, DIP), (3, BREAK)], [(6, BOTH)])):
        control_w = {x: simulate(deployed_book, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        scores = {key: {x: simulate(sorted(dips + trades, key=lambda t: t["entry"]), pots,
                                    *research.WINDOWS[x])["profit"] for x in windows}
                  for key, trades in sets.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        fixed = sum(scores[DEPLOYED][t] - control_w[t] for t in rg.TESTS)
        print(f"\n  --- {label} (control: {'the deployed settings' if label.startswith('shared') else f'{control_pots[0][0]} shared lots'})")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    deployed settings, no choice at all: ${fixed:8.2f}, window by window "
              f"{', '.join(f'{scores[DEPLOYED][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")
        print(f"    it picked: {'; '.join(name_of(p) for p in picks)}")


if __name__ == "__main__":
    main()
