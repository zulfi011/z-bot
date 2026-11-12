"""Screen the SOL day-trading grid: which intraday rules trade often AND survive every test."""

from __future__ import annotations

import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid

BOARD = grid.ROOT / "results" / "sol_daytrade_v1" / "all_combinations.parquet"
WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
FAMILY = ["chart_minutes", "zone_bars", "zone_pct", "confirm_minutes", "stop_pct"]
AXES = {"zone_pct": [0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0],
        "confirm_minutes": [0, 1, 2, 3, 5, 10, 15],
        "stop_pct": [0.75, 1.0, 1.5, 2.0, 2.5, 3.0]}
MONTHS = 22.0        # Oct 2024 - Aug 2026


def main() -> None:
    board = pd.read_parquet(BOARD)
    board["wf_profit"] = board[[f"{w}_profit" for w in WF]].sum(axis=1)
    board["wf_wins"] = sum((board[f"{w}_profit"] > 0).astype(int) for w in WF)
    board["per_month"] = board.full_trades / MONTHS
    board["capture"] = board.full_trades / board.full_signals.replace(0, pd.NA) * 100
    bnb, usdt = board[board.fees == "bnb_7.5bps"].copy(), board[board.fees == "usdt_10bps"].copy()
    key = FAMILY + ["trail_start_pct"]
    bnb["usdt_profit"] = usdt.set_index(key).full_profit.reindex(pd.MultiIndex.from_frame(bnb[key])).to_numpy()
    pd.set_option("display.width", 240, "display.max_columns", 40)
    print(f"SOL day-trading grid: {len(bnb):,} settings at each fee level")
    print(f"zone spans {int(bnb.zone_span_minutes.min())}-{int(bnb.zone_span_minutes.max())} minutes\n")

    checks = [("makes money overall", bnb.full_profit > 0),
              ("+ trades at least twice a week", bnb.per_month >= 8),
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

    fam = bnb.groupby(FAMILY).agg(variants_passing=("passes", "sum"), signals=("full_signals", "median"),
                                  trades=("full_trades", "median"), per_month=("per_month", "median"),
                                  capture=("capture", "median"), profit=("full_profit", "median"),
                                  worst_variant=("full_profit", "min"), earlier=("earlier_profit", "median"),
                                  later=("later_profit", "median"), unseen=("unseen_profit", "median"),
                                  wf=("wf_profit", "median"), wf_wins=("wf_wins", "median"), dd=("full_dd", "median"))
    solid = fam[fam.variants_passing == 10].copy()
    print(f"{len(fam):,} entry-rule families; {len(solid):,} where all 10 trailing variants pass\n")
    table = solid if not solid.empty else fam[fam.variants_passing >= 7]
    if table.empty:
        print("nothing robust. Best by walk-forward among rules that trade twice a week and make money:")
        loose = bnb[(bnb.full_profit > 0) & (bnb.per_month >= 8)]
        cols = ["zone_span_minutes", "full_signals", "full_trades", "per_month", "full_profit", "earlier_profit",
                "later_profit", "unseen_profit", "wf_profit", "wf_wins", "full_dd"]
        print(loose.sort_values("wf_profit", ascending=False)[FAMILY + cols].head(20).round(2).to_string(index=False))
        return

    passing = set(table.index)
    def neighbours(row):
        count = 0
        for axis, values in AXES.items():
            position = values.index(row[FAMILY.index(axis)])
            for shift in (-1, 1):
                if 0 <= position + shift < len(values):
                    probe = list(row); probe[FAMILY.index(axis)] = values[position + shift]
                    count += tuple(probe) in passing
        return count
    table = table.copy()
    table["neighbours_ok"] = [neighbours(row) for row in table.index]
    cols = ["signals", "trades", "per_month", "capture", "profit", "worst_variant", "earlier", "later", "unseen",
            "wf", "wf_wins", "dd", "neighbours_ok"]
    print("most robust intraday families, by trades per month:")
    print(table.sort_values("per_month", ascending=False)[cols].head(20).round(2).to_string())
    print("\nsame families, by profit:")
    print(table.sort_values("profit", ascending=False)[cols].head(20).round(2).to_string())
    table.reset_index().to_csv(grid.ROOT / "results" / "sol_daytrade_families.csv", index=False)


if __name__ == "__main__":
    main()
