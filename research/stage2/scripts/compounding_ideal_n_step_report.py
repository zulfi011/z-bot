"""Read all_runs.csv from compounding_ideal_n_step and print the decision tables."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compounding_full_analysis as ca  # noqa: E402

OUT = ca.OUT / (sys.argv[1] if len(sys.argv) > 1 else "ideal_n_step")


def table(df):
    full = df[df.tag == "full"].set_index("plan")
    stress = df[df.tag == "stress"].set_index("plan")
    out = full[["n", "inc", "profit", "dd_usd", "dd_pct", "profit_per_dd", "max_order"]].copy()
    out["stress_profit"] = stress.profit
    out["stress_per_dd"] = stress.profit_per_dd
    for tag in ("r12", "r6"):
        sub = df[df.tag == tag]
        piv = sub.pivot(index="start", columns="plan", values="profit")
        dd = sub.pivot(index="start", columns="plan", values="dd_usd")
        out[f"{tag}_median"] = piv.median()
        out[f"{tag}_worst"] = piv.min()
        out[f"{tag}_beats_live"] = (piv.sub(piv["LIVE"], axis=0) > 1e-9).sum()
        out[f"{tag}_median_per_dd"] = (piv / dd.abs()).median()
        out[f"{tag}_worst_dd"] = dd.min()
    for half in ("earlier", "later"):
        out[half] = df[df.tag == half].set_index("plan").profit
    return out


def main():
    df = pd.read_csv(OUT / "all_runs.csv")
    t = table(df)
    pd.set_option("display.width", 280)
    pd.set_option("display.max_rows", 200)
    cols = ["profit", "dd_usd", "dd_pct", "profit_per_dd", "stress_profit", "r12_median", "r12_worst",
            "r12_beats_live", "r12_median_per_dd", "r6_median", "r6_beats_live", "r6_median_per_dd", "r12_worst_dd"]

    print("=== STEP 1: how many lots? (no lot increase, lots stay $100)")
    step1 = t[(t.inc == 0) | (t.index == "LIVE")].sort_values("n")
    print(step1[cols].round(2).to_string())
    print("\nextra profit and extra drawdown for each added lot:")
    s = step1[step1.n > 0].set_index("n")
    print(pd.DataFrame({"extra_profit": s.profit.diff(), "extra_dd": s.dd_usd.diff(),
                        "extra_r12_median": s.r12_median.diff(), "extra_r6_median": s.r6_median.diff()})
          .round(2).to_string())

    print("\n=== STEP 2: lot increase after N (per $100 milestone)")
    for n in range(3, 13):
        sub = t[t.n == n].sort_values("inc")
        print(f"\n-- N = {n}")
        print(sub[["inc"] + cols].round(2).to_string())

    print("\n=== TOP 15 by full-history profit / drawdown")
    print(t.sort_values("profit_per_dd", ascending=False)[cols].head(15).round(2).to_string())
    print("\n=== TOP 15 by median 12-month profit / drawdown")
    print(t.sort_values("r12_median_per_dd", ascending=False)[cols].head(15).round(2).to_string())
    print("\n=== TOP 15 by median 12-month profit")
    print(t.sort_values("r12_median", ascending=False)[cols].head(15).round(2).to_string())

    print("\n=== HONEST SELECTION: choose on one year, test on the other (fresh $300 each)")
    halves = {h: df[df.tag == h].set_index("plan") for h in ("earlier", "later")}
    rows = []
    for pick, test in (("earlier", "later"), ("later", "earlier")):
        for by in ("profit", "profit_per_dd"):
            chosen = halves[pick][by].idxmax()
            tp = halves[test]
            rows.append({"choose_on": pick, "by": by, "chosen": chosen, "test_profit": tp.loc[chosen, "profit"],
                         "test_dd": tp.loc[chosen, "dd_usd"], "live_test_profit": tp.loc["LIVE", "profit"],
                         "live_test_dd": tp.loc["LIVE", "dd_usd"], "oracle": tp.profit.max(),
                         "rank": int((tp.profit > tp.loc[chosen, "profit"]).sum()) + 1, "of": len(tp)})
    print(pd.DataFrame(rows).round(2).to_string(index=False))
    t.to_csv(OUT / "summary.csv")


if __name__ == "__main__":
    main()
