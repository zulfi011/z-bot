"""BTC's exit, re-tuned properly: the stop, the arming level and the giveback chosen together, plus a trend exit.

The one-at-a-time recheck (btc_settings_recheck.py) left two loose ends, both hindsight-only: a wider stop of -4%
to -6% removes the loss on the unseen Aug-Sep 2026 window, and a 50% giveback gave the best walk-forward of
anything tested. Those interact, so they have to be searched together rather than one at a time.

BTC also has no trend exit - it was never tested here, only on TRX (rejected). A lot bought in an uptrend could
be held against an EMA once its trail arms, the way ETH and SOL do, so that is in the grid too.

Every combination:
  stop      -2 / -3 (deployed) / -4 / -5 / -6 / -8%
  arm       +1 / +1.257 (deployed) / +1.5 / +2 / +3%
  exit      "giveback" - give back 10 / 14 (deployed) / 20 / 30 / 50 / 70% of the best profit
            "line 8h / 16h / 24h" - once armed, hold while the close stays above that EMA, either only for lots
            opened in a clean uptrend (as ETH and SOL do) or for every lot
  entries   unchanged: the deployed 5-day dip, which the recheck confirmed

360 rules on 3 x $100. Corrected window engine, hourly mark-to-market drawdown, and the honest gate: choose the
exit on the six months before each window and see whether choosing beats leaving it deployed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import eth_regime as rg
import btc_pullback as bp
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE = {"dip"}
LOTS = [(3, CORE)]
STOPS = [2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
ARMS = [1.0, 1.257, 1.5, 2.0, 3.0]
GIVEBACKS = [10.0, 14.0, 20.0, 30.0, 50.0, 70.0]
LINES = [8, 16, 24]
WHEN = ["in uptrends", "always"]
DEPLOYED = (3.0, 1.257, "giveback", 14.0, None)


def build(entries, bullish, lines, stop, arm, style, giveback, when):
    line = lines.get(style)
    out = []
    for entry in entries:
        entry = int(entry)
        use = line if (line is not None and (when == "always" or bullish[entry])) else None
        exit_at, price, why = w.resolve(entry, arm, giveback, stop, use)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": "dip", "why": why})
    return out


def name_of(key):
    stop, arm, style, giveback, when = key
    tail = f"giveback {giveback:g}%" if style == "giveback" else f"{style} {when}"
    return f"stop -{stop:g}%, arm +{arm:g}%, {tail}"


def main() -> None:
    raw, bullish = bp.setup()
    rule = live.load_rule(bp.COIN)
    entries = [t["entry"] for t in bp.dip_trades(raw, rule)]
    lines = {f"line {h}h": pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy() for h in LINES}
    pd.set_option("display.width", 260)

    keys = [(s, a, "giveback", g, None) for s in STOPS for a in ARMS for g in GIVEBACKS]
    keys += [(s, a, f"line {h}h", 14.0, when) for s in STOPS for a in ARMS for h in LINES for when in WHEN]
    sets = {key: build(entries, bullish, lines, *key) for key in keys}
    base = vf.score("BTC as deployed (stop -3%, arm +1.257%, giveback 14%)", sets[DEPLOYED], LOTS)
    print(f"{len(sets)} exit rules on {len(entries)} deployed dip signals")
    print("\n=== the control")
    print(pd.DataFrame([base]).set_index("setup").to_string())

    rows = [vf.score(name_of(k), v, LOTS) for k, v in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print("\n=== 1. best 12 by walk-forward")
    print(frame.set_index("setup").head(12).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  beating the deployed exit: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame)} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame)} on the full window, "
          f"{int((frame.unseen > base['unseen']).sum())}/{len(frame)} on the unseen holdout, "
          f"{int((frame['mtm_dd%'] > base['mtm_dd%']).sum())}/{len(frame)} on drawdown")

    print("\n=== 2. best 8 by the unseen holdout (BTC's weak spot: the deployed exit loses $17.87 there)")
    print(frame.sort_values("unseen", ascending=False).set_index("setup").head(8).to_string())

    print("\n=== 3. the shape: walk-forward by stop and giveback (arm +1.257%)")
    print(pd.DataFrame({f"give {g:g}%": {f"stop -{s:g}%":
                                         vf.score("x", sets[(s, 1.257, "giveback", g, None)], LOTS)["walk_forward"]
                                         for s in STOPS} for g in GIVEBACKS}).round(2).to_string())

    print("\n=== 4. the trend exit, which BTC has never had (best 6 of the line rules)")
    line_rows = [r for k, r in zip(sets, rows) if k[2] != "giveback"]
    print(pd.DataFrame(line_rows).sort_values("walk_forward", ascending=False).set_index("setup").head(6).to_string())

    print("\n=== 5. the honest test: the whole exit is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    scores = {k: {x: simulate(v, LOTS, *research.WINDOWS[x])["profit"] for x in windows} for k, v in sets.items()}
    for label, pool in (("every rule", list(sets)),
                        ("giveback rules only", [k for k in sets if k[2] == "giveback"]),
                        ("deployed stop and arm, giveback only", [k for k in sets if k[2] == "giveback"
                                                                  and k[0] == 3.0 and k[1] == 1.257])):
        picks = [max(pool, key=lambda k: scores[k][TRAINS[i]]) for i in range(6)]
        chosen = sum(scores[p][t] for p, t in zip(picks, rg.TESTS))
        left = sum(scores[DEPLOYED][t] for t in rg.TESTS)
        best = max(pool, key=lambda k: sum(scores[k][t] for t in rg.TESTS))
        wins = sum(scores[p][t] > scores[DEPLOYED][t] for p, t in zip(picks, rg.TESTS))
        print(f"\n  --- choosing from {label} ({len(pool)} rules)")
        print(f"    chosen each window ${chosen:7.2f} against ${left:7.2f} for leaving it deployed ({wins}/6 better)")
        print(f"    best fixed rule in hindsight {name_of(best)}: ${sum(scores[best][t] for t in rg.TESTS):7.2f}, "
              f"window by window {', '.join(f'{scores[best][t]:+.2f}' for t in rg.TESTS)}")
        print(f"    deployed, window by window: {', '.join(f'{scores[DEPLOYED][t]:+.2f}' for t in rg.TESTS)}")
        print(f"    it picked: {'; '.join(name_of(p) for p in picks)}")


if __name__ == "__main__":
    main()
