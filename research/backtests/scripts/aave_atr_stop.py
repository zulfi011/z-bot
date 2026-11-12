"""Does an ATR-scaled stop (and trail arm) beat AAVE's flat percentages?

AAVE risks a flat -4% on a dip lot and -3.5% on a Mode C lot, and arms its trail at +1.276%, however violent the
week is. ATR measures how far AAVE actually travels in a normal day, so the same -4% is a long way down in a calm
week and ordinary noise in a wild one.

Every combination:
  period   ATR over 7, 14 or 21 days (completed UTC days only, effective the next day)
  stop     0.5 / 0.75 / 1 / 1.25 / 1.5 / 2 x ATR, or left flat
  arm      0.15 / 0.2 / 0.3 / 0.4 / 0.5 x ATR, or left flat
  scope    which lots are scaled: the dip only, Mode C only, or both
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
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_adaptive_average as ad
import eth_regime as rg
import aave_settings_recheck as a
import sol_atr_stop as sa
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE, ATR = {"dip", "breakout"}, {"atr dip", "atr breakout"}
PERIODS = [7, 14, 21]
STOPS = [None, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
ARMS = [None, 0.15, 0.2, 0.3, 0.4, 0.5]
SCOPES = ["dip", "mode c", "both"]


def signals(raw, frames, rule):
    frame = frames[rule["minutes"]]
    dips = [int(e) for e in ad.entries_for(raw, rule, frame, ad.average_by_bar(raw, frame, 10 * 1440))]
    high, low, open_, close, last_minute = v4.bars_for(raw, a.MODE_C["chart"])
    breaks = v4.entries_for(high, low, close, last_minute, a.MODE_C["bars"], a.MODE_C["zone"], a.MODE_C["wait"],
                            grid.CLOSE, len(raw))
    if rule["blocked"] and len(breaks):
        hours = grid.TIMES[breaks].hour
        breaks = breaks[~((hours >= rule["blocked"][0]) & (hours < rule["blocked"][1]))]
    return dips, [int(e) for e in breaks]


def build(rule, dips, breaks, atr=None, stop_k=None, arm_m=None, scope="both", tag=""):
    out = []
    for entries, source, flat_stop, flat_arm, giveback in (
            (dips, "dip", rule["stop_pct"], rule["activation_pct"], rule["giveback_pct"]),
            (breaks, "breakout", a.MODE_C["stop"], a.MODE_C["arm"], a.MODE_C["giveback"])):
        scaled = atr is not None and scope in ("both", "dip" if source == "dip" else "mode c")
        for entry in entries:
            stop, arm = flat_stop, flat_arm
            if scaled and np.isfinite(atr[entry]):
                stop = flat_stop if stop_k is None else stop_k * atr[entry]
                arm = flat_arm if arm_m is None else arm_m * atr[entry]
            exit_at, price, why = w.resolve(entry, arm, giveback, stop, None)
            out.append({"entry": entry, "exit": exit_at, "price": price, "source": f"{tag}{source}", "why": why})
    return sorted(out, key=lambda t: t["entry"])


def name_of(key):
    period, stop_k, arm_m, scope = key
    return (f"ATR{period} {'flat stop' if stop_k is None else f'stop {stop_k:g}xATR'}, "
            f"{'flat arm' if arm_m is None else f'arm {arm_m:g}xATR'}, {scope}")


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
    dips, breaks = signals(raw, frames, rule)
    atrs = {period: sa.atr_percent(raw, period) for period in PERIODS}
    flat = build(rule, dips, breaks)
    pd.set_option("display.width", 265)

    window = (grid.TIMES >= research.WINDOWS["full"][0]) & (grid.TIMES < research.WINDOWS["full"][1])
    series = pd.Series(atrs[14][window]).dropna()
    print(f"AAVE: {len(dips)} dip signals, {len(breaks)} Mode C signals")
    print("\n=== AAVE daily ATR(14) as a % of price, over the full window")
    print(series.describe(percentiles=[.1, .25, .5, .75, .9]).round(2).to_string())
    print(f"The flat -{rule['stop_pct']:g}% dip stop is {rule['stop_pct'] / series.median():.2f}x the median ATR, "
          f"{rule['stop_pct'] / series.quantile(.9):.2f}x on the calmest days and "
          f"{rule['stop_pct'] / series.quantile(.1):.2f}x on the wildest.")

    base = vf.score("AAVE as deployed, 3 x $100", flat, [(3, CORE)])
    controls = {"base": base}
    for n in (4, 5):
        controls[f"{n} shared"] = vf.score(f"{n} x $100 shared (control)", flat, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger {n}"] = vf.score(f"3 x ${n * 100 / 3:.0f} (control)", flat, [(3, CORE)])
        w.LOT = 100.0
    print("\n=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    keys = [(p, s, arm, sc) for p in PERIODS for s in STOPS for arm in ARMS for sc in SCOPES
            if not (s is None and arm is None)]
    sets = {key: build(rule, dips, breaks, atrs[key[0]], key[1], key[2], key[3]) for key in keys}

    print(f"\n=== 1. SHARED: all {len(sets)} ATR rules replacing the flat one (best 10 by walk-forward)")
    rows = [vf.score(name_of(k), v, [(3, CORE)]) for k, v in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  beating the flat rule: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame)} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame)} on the full window, "
          f"{int((frame['mtm_dd%'] > base['mtm_dd%']).sum())}/{len(frame)} on drawdown")

    print("\n=== 2. the shape: walk-forward by stop and arm (ATR14, both)")
    print(pd.DataFrame({("flat arm" if arm is None else f"{arm:g}xATR"):
                        {("flat stop" if s is None else f"{s:g}xATR"):
                         vf.score("x", sets[(14, s, arm, "both")], [(3, CORE)])["walk_forward"]
                         for s in STOPS if not (s is None and arm is None)} for arm in ARMS}).round(2).to_string())

    print("\n=== 3. SEPARATE: the core keeps the flat rule, an ATR sleeve takes the same signals")
    for size in (1, 2):
        more, bigger = controls[f"{3 + size} shared"], controls[f"3 bigger {3 + size}"]
        rows3 = []
        for key in sets:
            sleeve = build(rule, dips, breaks, atrs[key[0]], key[1], key[2], key[3], tag="atr ")
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
    sleeve_books = {k: sorted(flat + build(rule, dips, breaks, atrs[k[0]], k[1], k[2], k[3], tag="atr "),
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
