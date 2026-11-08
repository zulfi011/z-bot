"""Honest tests for compounding_full_analysis: start dates, costs, tie order, selection, per-quarter split."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compounding_full_analysis as ca  # noqa: E402
from compounding_full_analysis import Policy, T, replay  # noqa: E402

MAIN = ["LIVE $300", "PLAN 5 slots +$20", "PLAN 3 slots 100%", "FIXED 5x$100", "CONT 5 slots"]


def rolling(markets, cands, pols, months, last_start):
    rows = []
    for start in pd.date_range(ca.START, last_start, freq="MS"):
        end = min(start + pd.DateOffset(months=months), ca.END)
        for p in pols:
            s = replay(markets, cands, p, start, end)
            rows.append({"start": start.date(), "plan": p.name, "profit": s["profit"], "dd_pct": s["dd_pct"],
                         "dd_usd": s["dd_usd"]})
    return pd.DataFrame(rows)


def summarise_rolling(frame, label):
    piv = frame.pivot(index="start", columns="plan", values="profit")
    out = []
    for plan in piv.columns:
        sub = frame[frame.plan == plan]
        out.append({"test": label, "plan": plan, "starts": len(sub), "median_profit": sub.profit.median(),
                    "worst_profit": sub.profit.min(), "losing_starts": int((sub.profit < 0).sum()),
                    "beats_live": int((piv[plan] > piv["LIVE $300"] + 1e-9).sum()) if plan != "LIVE $300" else None,
                    "median_vs_live": (piv[plan] - piv["LIVE $300"]).median(),
                    "worst_vs_live": (piv[plan] - piv["LIVE $300"]).min(),
                    "worst_dd_pct": sub.dd_pct.min(), "worst_dd_usd": sub.dd_usd.min()})
    return pd.DataFrame(out)


def main():
    markets, cands = ca.load()
    allp = ca.policies()
    pols = [allp[n] for n in MAIN]
    pd.set_option("display.width", 250)
    ca.OUT.mkdir(parents=True, exist_ok=True)

    # 1. full history and quarter-by-quarter split of the SAME continuous account
    full, quarters = [], []
    for p in pols:
        s, led, eq = replay(markets, cands, p, want_frames=True)
        full.append(s)
        q = eq.set_index("timestamp").equity.resample("QS").last()
        prev = pd.concat([pd.Series([p.initial]), q.iloc[:-1]]).to_numpy()
        quarters.append(pd.Series(q.to_numpy() - prev, index=q.index.date, name=p.name))
        led.to_csv(ca.OUT / f"ledger_{p.name.replace(' ', '_').replace('$', '')}.csv", index=False)
    print("\n=== 1. full history Oct 2024 - Sep 10 2026, $300 start")
    print(pd.DataFrame(full).round(2).to_string(index=False))
    qt = pd.concat(quarters, axis=1).round(2)
    print("\n=== 1b. profit by quarter, one continuous account")
    print(qt.to_string())
    print("plan beats live in", int((qt["PLAN 5 slots +$20"] > qt["LIVE $300"]).sum()), "of", len(qt), "quarters")

    # 2. different start dates
    r12 = rolling(markets, cands, pols, 12, T("2025-09-01"))
    r6 = rolling(markets, cands, pols, 6, T("2026-03-01"))
    rs = pd.concat([summarise_rolling(r12, "12-month runs"), summarise_rolling(r6, "6-month runs")])
    print("\n=== 2. start with $300 on every month start")
    print(rs.round(2).to_string(index=False))
    print("\n12-month runs by start:")
    print(r12.pivot(index="start", columns="plan", values="profit").round(2).to_string())

    # 3. costs
    rows = []
    for fee, slip, label in ((7.5, 2, "base 7.5+2 bps"), (10, 5, "10+5 bps"), (10, 10, "10+10 bps"),
                             (15, 10, "15+10 bps")):
        for p in pols:
            s = replay(markets, cands, p, fee=fee, slip=slip)
            rows.append({"costs": label, "plan": p.name, "profit": s["profit"], "dd_pct": s["dd_pct"],
                         "profit_per_dd": s["profit_per_dd"]})
    print("\n=== 3. cost stress (per side)")
    print(pd.DataFrame(rows).pivot(index="plan", columns="costs", values="profit").round(2).to_string())

    # 4. same-minute tie order
    rows = []
    for seed in range(20):
        for p in pols[:2]:
            rows.append({"seed": seed, "plan": p.name, "profit": replay(markets, cands, p, tie_seed=seed)["profit"]})
    tie = pd.DataFrame(rows).pivot(index="seed", columns="plan", values="profit")
    print("\n=== 4. random same-minute order, 20 seeds")
    print(tie.describe().round(2).to_string())
    print("plan beats live in", int((tie["PLAN 5 slots +$20"] > tie["LIVE $300"]).sum()), "/ 20")

    # 5. honest selection: pick the plan on one year, run it fresh on the other year
    grid = [p for n, p in allp.items() if n.startswith("PLAN") and n != "PLAN 5 slots +$20"] + [allp["LIVE $300"]]
    halves = {"earlier": (T("2024-10-01"), T("2025-09-01")), "later": (T("2025-09-01"), ca.END)}
    sel = []
    for pick_on, test_on in (("earlier", "later"), ("later", "earlier")):
        scores = pd.DataFrame([replay(markets, cands, p, *halves[pick_on]) for p in grid])
        test = pd.DataFrame([replay(markets, cands, p, *halves[test_on]) for p in grid]).set_index("plan")
        for metric in ("profit", "profit_per_dd"):
            chosen = scores.sort_values(metric, ascending=False).iloc[0].plan
            sel.append({"pick_on": pick_on, "by": metric, "chosen": chosen,
                        "test_profit": test.loc[chosen, "profit"], "test_dd_pct": test.loc[chosen, "dd_pct"],
                        "live_test_profit": test.loc["LIVE $300", "profit"],
                        "live_test_dd_pct": test.loc["LIVE $300", "dd_pct"],
                        "doc_plan_test_profit": test.loc["PLAN 5 slots 100%", "profit"],
                        "best_possible": test.profit.max(),
                        "rank_of_live": int((test.profit > test.loc["LIVE $300", "profit"]).sum()) + 1,
                        "plans": len(test)})
    print("\n=== 5. choose on one year, test on the other (fresh $300)")
    print(pd.DataFrame(sel).round(2).to_string(index=False))

    # 6. same money-at-work control: live with bigger lots vs plan
    rows = []
    for lot in (100, 120, 140, 160):
        p = Policy(f"LIVE $300 lots ${lot}", "live", 300.0, lot=lot)
        rows.append(replay(markets, cands, p))
    rows.append(replay(markets, cands, allp["PLAN 5 slots +$20"]))
    print("\n=== 6. live with bigger fixed lots (same wallet) vs the plan")
    print(pd.DataFrame(rows)[["plan", "profit", "dd_usd", "dd_pct", "profit_per_dd", "avg_open_value",
                               "worst_month_pct"]].round(2).to_string(index=False))

    # 7. post-selection Aug 1 - Sep 10 2026 inside the continuous account
    rows = []
    for p in pols:
        _, _, eq = replay(markets, cands, p, want_frames=True)
        e = eq.set_index("timestamp").equity
        rows.append({"plan": p.name, "equity_aug1": e[:T("2026-08-01")].iloc[-1], "equity_end": e.iloc[-1],
                     "change": e.iloc[-1] - e[:T("2026-08-01")].iloc[-1]})
    print("\n=== 7. Aug 1 - Sep 10 2026 (post-selection data) inside the continuous account")
    print(pd.DataFrame(rows).round(2).to_string(index=False))

    rs.to_csv(ca.OUT / "rolling_summary.csv", index=False)
    r12.to_csv(ca.OUT / "rolling_12m.csv", index=False)
    r6.to_csv(ca.OUT / "rolling_6m.csv", index=False)
    qt.to_csv(ca.OUT / "quarters.csv")
    pd.DataFrame(sel).to_csv(ca.OUT / "selection.csv", index=False)


if __name__ == "__main__":
    main()
