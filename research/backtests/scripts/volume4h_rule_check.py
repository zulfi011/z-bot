"""Out-of-sample check of ONE volume rule found on ETH, fixed before looking at any other coin.

Rule (fixed 24 Oct 2026, no threshold search): skip a buy when the number of trades in the 4 hours before it is more
than 1.5x the coin's own 4-hour normal over the prior 30 days (eth_volume_windows.py, minutes before the buy only).
Applied unchanged to SOL, TRX, AAVE and BTC alone ($300, 3 x $100 -> 5 x $100 -> +$20), and to the shared pot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import breadth_rule_check as brc  # noqa: E402
import compounding_full_analysis as ca  # noqa: E402
import eth_volume_windows as evw  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "results" / "volume4h_rule_check_v1"
THRESHOLD = 1.5
SYMBOLS = {"SOL": "SOLUSDT", "TRX": "TRXUSDT", "AAVE": "AAVEUSDT", "BTC": "BTCUSDT", "ETH": "ETHUSDT"}


class Feats:
    """Stands in for breadth features: brc.kept() reads .above15 and compares it with brc.THRESHOLD."""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 240)
    markets, cands = ca.load()
    ratio = {}
    for coin, symbol in SYMBOLS.items():
        evw.SYMBOL = symbol
        f = evw.build_features()
        cs = [c for c in cands if c.coin == coin]
        r = evw.attach([c.entry_time for c in cs], f)["trades_4h"].to_numpy()
        ratio.update({(c.coin, c.entry_time, c.candidate_id): v for c, v in zip(cs, r)})

    def kept(cs, _feats):
        keep, skip = [], []
        for c in cs:
            (skip if ratio[(c.coin, c.entry_time, c.candidate_id)] > THRESHOLD else keep).append(c)
        return keep, skip

    brc.kept = kept
    rows, quarters = [], {}
    for coin in ("SOL", "TRX", "AAVE", "BTC", "ETH"):
        row, q = brc.compare(markets, [c for c in cands if c.coin == coin], None,
                             label=f"{coin} alone" + (" (where it was found)" if coin == "ETH" else ""))
        rows.append(row)
        quarters[coin] = q
    row, q = brc.compare(markets, list(cands), None, brc.PLAN, "5-coin pot, 3->5 +$20")
    rows.append(row)
    quarters["5-coin pot"] = q
    row, q = brc.compare(markets, [c for c in cands if c.coin != "ETH"], None, brc.PLAN, "4-coin pot without ETH")
    rows.append(row)
    quarters["pot without ETH"] = q
    table = pd.DataFrame(rows)
    print(f"rule: skip a buy when trades in the last 4h > {THRESHOLD}x the coin's 30-day normal\n")
    print(table.round(2).to_string(index=False))
    qt = pd.DataFrame(quarters, index=[d.date() for d in brc.QUARTERS]).round(2)
    print("\nprofit change by quarter (rule minus no rule)")
    print(qt.to_string())
    table.to_csv(OUT / "summary.csv", index=False)
    qt.to_csv(OUT / "quarters.csv")


if __name__ == "__main__":
    main()
