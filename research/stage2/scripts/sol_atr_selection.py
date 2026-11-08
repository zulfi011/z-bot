"""The sharper question for SOL's ATR sleeve: is it better than putting the SAME money in more flat core lots?

sol_atr_stop.py found that replacing SOL's flat stops with ATR-scaled ones fails the honest test outright, but
that running an ATR sleeve of its own lots ALONGSIDE the flat core survived it (+$25 to +$39 across the six
windows). That comparison was against leaving the extra money idle, which is the easy bar. This script asks the
hard one, window by window:

    $400 as flat core 4              vs   flat core 3 + 1 ATR lot
    $500 as flat core 5              vs   flat core 3 + 2 ATR lots

with the ATR rule chosen on the six months before each window and never with hindsight, and with the drawdown
each plan actually put the account through.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import eth_regime as rg
import sol_pullback as sp
import sol_atr_stop as atr_stop
from sol_atr_stop import ATR, FLAT, TRAINS, name_of, simulate, drawdown


def main() -> None:
    raw, bullish, ema = sp.setup()
    rule, dips, breaks = atr_stop.signals(raw)
    atrs = {period: atr_stop.atr_percent(raw, period) for period in atr_stop.PERIODS}
    flat = atr_stop.build(rule, dips, breaks, bullish, ema)
    keys = [(p, s, a, sc) for p in atr_stop.PERIODS for s in atr_stop.STOPS for a in atr_stop.ARMS
            for sc in atr_stop.SCOPES if not (s is None and a is None)]
    sleeves = {key: sorted(flat + atr_stop.build(rule, dips, breaks, bullish, ema, atrs[key[0]], key[1], key[2],
                                                 key[3], tag="atr "), key=lambda t: t["entry"]) for key in keys}
    pd.set_option("display.width", 250)
    windows = (*TRAINS, *rg.TESTS)

    for k in (1, 2):
        pots = [(3, FLAT), (k, ATR)]
        control = [(3 + k, FLAT)]
        money = (3 + k) * 100
        control_w = {w: simulate(flat, control, *research.WINDOWS[w])["profit"] for w in windows}
        scores = {key: {w: simulate(trades, pots, *research.WINDOWS[w])["profit"] for w in windows}
                  for key, trades in sleeves.items()}
        picks = [max(scores, key=lambda key: scores[key][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]

        rows = []
        for i, test in enumerate(rg.TESTS):
            rows.append({"window": research.TESTS[i][0], "chosen on the 6 months before": name_of(picks[i]),
                         "sleeve earned": round(scores[picks[i]][test], 2),
                         f"flat core {3 + k}": round(control_w[test], 2),
                         "difference": round(scores[picks[i]][test] - control_w[test], 2)})
        print(f"\n=== ${money}: flat core 3 + {k} ATR lot(s), chosen honestly, against flat core {3 + k}")
        print(pd.DataFrame(rows).to_string(index=False))
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(sleeves, key=lambda key: sum(scores[key][t] - control_w[t] for t in rg.TESTS))
        print(f"  honest total ${honest:8.2f} ({wins}/6 windows beat simply owning another flat lot)")
        print(f"  best fixed sleeve rule in hindsight: {name_of(best)} "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}")
        print(f"  drawdown over the full window: flat core {3 + k} {drawdown(flat, control, *research.WINDOWS['full'])}%"
              f" | that best sleeve {drawdown(sleeves[best], pots, *research.WINDOWS['full'])}%")
        wf = [scores[best][t] for t in rg.TESTS]
        print(f"  and that best rule window by window: {', '.join(f'{v - control_w[t]:+.2f}' for v, t in zip(wf, rg.TESTS))}")


if __name__ == "__main__":
    main()
