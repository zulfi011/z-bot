"""Does knowing what BTC is doing improve TRX?

TRX reads only its own chart. BTC leads the market, so its state is information TRX's price has not used. Two
families of daily gate, built from completed UTC days only and effective the next day:

  BTC regime     close above its own 7 / 15 / 30-day average, averages stacked up or not stacked down,
                 BTC up over the last 1 / 3 / 7 days
  TRX/BTC ratio  the ratio above its own 7 / 15 / 30-day average, or rising today

Every gate is also tried INVERTED, every single gate and every PAIR (both must agree), gating the dip alone,
Mode C alone, or both ways in.

Two ways to use one:
  SHARED    TRX's 3 deployed lots only buy when the gate agrees
  SEPARATE  the 3 core lots carry on and a sleeve of 1-2 lots of their own buys a SECOND lot on the signals the
            gate likes - the gate never removes a trade, it doubles down on one

Because TRX's best use of extra money is a bigger lot on its 3 slots, each sleeve is judged against BOTH
controls at the same money: more shared lots, and 3 bigger lots.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import stage3_replay as replay
import eth_regime as rg
import sol_btc_gates as sg
import sol_wide_stop as w
import trx_modec_lots as ml
import trx_pullback as tp
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE, SLEEVE = {"dip", "breakout"}, {"wide dip", "wide breakout"}
SCOPES = ["dip", "mode c", "both"]


def main() -> None:
    raw, bullish = tp.setup()
    btc = replay.load_raw("BTCUSDT", include_holdout=True)
    btc = btc[btc.open_time < research.T("2026-09-11")].reset_index(drop=True)
    rule = live.load_rule(tp.COIN)
    core = sorted(ml.dip_trades(raw, rule) + ml.break_trades(raw, rule, 40, 2.0, 3, "mode c"),
                  key=lambda t: t["entry"])
    gate = sg.gates(raw, btc)
    pd.set_option("display.width", 265)

    singles = [(name,) for name in gate]
    pairs = [pair for pair in combinations(list(gate), 2)
             if pair[1] != f"NOT {pair[0]}" and pair[0] != f"NOT {pair[1]}"]
    keys = [(names, scope) for names in singles + pairs for scope in SCOPES]
    print(f"TRX: {len(core)} core signals; {len(gate)} gates ({len(singles)} single, {len(pairs)} pairs) "
          f"x {len(SCOPES)} scopes = {len(keys)} rules")

    base = vf.score("TRX as deployed, 3 x $100", core, [(3, CORE)])
    controls = {}
    for n in (4, 5):
        controls[f"{n} shared lots"] = vf.score(f"{n} x $100 shared (control)", core, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger lots (${n}00)"] = vf.score(f"3 x ${n * 100 / 3:.0f} (control)", core, [(3, CORE)])
        w.LOT = 100.0
    print("\n=== the controls")
    print(pd.DataFrame([base, *controls.values()]).set_index("setup").to_string())

    print("\n=== 0. what TRX's lots did under each single gate (deployed 3 lots)")
    led = simulate(core, [(3, CORE)], *research.WINDOWS["full"])["ledger"]
    rows = []
    for name in list(gate):
        if name.startswith("NOT "):
            continue
        flags = np.array([gate[name][e] for e in led.entry])
        for label, part in ((name, led[flags]), (f"NOT {name}", led[~flags])):
            rows.append({"gate": label, "trades": len(part),
                         "win%": round(100 * (part.pnl > 0).mean(), 1) if len(part) else 0.0,
                         "total $": round(part.pnl.sum(), 2) if len(part) else 0.0,
                         "avg $": round(part.pnl.mean(), 3) if len(part) else 0.0})
    print(pd.DataFrame(rows).set_index("gate").to_string())

    shared = {key: sg.subset(core, gate, *key) for key in keys}
    print("\n=== 1. SHARED: the deployed lots only buy when the gate agrees (best 8 by walk-forward)")
    rows = [vf.score(f"{' + '.join(names)} [{scope}]", trades, [(3, CORE)])
            for (names, scope), trades in shared.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(8).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  beating no gate: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame)} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame)} on the full window, "
          f"{int((frame['mtm_dd%'] > base['mtm_dd%']).sum())}/{len(frame)} on drawdown")

    print("\n=== 2. SEPARATE: a gated sleeve doubles the signals the gate likes")
    sleeves = {key: sorted(core + sg.subset(core, gate, *key, tag="wide "), key=lambda t: t["entry"])
               for key in keys}
    for size in (1, 2):
        money = (3 + size) * 100
        more = controls[f"{3 + size} shared lots"]
        bigger = controls[f"3 bigger lots (${3 + size}00)"]
        rows = [vf.score(f"{' + '.join(names)} [{scope}]", book, [(3, CORE), (size, SLEEVE)])
                for (names, scope), book in sleeves.items()]
        part = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
        print(f"\n  --- sleeve of {size} (${money}) against {3 + size} shared lots (+${more['walk_forward']:.2f}) "
              f"and 3 bigger lots (+${bigger['walk_forward']:.2f})")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating more lots: {int((part.walk_forward > more['walk_forward']).sum())}/{len(part)}; "
              f"beating bigger lots: {int((part.walk_forward > bigger['walk_forward']).sum())}/{len(part)}")

    print("\n=== 3. the honest test: the gate is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for label, use, pots, control in (("shared, 3 lots", shared, [(3, CORE)], ("core", [(3, CORE)], 100.0)),
                                      ("sleeve of 1 vs more lots", sleeves, [(3, CORE), (1, SLEEVE)],
                                       ("core", [(4, CORE)], 100.0)),
                                      ("sleeve of 1 vs bigger lots", sleeves, [(3, CORE), (1, SLEEVE)],
                                       ("core", [(3, CORE)], 400 / 3)),
                                      ("sleeve of 2 vs more lots", sleeves, [(3, CORE), (2, SLEEVE)],
                                       ("core", [(5, CORE)], 100.0)),
                                      ("sleeve of 2 vs bigger lots", sleeves, [(3, CORE), (2, SLEEVE)],
                                       ("core", [(3, CORE)], 500 / 3))):
        _, control_pots, control_lot = control
        w.LOT = control_lot
        control_w = {x: simulate(core, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        w.LOT = 100.0
        scores = {k: {x: simulate(v, pots, *research.WINDOWS[x])["profit"] for x in windows} for k, v in use.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(use, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        name = lambda k: f"{' + '.join(k[0])} [{k[1]}]"
        print(f"\n  --- {label}")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    best fixed gate in hindsight {name(best)}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")


if __name__ == "__main__":
    main()
