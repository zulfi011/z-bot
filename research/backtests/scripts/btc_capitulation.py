"""BTC capitulation reversal: buy when a sharp sell-off's forced selling runs out.

Hourly bars from 1-minute data; aggressive SELLING = volume - taker buy.

  drop     the hour's close is at least D% below the highest high of the previous 12 / 24 / 48 hours
  climax   that hour's selling is at least 2 / 3 / 5x its own 7-day hourly average, or no volume test
  turn     the next hour closes green with selling under half the climax hour's, just a green hour, or a
           reclaim of the climax hour's high
  buy      the first minute after the turn hour closes, at most one entry per 24 hours
  exit     BTC's deployed numbers (stop -3%, arm +1.257%, giveback 14%), the same trail with a -5% or -8% stop,
           or the deployed stop with a later +3% arm
  lots     SHARED with BTC's 3 deployed lots, or 1-3 lots of its own

No blocked hours and no trend filter: a capitulation happens BECAUSE the market is breaking down. Judged against
both controls at the same money - more shared lots and 3 bigger lots - with the corrected window engine, hourly
mark-to-market drawdown and walk-forward selection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import eth_regime as rg
import btc_pullback as bp
import btc_volume_filter as bv
import sol_capitulation as sc
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE, CAP = {"dip"}, {"capitulation"}
DROPS = [2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
LOOKBACKS = [12, 24, 48]
CLIMAX = [None, 2.0, 3.0, 5.0]
TURNS = ["green + calmer", "green", "reclaim"]
EXITS = ["dip", "stop -5%", "stop -8%", "arm +3%"]
SIZES = [1, 2, 3]


def build(events, rule, drop, lookback, climax, turn, exit_style):
    arm, stop = {
        "dip": (rule["activation_pct"], rule["stop_pct"]),
        "stop -5%": (rule["activation_pct"], 5.0),
        "stop -8%": (rule["activation_pct"], 8.0),
        "arm +3%": (3.0, rule["stop_pct"]),
    }[exit_style]
    out = []
    for hour in events.signals(drop, lookback, climax, turn):
        entry = int(events.act[hour])
        exit_at, price, why = w.resolve(entry, arm, rule["giveback_pct"], stop, None)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": "capitulation", "why": why})
    return out


def name_of(key):
    drop, lookback, climax, turn, exit_style = key
    return (f"-{drop:g}% under the {lookback}h high, "
            f"{'no volume test' if climax is None else f'selling {climax:g}x'}, {turn}, {exit_style}")


def main() -> None:
    raw, bullish = bv.setup()
    rule = live.load_rule(bp.COIN)
    core = bp.dip_trades(raw, rule)
    events = sc.Events(raw)
    pd.set_option("display.width", 275)

    base = vf.score("BTC as deployed, 3 x $100", core, [(3, CORE)])
    controls = {"base": base}
    for n in (4, 5, 6):
        controls[f"{n} shared"] = vf.score(f"{n} x $100 shared (control)", core, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger {n}"] = vf.score(f"3 x ${n * 100 / 3:.0f} (control)", core, [(3, CORE)])
        w.LOT = 100.0
    print("=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    keys = [(d, lb, c, t, e) for d in DROPS for lb in LOOKBACKS for c in CLIMAX for t in TURNS for e in EXITS]
    sets = {key: build(events, rule, *key) for key in keys}
    sets = {k: v for k, v in sets.items() if v}
    counts = pd.Series({k: len(v) for k, v in sets.items()})
    print(f"\n{len(sets)} capitulation rules that fire; signals per rule: median {counts.median():.0f}, "
          f"range {counts.min()}-{counts.max()}")

    print("\n=== 1. capitulation ALONE, on its own money (2 x $100) - best 8")
    rows = [vf.score(name_of(k), v, [(2, CAP)]) for k, v in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(8).to_string())
    print(f"  rules that made money alone: {int((frame.profit > 0).sum())}/{len(frame)}")

    print("\n=== 2. SHARED: capitulation competes for BTC's 3 deployed lots (best 8)")
    rows = [base] + [vf.score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE | CAP)])
                     for k, v in sets.items()]
    frame2 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame2.set_index("setup").head(8).to_string())
    print(f"  beating no capitulation: {int((frame2.walk_forward > base['walk_forward']).sum())}/{len(frame2) - 1}"
          f" on walk-forward, {int((frame2.profit > base['profit']).sum())}/{len(frame2) - 1} on the full window, "
          f"{int((frame2.unseen > base['unseen']).sum())}/{len(frame2) - 1} on the unseen holdout")

    print("\n=== 3. SEPARATE: the dip carries on, capitulation holds lots of its own")
    for size in SIZES:
        more, bigger = controls[f"{3 + size} shared"], controls[f"3 bigger {3 + size}"]
        rows3 = [vf.score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE), (size, CAP)])
                 for k, v in sets.items()]
        part = pd.DataFrame(rows3).sort_values("walk_forward", ascending=False)
        print(f"\n  --- own {size} (${(3 + size) * 100}) against {3 + size} shared lots "
              f"(+${more['walk_forward']:.2f}) and 3 bigger lots (+${bigger['walk_forward']:.2f})")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating more lots: {int((part.walk_forward > more['walk_forward']).sum())}/{len(part)}; "
              f"beating bigger lots: {int((part.walk_forward > bigger['walk_forward']).sum())}/{len(part)}")

    print("\n=== 4. the honest test: the rule is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    books = {k: sorted(core + v, key=lambda t: t["entry"]) for k, v in sets.items()}
    for label, pots, control_pots, control_lot in (
            ("shared, 3 lots", [(3, CORE | CAP)], [(3, CORE)], 100.0),
            ("own 2 vs more lots", [(3, CORE), (2, CAP)], [(5, CORE)], 100.0),
            ("own 2 vs bigger lots", [(3, CORE), (2, CAP)], [(3, CORE)], 500 / 3)):
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
