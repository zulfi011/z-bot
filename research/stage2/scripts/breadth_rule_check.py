"""Out-of-sample check of ONE breadth rule found on ETH, fixed before looking at any other coin.

Rule (pre-registered 24 Oct 2026, no threshold search): skip a buy when more than 90% of the 40 breadth coins
closed above their 15-day average (eth_breadth.py, usable from 00:05 UTC the next day).

Applied unchanged to SOL, TRX, AAVE and BTC on their own (same money rule as the ETH test: $300, 3 x $100 ->
5 x $100 -> +$20 per lot per $100), and to the five-coin shared pot (5 lots +$20, and the 3 x $100 start used in
the ETH test). ETH is shown for reference only - it is where the rule was found.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compounding_full_analysis as ca  # noqa: E402
from compounding_full_analysis import Policy, T, replay  # noqa: E402
from eth_breadth import attach, build_features  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "results" / "breadth_rule_check_v1"
THRESHOLD = 90.0
PLAN = Policy("3->5 then +$20", "plan", 300.0, 5, 1.0)
QUARTERS = pd.date_range("2024-10-01", "2026-07-01", freq="QS", tz="UTC")


def kept(cands, feats):
    f = attach([c.entry_time for c in cands], feats)
    skip = f.above15.to_numpy() > THRESHOLD
    return [c for c, s in zip(cands, skip) if not s], [c for c, s in zip(cands, skip) if s]


def compare(markets, cands, feats, policy=PLAN, label=""):
    keep, skipped = kept(cands, feats)
    row = {"test": label, "signals": len(cands), "skipped_signals": len(skipped)}
    base, base_led, _ = replay(markets, cands, policy, want_frames=True)
    rule, _, _ = replay(markets, keep, policy, want_frames=True)
    row.update(none_profit=base["profit"], rule_profit=rule["profit"], change=rule["profit"] - base["profit"],
               none_dd=base["dd_usd"], rule_dd=rule["dd_usd"], none_win=base["win_pct"], rule_win=rule["win_pct"])
    ids = {(c.coin, c.entry_time) for c in skipped}
    hit = base_led[[(k, t) in ids for k, t in zip(base_led.coin, base_led.entry_time)]]
    row.update(skipped_trades=len(hit), skipped_win=100 * (hit.pnl > 0).mean() if len(hit) else np.nan,
               skipped_pnl=hit.pnl.sum())
    for fee, slip, tag in ((10, 10, "stress"),):
        b = replay(markets, cands, policy, fee=fee, slip=slip)["profit"]
        r = replay(markets, keep, policy, fee=fee, slip=slip)["profit"]
        row[f"{tag}_change"] = r - b
    for name, (a, b) in {"earlier": (T("2024-10-01"), T("2025-09-01")), "later": (T("2025-09-01"), ca.END)}.items():
        row[f"{name}_change"] = (replay(markets, keep, policy, a, b)["profit"]
                                 - replay(markets, cands, policy, a, b)["profit"])
    q = []
    for start in QUARTERS:
        end = min(start + pd.DateOffset(months=3), ca.END)
        q.append(replay(markets, keep, policy, start, end)["profit"] - replay(markets, cands, policy, start, end)["profit"])
    q = np.array(q)
    row.update(quarters_better=int((q > 1e-9).sum()), quarters_worse=int((q < -1e-9).sum()), quarters=len(q))
    for months, last in ((12, "2025-09-01"), (6, "2026-03-01")):
        d = []
        for start in pd.date_range(ca.START, T(last), freq="MS"):
            end = min(start + pd.DateOffset(months=months), ca.END)
            d.append(replay(markets, keep, policy, start, end)["profit"]
                     - replay(markets, cands, policy, start, end)["profit"])
        d = np.array(d)
        row[f"r{months}_better"] = f"{int((d > 1e-9).sum())}/{len(d)}"
        row[f"r{months}_median"] = float(np.median(d))
    return row, q


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 240)
    markets, cands = ca.load()
    feats = build_features()
    rows, quarters = [], {}
    for coin in ("SOL", "TRX", "AAVE", "BTC", "ETH"):
        row, q = compare(markets, [c for c in cands if c.coin == coin], feats,
                         label=f"{coin} alone" + (" (where it was found)" if coin == "ETH" else ""))
        rows.append(row)
        quarters[coin] = q
    pot = [c for c in cands]
    row, q = compare(markets, pot, feats, PLAN, "5-coin pot, 3->5 +$20")
    rows.append(row)
    quarters["5-coin pot"] = q
    others = [c for c in cands if c.coin != "ETH"]
    row, q = compare(markets, others, feats, PLAN, "4-coin pot without ETH")
    rows.append(row)
    quarters["pot without ETH"] = q
    table = pd.DataFrame(rows)
    print(f"rule: skip a buy when >{THRESHOLD:.0f}% of 40 coins are above their 15-day average\n")
    print(table.round(2).to_string(index=False))
    qt = pd.DataFrame(quarters, index=[d.date() for d in QUARTERS]).round(2)
    print("\nprofit change by quarter (rule minus no rule)")
    print(qt.to_string())
    table.to_csv(OUT / "summary.csv", index=False)
    qt.to_csv(OUT / "quarters.csv")


if __name__ == "__main__":
    main()
