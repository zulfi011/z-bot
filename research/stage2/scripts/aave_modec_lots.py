"""Should AAVE's Mode C break have lots of its own, instead of sharing the dip's three?

Today the dip and Mode C compete for the same 3 lots, first come first served. AAVE's dip fires far more often
(255 of its 289 trades), so Mode C rarely gets a slot when the dip is busy - and Mode C is the better-behaved of
the two (38 trades, +$24.44, an 89.5% win rate and six of six walk-forward windows in the original research).
This asks whether separating them pays, against the only fair controls: the same money in more SHARED lots, and
in 3 bigger lots.

Every combination:
  chart     the band is measured on 15 / 30 (deployed) / 60-minute bars
  bars      12 / 24 (deployed) / 40 of them
  width     no wider than 1.5 / 2.0 (deployed) / 2.5%
  wait      the re-check after the break: 0 / 30 / 60 (deployed) minutes
  exit      Mode C's own numbers (stop -3.5%, arm +1.283%, giveback 22%) or the dip's (-4%, +1.276%, 20%)
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
import stage3_replay as replay
import eth_adaptive_average as aa
import eth_regime as rg
import aave_settings_recheck as a
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

DIP, BREAK = {"dip"}, {"breakout"}
BOTH = DIP | BREAK
CHARTS = [15, 30, 60]
BARS = [12, 24, 40]
ZONES = [1.5, 2.0, 2.5]
WAITS = [0, 30, 60]
EXITS = ["mode c", "dip"]
SIZES = [1, 2, 3]
DEPLOYED = (30, 24, 2.0, 60, "mode c")


def dip_trades(raw, frames, rule):
    frame = frames[rule["minutes"]]
    entries = aa.entries_for(raw, rule, frame, aa.average_by_bar(raw, frame, 10 * 1440))
    out = []
    for entry in entries:
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"], None)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": "dip", "why": why})
    return out


def break_trades(raw, rule, chart, bars, zone, wait, exit_style):
    high, low, open_, close, last_minute = v4.bars_for(raw, chart)
    entries = v4.entries_for(high, low, close, last_minute, bars, zone, wait, grid.CLOSE, len(raw))
    if rule["blocked"] and len(entries):
        hours = grid.TIMES[entries].hour
        entries = entries[~((hours >= rule["blocked"][0]) & (hours < rule["blocked"][1]))]
    arm, giveback, stop = ((a.MODE_C["arm"], a.MODE_C["giveback"], a.MODE_C["stop"]) if exit_style == "mode c"
                           else (rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"]))
    out = []
    for entry in entries:
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, arm, giveback, stop, None)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": "breakout", "why": why})
    return out


def score(label, trades, pots):
    row = vf.score(label, trades, pots)
    led = simulate(trades, pots, *research.WINDOWS["full"])["ledger"]
    dips = led[led.source == "dip"] if len(led) else led
    breaks = led[led.source == "breakout"] if len(led) else led
    return {**row, "dips": len(dips), "breaks": len(breaks),
            "dip_pnl": round(dips.pnl.sum(), 2) if len(dips) else 0.0,
            "break_pnl": round(breaks.pnl.sum(), 2) if len(breaks) else 0.0}


def name_of(key):
    chart, bars, zone, wait, exit_style = key
    tag = " (deployed)" if key == DEPLOYED else ""
    return f"{bars} x {chart}m bars <= {zone:g}%, wait {wait}m, exit {exit_style}{tag}"


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
    dips = dip_trades(raw, frames, rule)
    pd.set_option("display.width", 285)

    sets = {(c, b, z, wt, e): break_trades(raw, rule, c, b, z, wt, e)
            for c in CHARTS for b in BARS for z in ZONES for wt in WAITS for e in EXITS}
    sets = {k: v for k, v in sets.items() if v}
    deployed_book = sorted(dips + sets[DEPLOYED], key=lambda t: t["entry"])
    print(f"AAVE: {len(dips)} dip signals, {len(sets[DEPLOYED])} Mode C signals at the deployed settings; "
          f"{len(sets)} Mode C rules")

    print("\n=== 0. the controls: everything shared, and the dip alone")
    controls = {n: score(f"shared {n} lots (control)", deployed_book, [(n, BOTH)]) for n in (3, 4, 5, 6)}
    for n in (4, 5, 6):
        w.LOT = n * 100 / 3
        controls[f"bigger {n}"] = score(f"3 x ${n * 100 / 3:.0f} shared (control)", deployed_book, [(3, BOTH)])
        w.LOT = 100.0
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())
    print(pd.DataFrame([score("dip only, 3 lots", dips, [(3, DIP)])]).set_index("setup").to_string())

    print("\n=== 1. Mode C on lots of its own, deployed settings, against the same money")
    rows = []
    for size in SIZES:
        rows.append(controls[3 + size])
        rows.append(controls[f"bigger {3 + size}"])
        rows.append(score(f"dip 3 + Mode C own {size}", deployed_book, [(3, DIP), (size, BREAK)]))
    print(pd.DataFrame(rows).set_index("setup").to_string())

    print("\n=== 2. every Mode C setting, on 2 lots of its own (best 8 by walk-forward)")
    rows = [score(name_of(k), sorted(dips + v, key=lambda t: t["entry"]), [(3, DIP), (2, BREAK)])
            for k, v in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(8).to_string())
    print(f"  beating shared 5 lots (+${controls[5]['walk_forward']:.2f}): "
          f"{int((frame.walk_forward > controls[5]['walk_forward']).sum())}/{len(frame)}; beating 3 x $167 "
          f"(+${controls['bigger 5']['walk_forward']:.2f}): "
          f"{int((frame.walk_forward > controls['bigger 5']['walk_forward']).sum())}/{len(frame)}")

    print("\n=== 3. every Mode C setting, SHARED on the 3 deployed lots (best 6)")
    rows = [score(name_of(k), sorted(dips + v, key=lambda t: t["entry"]), [(3, BOTH)]) for k, v in sets.items()]
    frame3 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame3.set_index("setup").head(6).to_string())
    print(f"  beating the deployed settings (+${controls[3]['walk_forward']:.2f}): "
          f"{int((frame3.walk_forward > controls[3]['walk_forward']).sum())}/{len(frame3)}")

    print("\n=== 4. the honest test: the Mode C setting is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    books = {k: sorted(dips + v, key=lambda t: t["entry"]) for k, v in sets.items()}
    for label, pots, control_pots, control_lot in (
            ("shared, 3 lots", [(3, BOTH)], [(3, BOTH)], 100.0),
            ("own 1 vs more lots", [(3, DIP), (1, BREAK)], [(4, BOTH)], 100.0),
            ("own 1 vs bigger lots", [(3, DIP), (1, BREAK)], [(3, BOTH)], 400 / 3),
            ("own 2 vs more lots", [(3, DIP), (2, BREAK)], [(5, BOTH)], 100.0),
            ("own 2 vs bigger lots", [(3, DIP), (2, BREAK)], [(3, BOTH)], 500 / 3)):
        w.LOT = control_lot
        control_w = {x: simulate(deployed_book, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        w.LOT = 100.0
        scores = {k: {x: simulate(v, pots, *research.WINDOWS[x])["profit"] for x in windows} for k, v in books.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        fixed = sum(scores[DEPLOYED][t] - control_w[t] for t in rg.TESTS)
        best = max(books, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        print(f"\n  --- {label}")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    deployed Mode C settings, no choice: ${fixed:8.2f}, window by window "
              f"{', '.join(f'{scores[DEPLOYED][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")
        print(f"    best fixed setting in hindsight {name_of(best)}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}")


if __name__ == "__main__":
    main()
