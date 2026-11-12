"""Which coins to put in the shared pot: all 31 combinations of ETH/TRX/BTC/AAVE/SOL.

Pot: $300 start, 3 x $100, +1 lot per new $100 up to 5, then +$20 per lot per new $100 (the chosen plan),
first come first served, last buy takes what is left. Also run with 5 x $100 fixed (no lot increase) so the
answer does not depend on compounding. Tests: full history, 12/6-month starts, choose-one-year/test-the-other,
10+10 bps costs.
"""

from __future__ import annotations

import itertools
import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compounding_full_analysis as ca  # noqa: E402
from compounding_full_analysis import Policy, T, replay  # noqa: E402

OUT = ca.OUT / "coin_sets"
PLANS = {"plan": Policy("N5 +$20", "step", 300.0, 5, 20.0), "fixed5": Policy("N5 +$0", "step", 300.0, 5, 0.0)}
HALVES = {"earlier": (T("2024-10-01"), T("2025-09-01")), "later": (T("2025-09-01"), ca.END)}
M, C = None, None


def init():
    global M, C
    M, C = ca.load()


def job(args):
    coins, plan, start, end, fee, slip, tag = args
    sub = [c for c in C if c.coin in coins]
    s = replay(M, sub, PLANS[plan], start, end, fee=fee, slip=slip)
    return {"coins": "+".join(coins), "k": len(coins), "plan": plan, "tag": tag, "start": start.date(),
            **{k: s[k] for k in ("profit", "dd_usd", "dd_pct", "profit_per_dd", "trades", "win_pct",
                                 "avg_open_value", "worst_month_pct")}}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sets = [c for k in range(1, 6) for c in itertools.combinations(ca.COINS, k)]
    tasks = []
    for coins in sets:
        for plan in PLANS:
            tasks.append((coins, plan, ca.START, ca.END, 7.5, 2.0, "full"))
            tasks.append((coins, plan, ca.START, ca.END, 10.0, 10.0, "stress"))
            for name, (a, b) in HALVES.items():
                tasks.append((coins, plan, a, b, 7.5, 2.0, name))
            for s in pd.date_range(ca.START, T("2025-09-01"), freq="MS"):
                tasks.append((coins, plan, s, min(s + pd.DateOffset(months=12), ca.END), 7.5, 2.0, "r12"))
            for s in pd.date_range(ca.START, T("2026-03-01"), freq="MS"):
                tasks.append((coins, plan, s, s + pd.DateOffset(months=6), 7.5, 2.0, "r6"))
    print(len(sets), "sets,", len(tasks), "replays", flush=True)
    with Pool(8, initializer=init) as pool:
        rows = pool.map(job, tasks, chunksize=8)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "all_runs.csv", index=False)

    pd.set_option("display.width", 260)
    pd.set_option("display.max_rows", 200)
    all5 = "+".join(ca.COINS)
    for plan in PLANS:
        d = df[df.plan == plan]
        full = d[d.tag == "full"].set_index("coins")
        t = full[["k", "profit", "dd_usd", "dd_pct", "profit_per_dd", "trades", "win_pct"]].copy()
        t["stress_profit"] = d[d.tag == "stress"].set_index("coins").profit
        for tag in ("r12", "r6"):
            piv = d[d.tag == tag].pivot(index="start", columns="coins", values="profit")
            dd = d[d.tag == tag].pivot(index="start", columns="coins", values="dd_usd")
            t[f"{tag}_median"] = piv.median()
            t[f"{tag}_worst"] = piv.min()
            t[f"{tag}_losing"] = (piv < 0).sum()
            t[f"{tag}_beats_all5"] = (piv.sub(piv[all5], axis=0) > 1e-9).sum()
            t[f"{tag}_med_per_dd"] = (piv / dd.abs()).median()
        t["earlier"] = d[d.tag == "earlier"].set_index("coins").profit
        t["later"] = d[d.tag == "later"].set_index("coins").profit
        t["earlier_dd"] = d[d.tag == "earlier"].set_index("coins").dd_usd
        t["later_dd"] = d[d.tag == "later"].set_index("coins").dd_usd
        t.to_csv(OUT / f"summary_{plan}.csv")
        print(f"\n===== {PLANS[plan].name}: all sets by full-history profit")
        print(t.sort_values("profit", ascending=False).round(2).to_string())

        print(f"\n-- honest selection ({plan}): choose set on one year, test on the other")
        rows = []
        for pick, test in (("earlier", "later"), ("later", "earlier")):
            for by in ("profit", "per_dd"):
                score = t[pick] if by == "profit" else t[pick] / t[f"{pick}_dd"].abs()
                chosen = score.idxmax()
                rows.append({"choose_on": pick, "by": by, "chosen": chosen, "test_profit": t.loc[chosen, test],
                             "test_dd": t.loc[chosen, f"{test}_dd"], "all5_test": t.loc[all5, test],
                             "all5_test_dd": t.loc[all5, f"{test}_dd"],
                             "rank": int((t[test] > t.loc[chosen, test]).sum()) + 1, "of": len(t)})
        print(pd.DataFrame(rows).round(2).to_string(index=False))

        print(f"\n-- leave-one-out vs all five ({plan})")
        loo = []
        for coin in ca.COINS:
            rest = "+".join(c for c in ca.COINS if c != coin)
            loo.append({"drop": coin, "profit_change": t.loc[rest, "profit"] - t.loc[all5, "profit"],
                        "dd_change": t.loc[rest, "dd_usd"] - t.loc[all5, "dd_usd"],
                        "r12_median_change": t.loc[rest, "r12_median"] - t.loc[all5, "r12_median"],
                        "r6_median_change": t.loc[rest, "r6_median"] - t.loc[all5, "r6_median"],
                        "stress_change": t.loc[rest, "stress_profit"] - t.loc[all5, "stress_profit"],
                        "earlier_change": t.loc[rest, "earlier"] - t.loc[all5, "earlier"],
                        "later_change": t.loc[rest, "later"] - t.loc[all5, "later"]})
        print(pd.DataFrame(loo).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
