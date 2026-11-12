"""Does the pullback entry help AAVE, and on what settings?

The third way in built for ETH, tuned from scratch for AAVE: in an uptrend, 1-minute closes below an N-hour EMA
for at least `dwell` minutes, then the first close back above it buys at the next minute.

AAVE has no trend exit - Mode A was tested when the strategy was built and deliberately left out (its honest
contribution was $2) - so a pullback lot has to be told how to leave. Every combination:

  line      4 / 8 / 12 / 24 / 36 / 48 hours
  dwell     15 / 60 / 180 / 360 minutes below it
  uptrend   require 7d > 15d > 30d at the signal, or take any reclaim
  hours     obey AAVE's 06:00-12:00 blocked window, or ignore it (it was fitted to the dip entry)
  exit      "dip"      AAVE's deployed numbers (stop -4%, arm +1.276%, giveback 20%)
            "mode c"   its Mode C numbers (stop -3.5%, arm +1.283%, giveback 22%)
            "wide"     the dip trail with a -6% stop
            "line 8h" / "line 16h" / "line 24h"  held against that EMA once the trail arms (Mode A)
  lots      SHARED with AAVE's 3 deployed lots, or 1-3 lots of its own

Each own-lot version is judged against BOTH controls at the same money: more shared lots, and 3 bigger lots.
Corrected window engine, hourly mark-to-market drawdown, walk-forward selection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_pullback as pb
import eth_regime as rg
import aave_settings_recheck as a
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE, PULL = {"dip", "breakout"}, {"pullback"}
HOURS = [4, 8, 12, 24, 36, 48]
DWELL = [15, 60, 180, 360]
UPTREND = [True, False]
BLOCKED = [True, False]
EXITS = ["dip", "mode c", "wide", "line 8h", "line 16h", "line 24h"]
SIZES = [1, 2, 3]


def pullback_trades(entries, rule, exit_style, lines):
    arm, giveback, stop = {
        "dip": (rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"]),
        "mode c": (a.MODE_C["arm"], a.MODE_C["giveback"], a.MODE_C["stop"]),
        "wide": (rule["activation_pct"], rule["giveback_pct"], 6.0),
    }.get(exit_style, (rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"]))
    line = lines.get(exit_style)
    out = []
    for entry in entries:
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, arm, giveback, stop, line)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": "pullback", "why": why})
    return out


def name_of(key):
    hours, dwell, uptrend, blocked, exit_style = key
    return (f"{hours}h line, {dwell}m below{'' if uptrend else ', any market'}"
            f"{'' if blocked else ', all hours'}, exit {exit_style}")


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
    core = a.build(raw, frames)
    lines = {f"line {h}h": pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy()
             for h in (8, 16, 24)}
    pd.set_option("display.width", 270)

    base = vf.score("AAVE as deployed, 3 x $100", core, [(3, CORE)])
    controls = {"base": base}
    for n in (4, 5, 6):
        controls[f"{n} shared"] = vf.score(f"{n} x $100 shared (control)", core, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger {n}"] = vf.score(f"3 x ${n * 100 / 3:.0f} (control)", core, [(3, CORE)])
        w.LOT = 100.0
    print("=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    everywhere = np.ones(len(grid.CLOSE), bool)
    entries = {}
    for hours in HOURS:
        for dwell in DWELL:
            for uptrend in UPTREND:
                for blocked in BLOCKED:
                    entries[(hours, dwell, uptrend, blocked)] = pb.pullback_entries(
                        grid.CLOSE, bullish if uptrend else everywhere, hours, dwell, grid.TIMES,
                        blocked=rule["blocked"] if blocked else None)
    counts = pd.Series({k: len(v) for k, v in entries.items()})
    print(f"\nAAVE: {len(core)} core signals; {len(entries)} entry settings x {len(EXITS)} exits = "
          f"{len(entries) * len(EXITS)} rules; reclaims per setting: median {counts.median():.0f}, "
          f"range {counts.min()}-{counts.max()}")

    sets = {(*k, e): pullback_trades(v, rule, e, lines) for k, v in entries.items() for e in EXITS}
    sets = {k: v for k, v in sets.items() if v}

    print("\n=== 1. SHARED: the pullback competes for AAVE's 3 deployed lots (best 10 by walk-forward)")
    rows = [base] + [vf.score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE | PULL)])
                     for k, v in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  beating no pullback: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame) - 1} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame) - 1} on the full window")

    print("\n=== 2. the pullback ALONE, on its own money (3 x $100) - best 5")
    alone = pd.DataFrame([vf.score(name_of(k), v, [(3, PULL)]) for k, v in sets.items()])
    print(alone.sort_values("walk_forward", ascending=False).set_index("setup").head(5).to_string())
    print(f"  pullback rules that made money alone: {int((alone.profit > 0).sum())}/{len(alone)}")

    print("\n=== 3. SEPARATE: the core carries on, the pullback holds lots of its own")
    for size in SIZES:
        more, bigger = controls[f"{3 + size} shared"], controls[f"3 bigger {3 + size}"]
        rows3 = [vf.score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE), (size, PULL)])
                 for k, v in sets.items()]
        part = pd.DataFrame(rows3).sort_values("walk_forward", ascending=False)
        print(f"\n  --- own {size} (${(3 + size) * 100}) against {3 + size} shared lots "
              f"(+${more['walk_forward']:.2f}) and 3 bigger lots (+${bigger['walk_forward']:.2f})")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating more lots: {int((part.walk_forward > more['walk_forward']).sum())}/{len(part)}; "
              f"beating bigger lots: {int((part.walk_forward > bigger['walk_forward']).sum())}/{len(part)}")

    print("\n=== 4. the honest test: the pullback rule is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    books = {k: sorted(core + v, key=lambda t: t["entry"]) for k, v in sets.items()}
    for label, pots, control_pots, control_lot in (
            ("shared, 3 lots", [(3, CORE | PULL)], [(3, CORE)], 100.0),
            ("own 1 vs bigger lots", [(3, CORE), (1, PULL)], [(3, CORE)], 400 / 3),
            ("own 2 vs more lots", [(3, CORE), (2, PULL)], [(5, CORE)], 100.0),
            ("own 2 vs bigger lots", [(3, CORE), (2, PULL)], [(3, CORE)], 500 / 3),
            ("own 3 vs bigger lots", [(3, CORE), (3, PULL)], [(3, CORE)], 200.0)):
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
