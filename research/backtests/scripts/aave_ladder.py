"""AAVE dip ladder: buy the dislocation itself, in steps, below the average.

AAVE's dip entry waits for price to come back UP to its 10-day average, inside a tight +-0.1% zone. The ladder
bets the other way: the further below the average AAVE falls, the better the price, so buy a lot at each rung on
the way down and wait for the reversion.

Every combination (rungs sized for the most volatile coin in the book - median daily ATR 7.31%):
  average   the deployed 10-day average, or a faster 5-day one
  rungs     -2/-4/-6%, -3/-6/-9%, -4/-8/-12%, -5/-10/-15% or -6/-12/-18%, used one, two or three deep
  reset     a dip ends when a close gets back to the average; only then can the rungs fire again
  exit      "average" - sell when the close is back at the average, with a ladder stop 8 / 12 / 20% below the
            average or none at all - or AAVE's own dip exit, or that exit with a -8% stop
  lots      SHARED with the 3 deployed lots, or 1-3 lots of its own, judged against more shared lots AND
            3 bigger lots

No downtrend filter: deep dips happen when the averages are stacked downward, which is the point. Hourly
mark-to-market drawdown matters most here - a ladder sits underwater for weeks.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_regime as rg
import aave_settings_recheck as a
import sol_ladder as sl
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE, LAD = {"dip", "breakout"}, {"ladder"}
AVERAGES = [10, 5]
RUNG_SETS = [(2.0, 4.0, 6.0), (3.0, 6.0, 9.0), (4.0, 8.0, 12.0), (5.0, 10.0, 15.0), (6.0, 12.0, 18.0)]
DEPTHS = [1, 2, 3]
EXITS = [("average", 8.0), ("average", 12.0), ("average", 20.0), ("average", None), ("dip", None),
         ("dip wide", None)]
SIZES = [1, 2, 3]


def build(avg, runs, rule, rungs, depth, exit_style, ladder_stop):
    deviation = grid.CLOSE / avg - 1
    last = len(grid.OPEN) - 1
    stop = rule["stop_pct"] if exit_style == "dip" else 8.0
    trades = []
    for start, end in runs:
        finish = end if end > 0 else last
        first_fill = None
        for level in rungs[:depth]:
            reached = np.flatnonzero(deviation[start:finish] <= -level / 100)
            if not len(reached):
                break
            entry = start + int(reached[0]) + 1
            if entry >= finish or entry >= last:
                break
            if first_fill is None:
                first_fill = float(avg[entry]) if np.isfinite(avg[entry]) else None
            if exit_style in ("dip", "dip wide"):
                exit_at, price, why = w.resolve(entry, rule["activation_pct"], rule["giveback_pct"], stop, None)
            else:
                exit_at, price, why = min(finish + 1, last), float(grid.OPEN[min(finish + 1, last)]), 7
                if ladder_stop is not None and first_fill:
                    level_price = first_fill * (1 - ladder_stop / 100)
                    hit = np.flatnonzero(grid.LOW[entry:exit_at] <= level_price)
                    if len(hit):
                        exit_at = entry + int(hit[0])
                        price, why = min(level_price, float(grid.OPEN[exit_at])), 2
            trades.append({"entry": int(entry), "exit": int(exit_at), "price": price, "source": "ladder",
                           "why": why})
    return sorted(trades, key=lambda t: t["entry"])


def name_of(key):
    days, rungs, depth, exit_style, stop = key
    where = "/".join(f"-{r:g}%" for r in rungs[:depth])
    tail = exit_style if exit_style != "average" else f"back to average, stop {'none' if stop is None else f'-{stop:g}%'}"
    return f"{days}d avg {where}, exit {tail}"


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
    pd.set_option("display.width", 275)

    base = vf.score("AAVE as deployed, 3 x $100", core, [(3, CORE)])
    controls = {"base": base}
    for n in (4, 5, 6):
        controls[f"{n} shared"] = vf.score(f"{n} x $100 shared (control)", core, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger {n}"] = vf.score(f"3 x ${n * 100 / 3:.0f} (control)", core, [(3, CORE)])
        w.LOT = 100.0
    print("=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    averages = {days: sl.average_of(raw, days) for days in AVERAGES}
    runs = {days: sl.dip_runs(averages[days]) for days in AVERAGES}
    print("\n=== 0. how far below its average AAVE actually goes")
    for days in AVERAGES:
        deviation = grid.CLOSE / averages[days] - 1
        reach = [f"{level:g}%: {sum(1 for s, e in runs[days] if (deviation[s:(e if e > 0 else len(deviation))] <= -level / 100).any())}"
                 for level in (2, 4, 6, 8, 12, 18)]
        print(f"  {days}-day average: {len(runs[days])} dips below it; deepest "
              f"{100 * pd.Series(deviation).dropna().min():.1f}%; dips reaching " + ", ".join(reach))

    keys = [(d, r, k, e, s) for d in AVERAGES for r in RUNG_SETS for k in DEPTHS for e, s in EXITS]
    sets = {key: build(averages[key[0]], runs[key[0]], rule, key[1], key[2], key[3], key[4]) for key in keys}
    sets = {k: v for k, v in sets.items() if v}
    print(f"\n{len(sets)} ladder rules; lots offered: median "
          f"{pd.Series({k: len(v) for k, v in sets.items()}).median():.0f}")

    print("\n=== 1. the ladder ALONE, on its own money (3 x $100) - best 8")
    rows = [vf.score(name_of(k), v, [(3, LAD)]) for k, v in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(8).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  ladders that made money alone: {int((frame.profit > 0).sum())}/{len(frame)}")

    print("\n=== 2. SHARED: the ladder competes for AAVE's 3 deployed lots (best 8)")
    rows = [base] + [vf.score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE | LAD)])
                     for k, v in sets.items()]
    frame2 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame2.set_index("setup").head(8).to_string())
    print(f"  beating no ladder: {int((frame2.walk_forward > base['walk_forward']).sum())}/{len(frame2) - 1} on "
          f"walk-forward, {int((frame2.profit > base['profit']).sum())}/{len(frame2) - 1} on the full window")

    print("\n=== 3. SEPARATE: the core carries on, the ladder holds lots of its own")
    for size in SIZES:
        more, bigger = controls[f"{3 + size} shared"], controls[f"3 bigger {3 + size}"]
        rows3 = [vf.score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE), (size, LAD)])
                 for k, v in sets.items()]
        part = pd.DataFrame(rows3).sort_values("walk_forward", ascending=False)
        print(f"\n  --- own {size} (${(3 + size) * 100}) against {3 + size} shared lots "
              f"(+${more['walk_forward']:.2f}) and 3 bigger lots (+${bigger['walk_forward']:.2f})")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating more lots: {int((part.walk_forward > more['walk_forward']).sum())}/{len(part)}; "
              f"beating bigger lots: {int((part.walk_forward > bigger['walk_forward']).sum())}/{len(part)}")

    print("\n=== 4. the honest test: the ladder is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    books = {k: sorted(core + v, key=lambda t: t["entry"]) for k, v in sets.items()}
    for label, pots, control_pots, control_lot in (
            ("shared, 3 lots", [(3, CORE | LAD)], [(3, CORE)], 100.0),
            ("own 2 vs more lots", [(3, CORE), (2, LAD)], [(5, CORE)], 100.0),
            ("own 2 vs bigger lots", [(3, CORE), (2, LAD)], [(3, CORE)], 500 / 3)):
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
        print(f"    best fixed ladder in hindsight {name_of(best)}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")


if __name__ == "__main__":
    main()
