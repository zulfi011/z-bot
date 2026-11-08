"""Unbiased check of ONE futures rule found on SOL, applied unchanged to another coin before that coin's own search.

Rule (fixed 25 Oct 2026 on SOL, no threshold search): skip a buy when the 24-hour average funding rate (last 3
settlements) is in the bottom 20% of its trailing 90 days (eth_futures_filter.py feature `funding_24h_pct` <= 0.2).
Usage: FG_COIN=TRX scripts/low_funding_rule_check.py. Same money rule: $300, 3 x $100 -> 5 x $100 -> +$20 per lot.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import breadth_rule_check as brc  # noqa: E402
import compounding_full_analysis as ca  # noqa: E402
import eth_futures_filter as eff  # noqa: E402

COIN = os.environ.get("FG_COIN", "TRX").upper()
OUT = Path(__file__).resolve().parents[1] / "results" / f"{COIN.lower()}_low_funding_check_v1"
CUTOFF = 0.2


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 240)
    markets, cands = ca.load()
    cs = [c for c in cands if c.coin == COIN]
    feat = eff.attach(cs, eff.build_features(markets[COIN]))
    low = dict(zip((c.candidate_id for c in cs), feat.funding_24h_pct.to_numpy() <= CUTOFF))   # NaN -> False

    def kept(group, _feats):
        keep, skip = [], []
        for c in group:
            (skip if low[c.candidate_id] else keep).append(c)
        return keep, skip

    brc.kept = kept
    row, q = brc.compare(markets, cs, None, label=f"{COIN} alone, SOL's low-funding rule unchanged")
    table = pd.DataFrame([row])
    print("rule: skip a buy when 24h-average funding is in its trailing-90-day bottom 20% (found on SOL)\n")
    print(table.round(2).T.to_string(header=False))
    qt = pd.Series(q, index=[d.date() for d in brc.QUARTERS], name="change").round(2)
    print("\nprofit change by quarter (rule minus no rule)")
    print(qt.to_string())
    table.to_csv(OUT / "summary.csv", index=False)
    qt.to_csv(OUT / "quarters.csv")


if __name__ == "__main__":
    main()
