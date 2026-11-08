"""SUPERSEDED - its numbers are wrong. Use sol_wide_stop.py instead.

This first pass measured windows with two leaks that both flatter a wide stop: a lot that never hit its stop and
never armed its trail was dropped instead of marked (so the idea's worst outcomes vanished), and a lot was allowed
to run past the end of a window and collect a recovery that happened months later. sol_wide_stop.py marks every
lot and closes it at the window's last price; with that fixed, the honest result turns negative and the idea is
rejected. Kept only so the mistake is on the record.

Was it the ATR, or just a wider stop? The honest test for a plain fixed-percentage sleeve on SOL.

sol_atr_stop.py found that SOL's only ATR result worth a second look was a SLEEVE: the flat core untouched, plus
lots of their own taking the same entries with a much wider stop and a later trail arm. But the winning ATR
setting worked out at roughly a -9% stop and a +1.8% arm, and plain fixed percentages in that region do most of
the same job - so the ATR scaling may be adding nothing at all.

This checks it the only way that counts: a grid of FIXED stop/arm sleeves, chosen on the six months before each
window, scored against simply owning the same money as another flat core lot.
"""

from __future__ import annotations

import pandas as pd

import run_eth_full_research as research
import eth_regime as rg
import sol_pullback as sp
import sol_atr_stop as a
from sol_atr_stop import ATR, FLAT, TRAINS, simulate, drawdown

STOPS = [3.0, 4.0, 6.0, 9.0, 12.0, 15.0]
ARMS = [1.251, 1.8, 2.5, 3.5]


def main() -> None:
    raw, bullish, ema = sp.setup()
    rule, dips, breaks = a.signals(raw)
    flat = a.build(rule, dips, breaks, bullish, ema)
    sleeves = {(stop, arm): sorted(flat + a.build({**rule, "stop_pct": stop, "activation_pct": arm},
                                                  dips, breaks, bullish, ema, tag="atr "),
                                   key=lambda t: t["entry"])
               for stop in STOPS for arm in ARMS}
    pd.set_option("display.width", 240)
    windows = (*TRAINS, *rg.TESTS)

    print("=== every fixed sleeve, full window and walk-forward (sleeve of 2, $500)")
    rows = [a.score("flat core 5 (control)", flat, [(5, FLAT)])]
    rows += [a.score(f"sleeve stop -{s:g}%, arm +{m:g}%", trades, [(3, FLAT), (2, ATR)])
             for (s, m), trades in sleeves.items()]
    print(pd.DataFrame(rows).sort_values("walk_forward", ascending=False).set_index("setup").head(10).to_string())

    for k in (1, 2):
        pots, control = [(3, FLAT), (k, ATR)], [(3 + k, FLAT)]
        control_w = {w: simulate(flat, control, *research.WINDOWS[w])["profit"] for w in windows}
        scores = {key: {w: simulate(trades, pots, *research.WINDOWS[w])["profit"] for w in windows}
                  for key, trades in sleeves.items()}
        picks = [max(scores, key=lambda key: scores[key][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(sleeves, key=lambda key: sum(scores[key][t] - control_w[t] for t in rg.TESTS))
        print(f"\n=== ${(3 + k) * 100}: fixed sleeve of {k}, chosen honestly, against flat core {3 + k}")
        print(f"  honest ${honest:8.2f} ({wins}/6) | picked: "
              f"{', '.join(f'-{s:g}%/+{m:g}%' for s, m in picks)}")
        print(f"  best fixed rule in hindsight -{best[0]:g}%/+{best[1]:g}%: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")
        print(f"  drawdown: flat core {3 + k} {drawdown(flat, control, *research.WINDOWS['full'])}% | "
              f"that sleeve {drawdown(sleeves[best], pots, *research.WINDOWS['full'])}%")


if __name__ == "__main__":
    main()
