"""Screen any coin's full consolidation grid: who survives, and which families are robust.

Usage: analyze_consolidation_grid.py trx     (reads results/<coin>_consolidation_full/all_combinations.parquet)
"""

from __future__ import annotations

import sys

import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid

WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
FAMILY = ["chart_minutes", "zone_bars", "zone_pct", "confirm_minutes", "stop_pct"]
KEYS = FAMILY + ["trail_start_pct", "giveback_pct"]
AXES = {"zone_pct": [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0],
        "confirm_minutes": [0, 1, 3, 5, 10, 15, 30, 60],
        "stop_pct": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]}
MIN_TRADES = 30


def main() -> None:
    coin = (sys.argv[1] if len(sys.argv) > 1 else "eth").lower()
    board = pd.read_parquet(grid.ROOT / "results" / f"{coin}_consolidation_full" / "all_combinations.parquet")
    board["wf_profit"] = board[[f"{w}_profit" for w in WF]].sum(axis=1)
    board["wf_wins"] = sum((board[f"{w}_profit"] > 0).astype(int) for w in WF)
    bnb, usdt = board[board.fees == "bnb_7.5bps"].copy(), board[board.fees == "usdt_10bps"].copy()
    key = FAMILY + ["trail_start_pct"]
    bnb["usdt_profit"] = usdt.set_index(key).full_profit.reindex(pd.MultiIndex.from_frame(bnb[key])).to_numpy()
    pd.set_option("display.width", 230, "display.max_columns", 40)
    print(f"{coin.upper()}: {len(bnb):,} settings at each fee level\n")

    checks = [("makes money overall", bnb.full_profit > 0),
              ("+ at least 30 trades", bnb.full_trades >= MIN_TRADES),
              ("+ both halves positive", (bnb.earlier_profit > 0) & (bnb.later_profit > 0)),
              ("+ unseen weeks not negative", bnb.unseen_profit >= 0),
              ("+ walk-forward positive", bnb.wf_profit > 0),
              ("+ 4 of 6 walk-forward windows", bnb.wf_wins >= 4),
              ("+ profitable on USDT fees too", bnb.usdt_profit > 0)]
    keep = pd.Series(True, index=bnb.index)
    for label, extra in checks:
        keep &= extra
        print(f"  {label:<34} {int(keep.sum()):>7,}")
    bnb["passes"] = keep
    print(f"\n{int(keep.sum()):,} survivors")

    fam = bnb.groupby(FAMILY).agg(variants_passing=("passes", "sum"), trades=("full_trades", "median"),
                                  profit=("full_profit", "median"), worst_variant=("full_profit", "min"),
                                  earlier=("earlier_profit", "median"), later=("later_profit", "median"),
                                  unseen=("unseen_profit", "median"), wf=("wf_profit", "median"),
                                  wf_wins=("wf_wins", "median"), dd=("full_dd", "median"))
    solid = fam[fam.variants_passing == 10].copy()
    print(f"{len(fam):,} entry-rule families; {len(solid):,} where all 10 trailing variants pass\n")
    if solid.empty:
        print("no fully robust family. Best families by median walk-forward with at least 6 variants passing:")
        loose = fam[fam.variants_passing >= 6]
        print(loose.sort_values("wf", ascending=False).head(15).round(2).to_string())
        return

    passing = set(solid.index)
    def neighbours(row):
        count = 0
        for axis, values in AXES.items():
            position = values.index(row[FAMILY.index(axis)])
            for shift in (-1, 1):
                if 0 <= position + shift < len(values):
                    probe = list(row); probe[FAMILY.index(axis)] = values[position + shift]
                    count += tuple(probe) in passing
        return count
    solid["neighbours_ok"] = [neighbours(row) for row in solid.index]
    cols = ["trades", "profit", "worst_variant", "earlier", "later", "unseen", "wf", "wf_wins", "dd", "neighbours_ok"]
    print("most robust families (all 10 trailing variants pass, ranked by surviving neighbours then profit):")
    best = solid.sort_values(["neighbours_ok", "profit"], ascending=False)
    print(best[cols].head(25).round(2).to_string())
    best.reset_index().to_csv(grid.ROOT / "results" / f"{coin}_consolidation_families.csv", index=False)

    print("\nwhere the survivors sit:")
    flat = bnb[keep].reset_index()
    for column in KEYS:
        counts = flat[column].value_counts().sort_index()
        print(f"  {column:<16} " + "  ".join(f"{v}:{c}" for v, c in counts.items()))


if __name__ == "__main__":
    main()
