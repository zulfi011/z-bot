"""Why does pyramiding fire so rarely? Count candidates, skips, and how often ETH trends with nothing open."""
from __future__ import annotations
import numpy as np, pandas as pd
import run_eth_full_research as research, run_sol_stage3_space_grid as grid
import eth_pyramid as py

raw, bullish, ema = py.setup()
parents = py.base_trades(raw, bullish, ema)
start, end = research.WINDOWS["full"]

# which parents the deployed system actually takes, and when they are open
led = py.account(parents, start, end)["ledger"]
taken = set(led.entry)
open_minutes = np.zeros(len(grid.CLOSE), np.int16)
for p in parents:
    if p["entry"] in taken and p["exit"] > 0:
        open_minutes[p["entry"]:p["exit"]] += 1
window = (grid.TIMES >= start) & (grid.TIMES < end)

# a "strong uptrend" minute: averages stacked AND price at least 5% above the 16h... use 7d avg proxy: close > ema
up = bullish & (grid.CLOSE > ema) & window
print(f"minutes in the full window:                 {window.sum():,}")
print(f"uptrend minutes (7d>15d>30d, above 16h EMA): {up.sum():,}  ({100*up.sum()/window.sum():.1f}%)")
for n in range(4):
    share = ((open_minutes == n) & up).sum() / up.sum() * 100
    print(f"   ...with {n} lots open: {share:5.1f}%")

# gains the taken parents reached
peaks = []
for p in parents:
    if p["entry"] in taken and p["exit"] > 0:
        fill = grid.OPEN[p["entry"]] * (1 + grid.SLIP)
        peaks.append(100 * (grid.CLOSE[p["entry"]:p["exit"] + 1].max() / fill - 1))
peaks = pd.Series(peaks)
print(f"\ntaken lots: {len(peaks)}; best close they reached above their fill:")
for x in (2, 3, 4, 6):
    print(f"   reached +{x}% : {(peaks >= x).sum():3d} lots ({100*(peaks >= x).mean():4.1f}%)")

print("\ncandidate adds vs taken, 'all lots, own exit':")
for step in py.STEPS:
    adds = py.adds_for(parents, bullish, ema, step, "own exit", "all")
    inside = [a for a in adds if start <= grid.TIMES[a["entry"]] < end]
    real = py.account(parents + adds, start, end)["ledger"]
    print(f"   +{step:g}%: {len(inside):3d} candidates (parents incl. skipped ones), {int((real.source=='pyramid').sum()):3d} taken")
