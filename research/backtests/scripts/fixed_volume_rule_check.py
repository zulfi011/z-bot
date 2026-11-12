"""Unbiased check of fixed 4h-trade-count volume rules found on earlier coins, applied unchanged to one coin.

  ETH busy-4h:  skip a buy when trades in the last 4h are MORE than 1.5x the 30-day normal (found on ETH, 24 Oct)
  BTC quiet-4h: skip a buy when trades in the last 4h are LESS than 0.75x the 30-day normal (found on BTC, 25 Oct)
Usage: FG_COIN=AAVE scripts/fixed_volume_rule_check.py. Money rule: $300, 3 x $100 -> 5 x $100 -> +$20 per lot.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import breadth_rule_check as brc  # noqa: E402
import compounding_full_analysis as ca  # noqa: E402
import eth_volume_windows as evw  # noqa: E402

COIN = os.environ.get("FG_COIN", "AAVE").upper()
OUT = Path(__file__).resolve().parents[1] / "results" / f"{COIN.lower()}_fixed_volume_rules_v1"
RULES = {"ETH busy-4h (skip if 4h trades > 1.5x)": lambda r: r > 1.5,
         "BTC quiet-4h (skip if 4h trades < 0.75x)": lambda r: r < 0.75}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 240)
    markets, cands = ca.load()
    cs = [c for c in cands if c.coin == COIN]
    ratio = dict(zip((c.candidate_id for c in cs),
                     evw.attach([c.entry_time for c in cs], evw.build_features())["trades_4h"].to_numpy()))
    rows, quarters = [], {}
    for name, skip_if in RULES.items():
        def kept(group, _feats, skip_if=skip_if):
            keep, skip = [], []
            for c in group:
                (skip if skip_if(ratio[c.candidate_id]) else keep).append(c)   # NaN compares False: kept
            return keep, skip

        brc.kept = kept
        row, q = brc.compare(markets, cs, None, label=f"{COIN}: {name}")
        rows.append(row)
        quarters[name] = q
    table = pd.DataFrame(rows)
    print(table.round(2).set_index("test").T.to_string())
    qt = pd.DataFrame(quarters, index=[d.date() for d in brc.QUARTERS]).round(2)
    print("\nprofit change by quarter (rule minus no rule)")
    print(qt.to_string())
    table.to_csv(OUT / "summary.csv", index=False)
    qt.to_csv(OUT / "quarters.csv")


if __name__ == "__main__":
    main()
