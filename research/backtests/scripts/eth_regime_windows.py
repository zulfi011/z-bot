"""Per-window contribution: regime sleeve (1 lot, pure) vs a 3rd pullback lot, each over the planned book."""
from __future__ import annotations
import pandas as pd
import run_eth_full_research as research, run_sol_stage3_space_grid as grid
import eth_pullback as pb, eth_regime as rg

raw, bullish, ema, mode_c = pb.setup()
core = pb.build(raw, bullish, ema, mode_c)
pull = [t for t in pb.build(raw, bullish, ema, [], pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES))
        if t[3] == "pullback"]
reg, _ = rg.regime_trades(bullish)
key = lambda t: (t[0], rg.PRIORITY[t[3]])
plan = sorted(core + pull, key=key)
withreg = sorted(core + pull + reg, key=key)
base = [(5, rg.CORE), (2, rg.PULL)]
rows = []
for i, w in enumerate(rg.TESTS):
    p = rg.simulate(plan, base, *research.WINDOWS[w])["profit"]
    r = rg.simulate(withreg, base + [(1, rg.REG)], *research.WINDOWS[w])["profit"] - p
    q = rg.simulate(plan, [(5, rg.CORE), (3, rg.PULL)], *research.WINDOWS[w])["profit"] - p
    rows.append({"window": research.TESTS[i][0], "regime 1 lot added": round(r, 2), "3rd pullback lot added": round(q, 2)})
f = pd.DataFrame(rows)
print(f.to_string(index=False))
print(f"\ntotals: regime {f.iloc[:,1].sum():.2f} (positive {int((f.iloc[:,1]>0).sum())}/6), "
      f"3rd pullback lot {f.iloc[:,2].sum():.2f} (positive {int((f.iloc[:,2]>0).sum())}/6)")
