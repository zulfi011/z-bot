"""SOL dip ladder: buy the dislocation itself, in steps, below the average.

SOL's dip entry waits for price to come back UP to its 12-day average. The ladder bets the other way: the further
below the average SOL falls, the better the price, so buy a lot at each rung on the way down and wait for the
reversion.

  average   SOL's deployed 12-day average, or a faster 7-day one (completed UTC days, effective the next day)
  rungs     one lot the first time a 1-minute close reaches each rung below the average; the next minute buys.
            Rung sets from shallow to deep, used one, two or three deep.
  reset     a dip ends when a close gets back to the average; only then can the rungs fire again
  exit      "average"   every rung lot sells at the next minute's open once the close is back at the average -
                        the reversion it is betting on - with a hard ladder stop 10 / 15 / 20% below the average,
                        or with no stop at all
            "dip"       each rung lot takes SOL's deployed dip exit from its own fill (-2% stop, trail +1.251%)
            "mode a"    each rung lot is held against the 8-hour line
  lots      SHARED with SOL's 3 deployed lots, or 1-3 lots of its own

No downtrend filter: deep dips happen exactly when the averages are stacked downward, which is the point.
Corrected window engine and hourly mark-to-market drawdown - essential here, because a ladder can sit underwater
for weeks before it is sold.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import stage3_replay as replay
import eth_regime as rg
import sol_pullback as sp
import sol_wide_stop as w
from sol_wide_stop import CORE, TRAINS, simulate

LAD = {"ladder"}
AVERAGES = [12, 7]
RUNG_SETS = [(2.0, 4.0, 6.0), (3.0, 5.0, 7.0), (3.0, 6.0, 9.0), (4.0, 7.0, 10.0), (5.0, 8.0, 11.0),
             (6.0, 9.0, 12.0)]
DEPTHS = [1, 2, 3]
EXITS = [("average", 10.0), ("average", 15.0), ("average", 20.0), ("average", None), ("dip", None),
         ("mode a", None)]
SIZES = [1, 2, 3]


def average_of(raw, days):
    table = replay.daily_average_n(raw, days)
    day = raw.open_time.dt.floor("D")
    return day.map({d: float(v) for d, v in table.items() if v is not None}).to_numpy(float)


def dip_runs(avg):
    """(start, end) minute ranges where the close is below the average; end = the first close back at it."""
    below = np.isfinite(avg) & (w.grid.CLOSE < avg)
    change = np.flatnonzero(np.diff(below.astype(np.int8))) + 1
    starts, ends = change[below[change]], change[~below[change]]
    return [(int(s), int(ends[ends > s][0]) if len(ends[ends > s]) else -1) for s in starts]


def build(avg, runs, bullish, ema, rule, rungs, depth, exit_style, ladder_stop):
    """One lot per rung reached, exiting the way `exit_style` says."""
    deviation = w.grid.CLOSE / avg - 1
    last = len(w.grid.OPEN) - 1
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
            if exit_style in ("dip", "mode a"):
                line = ema if (exit_style == "mode a" or bullish[entry]) else None
                exit_at, price, why = w.resolve(entry, rule["activation_pct"], rule["giveback_pct"],
                                                rule["stop_pct"], line)
            else:
                exit_at, price, why = min(finish + 1, last), float(w.grid.OPEN[min(finish + 1, last)]), 7
                if ladder_stop is not None and first_fill:
                    level_price = first_fill * (1 - ladder_stop / 100)
                    hit = np.flatnonzero(w.grid.LOW[entry:exit_at] <= level_price)
                    if len(hit):
                        exit_at = entry + int(hit[0])
                        price, why = min(level_price, float(w.grid.OPEN[exit_at])), 2
            trades.append({"entry": int(entry), "exit": int(exit_at), "price": price, "source": "ladder",
                           "why": why})
    return sorted(trades, key=lambda t: t["entry"])


def name_of(key):
    days, rungs, depth, exit_style, stop = key
    where = "/".join(f"-{r:g}%" for r in rungs[:depth])
    tail = exit_style if exit_style != "average" else f"back to average, stop {'none' if stop is None else f'-{stop:g}%'}"
    return f"{days}d avg {where}, exit {tail}"


def main() -> None:
    raw, bullish, ema = sp.setup()
    rule, dips, breaks = w.signals(raw)
    core = w.core_trades(rule, dips, breaks, bullish, ema)
    pd.set_option("display.width", 275)

    base = w.score("SOL as deployed, 3 x $100", core, [(3, CORE)])
    controls = {n: w.score(f"flat core {n} (control)", core, [(n, CORE)]) for n in (4, 5, 6)}
    print("=== the controls")
    print(pd.DataFrame([base, *controls.values()]).set_index("setup").to_string())

    averages = {days: average_of(raw, days) for days in AVERAGES}
    runs = {days: dip_runs(averages[days]) for days in AVERAGES}
    print("\n=== 0. how far below its average SOL actually goes")
    for days in AVERAGES:
        deviation = w.grid.CLOSE / averages[days] - 1
        inside = (w.grid.TIMES >= research.WINDOWS["full"][0]) & (w.grid.TIMES < research.WINDOWS["full"][1])
        series = pd.Series(deviation[inside]).dropna()
        depths = [f"{level:g}%: {int(sum(1 for s, e in runs[days] if (deviation[s:(e if e > 0 else len(deviation))] <= -level / 100).any()))}"
                  for level in (2, 4, 6, 8, 10, 12)]
        print(f"  {days}-day average: {len(runs[days])} dips below it; deepest {100 * series.min():.1f}%, "
              f"median minute {100 * series.median():.2f}%; dips reaching " + ", ".join(depths))

    keys = [(d, r, k, e, s) for d in AVERAGES for r in RUNG_SETS for k in DEPTHS for e, s in EXITS]
    sets = {key: build(averages[key[0]], runs[key[0]], bullish, ema, rule, key[1], key[2], key[3], key[4])
            for key in keys}
    sets = {key: trades for key, trades in sets.items() if trades}
    print(f"\n{len(sets)} ladder rules; lots bought: median "
          f"{pd.Series({k: len(v) for k, v in sets.items()}).median():.0f}")

    print("\n=== 1. the ladder ALONE, on its own money (3 x $100) - best 10 by walk-forward")
    rows = [w.score(name_of(key), trades, [(3, LAD)]) for key, trades in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  ladders that made money alone: {int((frame.profit > 0).sum())}/{len(frame)}")

    print("\n=== 2. SHARED: the ladder competes for SOL's 3 deployed lots")
    rows = [base] + [w.score(name_of(key), sorted(core + trades, key=lambda t: t["entry"]), [(3, CORE | LAD)])
                     for key, trades in sets.items()]
    frame2 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame2.set_index("setup").head(8).to_string())
    print(f"  beating no ladder: {int((frame2.walk_forward > base['walk_forward']).sum())}/{len(frame2) - 1} on "
          f"walk-forward, {int((frame2.profit > base['profit']).sum())}/{len(frame2) - 1} on the full window")

    print("\n=== 3. SEPARATE: the core carries on, the ladder holds lots of its own")
    for size in SIZES:
        control = controls[3 + size]
        rows = [w.score(name_of(key), sorted(core + trades, key=lambda t: t["entry"]), [(3, CORE), (size, LAD)])
                for key, trades in sets.items()]
        part = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
        print(f"\n  --- own {size} (${(3 + size) * 100}) against flat core {3 + size} "
              f"(+${control['walk_forward']:.2f}, {control['windows']}, {control['mtm_dd%']}%)")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating that control: {int((part.walk_forward > control['walk_forward']).sum())}/{len(part)} "
              f"on walk-forward, {int((part['mtm_dd%'] > control['mtm_dd%']).sum())}/{len(part)} on drawdown")

    print("\n=== 4. the honest test: the ladder is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for label, pots, control_pots in (("shared, 3 lots", [(3, CORE | LAD)], [(3, CORE)]),
                                      ("own 1", [(3, CORE), (1, LAD)], [(4, CORE)]),
                                      ("own 2", [(3, CORE), (2, LAD)], [(5, CORE)]),
                                      ("own 3", [(3, CORE), (3, LAD)], [(6, CORE)])):
        control_w = {x: simulate(core, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        scores = {key: {x: simulate(sorted(core + trades, key=lambda t: t["entry"]), pots,
                                    *research.WINDOWS[x])["profit"] for x in windows}
                  for key, trades in sets.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(sets, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        print(f"\n  --- {label}")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    best fixed ladder in hindsight {name_of(best)}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")


if __name__ == "__main__":
    main()
