"""How much does each extra $100 lot add to ETH's core (dip + Mode C), and how often is the money busy?"""
from __future__ import annotations
import pandas as pd
import run_eth_full_research as research, eth_pullback as pb, eth_sleeves as sl

raw, bullish, ema, mode_c = pb.setup()
core = pb.build(raw, bullish, ema, mode_c)
rows, previous, previous_wf = [], None, None
for lots in range(3, 9):
    r = sl.evaluate(f"core {lots} x $100", core, [(lots, sl.CORE)])
    r["added_by_this_lot"] = round(r["profit"] - previous, 2) if previous is not None else None
    r["added_wf"] = round(r["walk_forward"] - previous_wf, 2) if previous_wf is not None else None
    previous, previous_wf = r["profit"], r["walk_forward"]
    rows.append(r)
pd.set_option("display.width", 300)
cols = ["capital", "core_trades", "profit", "added_by_this_lot", "return%", "walk_forward", "added_wf",
        "wf_windows", "unseen", "drawdown%", "drawdown$", "money_busy%"]
print(pd.DataFrame(rows).set_index("design")[cols].to_string())
