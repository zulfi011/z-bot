"""Does an ATR-scaled stop (and trail arm) beat BTC's flat percentages?

BTC risks a flat -3% on every lot and arms its trail at +1.257%, however violent the week is. ATR measures how
far BTC actually travels in a normal day, so the same -3% is a long way down in a calm week and ordinary noise
in a wild one. This matters more here than on the other coins, because BTC's recheck showed that a WIDER stop
(-4% to -6%) removes the loss on the unseen window - the question is whether volatility scaling is the right way
to get there.

Every combination:
  period   ATR over 7, 14 or 21 days (completed UTC days only, effective the next day)
  stop     0.5 / 0.75 / 1 / 1.25 / 1.5 / 2 / 3 x ATR, or left flat
  arm      0.2 / 0.3 / 0.4 / 0.5 / 0.75 x ATR, or left flat
  lots     SHARED - the 3 deployed lots switch to the ATR rule
           SEPARATE - the 3 core lots keep the flat rule and an ATR sleeve of 1-2 lots takes the same signals

Judged against both controls at the same money - more shared lots and 3 bigger lots - with the corrected window
engine, hourly mark-to-market drawdown and walk-forward selection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import eth_regime as rg
import btc_pullback as bp
import sol_atr_stop as sa
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE, ATR = {"dip"}, {"atr dip"}
PERIODS = [7, 14, 21]
STOPS = [None, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]
ARMS = [None, 0.2, 0.3, 0.4, 0.5, 0.75]


def build(entries, rule, atr=None, stop_k=None, arm_m=None, tag=""):
    out = []
    for entry in entries:
        entry = int(entry)
        stop, arm = rule["stop_pct"], rule["activation_pct"]
        if atr is not None and np.isfinite(atr[entry]):
            stop = stop if stop_k is None else stop_k * atr[entry]
            arm = arm if arm_m is None else arm_m * atr[entry]
        exit_at, price, why = w.resolve(entry, arm, rule["giveback_pct"], stop, None)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": f"{tag}dip", "why": why})
    return out


def name_of(key):
    period, stop_k, arm_m = key
    return (f"ATR{period} {'flat stop' if stop_k is None else f'stop {stop_k:g}xATR'}, "
            f"{'flat arm' if arm_m is None else f'arm {arm_m:g}xATR'}")


def main() -> None:
    raw, bullish = bp.setup()
    rule = live.load_rule(bp.COIN)
    entries = [t["entry"] for t in bp.dip_trades(raw, rule)]
    atrs = {period: sa.atr_percent(raw, period) for period in PERIODS}
    flat = build(entries, rule)
    pd.set_option("display.width", 265)

    window = (grid.TIMES >= research.WINDOWS["full"][0]) & (grid.TIMES < research.WINDOWS["full"][1])
    series = pd.Series(atrs[14][window]).dropna()
    print("=== BTC daily ATR(14) as a % of price, over the full window")
    print(series.describe(percentiles=[.1, .25, .5, .75, .9]).round(2).to_string())
    print(f"The flat -{rule['stop_pct']:g}% stop is {rule['stop_pct'] / series.median():.2f}x the median ATR, "
          f"{rule['stop_pct'] / series.quantile(.9):.2f}x on the calmest days and "
          f"{rule['stop_pct'] / series.quantile(.1):.2f}x on the wildest.")

    base = vf.score("BTC as deployed, 3 x $100", flat, [(3, CORE)])
    controls = {"base": base}
    for n in (4, 5):
        controls[f"{n} shared"] = vf.score(f"{n} x $100 shared (control)", flat, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger {n}"] = vf.score(f"3 x ${n * 100 / 3:.0f} (control)", flat, [(3, CORE)])
        w.LOT = 100.0
    print("\n=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    keys = [(p, s, a) for p in PERIODS for s in STOPS for a in ARMS if not (s is None and a is None)]
    sets = {key: build(entries, rule, atrs[key[0]], key[1], key[2]) for key in keys}

    print(f"\n=== 1. SHARED: all {len(sets)} ATR rules replacing the flat one (best 10 by walk-forward)")
    rows = [vf.score(name_of(k), v, [(3, CORE)]) for k, v in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  beating the flat rule: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame)} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame)} on the full window, "
          f"{int((frame.unseen > base['unseen']).sum())}/{len(frame)} on the unseen holdout, "
          f"{int((frame['mtm_dd%'] > base['mtm_dd%']).sum())}/{len(frame)} on drawdown")

    print("\n=== 2. the shape: walk-forward by stop and arm (ATR14)")
    print(pd.DataFrame({("flat arm" if a is None else f"{a:g}xATR"):
                        {("flat stop" if s is None else f"{s:g}xATR"):
                         vf.score("x", sets[(14, s, a)], [(3, CORE)])["walk_forward"]
                         for s in STOPS if not (s is None and a is None)} for a in ARMS}).round(2).to_string())

    print("\n=== 3. SEPARATE: the core keeps the flat rule, an ATR sleeve takes the same signals")
    for size in (1, 2):
        more, bigger = controls[f"{3 + size} shared"], controls[f"3 bigger {3 + size}"]
        rows3 = []
        for key in sets:
            sleeve = build(entries, rule, atrs[key[0]], key[1], key[2], tag="atr ")
            rows3.append(vf.score(name_of(key), sorted(flat + sleeve, key=lambda t: t["entry"]),
                                  [(3, CORE), (size, ATR)]))
        part = pd.DataFrame(rows3).sort_values("walk_forward", ascending=False)
        print(f"\n  --- sleeve of {size} (${(3 + size) * 100}) against {3 + size} shared lots "
              f"(+${more['walk_forward']:.2f}) and 3 bigger lots (+${bigger['walk_forward']:.2f})")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating more lots: {int((part.walk_forward > more['walk_forward']).sum())}/{len(part)}; "
              f"beating bigger lots: {int((part.walk_forward > bigger['walk_forward']).sum())}/{len(part)}")

    print("\n=== 4. the honest test: the ATR rule is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    sleeve_books = {k: sorted(flat + build(entries, rule, atrs[k[0]], k[1], k[2], tag="atr "),
                              key=lambda t: t["entry"]) for k in sets}
    for label, books, pots, control_pots, control_lot in (
            ("shared, 3 lots", sets, [(3, CORE)], [(3, CORE)], 100.0),
            ("sleeve of 1 vs bigger lots", sleeve_books, [(3, CORE), (1, ATR)], [(3, CORE)], 400 / 3),
            ("sleeve of 2 vs bigger lots", sleeve_books, [(3, CORE), (2, ATR)], [(3, CORE)], 500 / 3)):
        w.LOT = control_lot
        control_w = {x: simulate(flat, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
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
