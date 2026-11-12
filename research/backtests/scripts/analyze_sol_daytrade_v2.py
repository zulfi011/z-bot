"""Screen the corrected SOL intraday grid: exits sized to the move, plus a time exit."""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid

WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
FAMILY = ["chart_minutes", "zone_bars", "zone_pct", "confirm_minutes", "arm_pct", "stop_pct", "hold_minutes"]
MONTHS = 22.0


def main() -> None:
    board = pd.read_parquet(grid.ROOT / "results" / "sol_daytrade_v2" / "all_combinations.parquet")
    board["wf_profit"] = board[[f"{w}_profit" for w in WF]].sum(axis=1)
    board["wf_wins"] = sum((board[f"{w}_profit"] > 0).astype(int) for w in WF)
    board["per_month"] = board.full_trades / MONTHS
    board["win_rate"] = board.full_wins / board.full_trades.replace(0, np.nan) * 100
    board["per_trade"] = board.full_profit / board.full_trades.replace(0, np.nan)
    bnb, usdt = board[board.fees == "bnb_7.5bps"].copy(), board[board.fees == "usdt_10bps"].copy()
    key = FAMILY + ["giveback_pct"]
    bnb["usdt_profit"] = usdt.set_index(key).full_profit.reindex(pd.MultiIndex.from_frame(bnb[key])).to_numpy()
    pd.set_option("display.width", 250, "display.max_columns", 40)
    print(f"{len(bnb):,} settings at each fee level\n")

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
    print(f"\n{int(keep.sum()):,} survivors of the day-trading bar")

    # the same bar, but without demanding two trades a week
    relaxed = ((bnb.full_profit > 0) & (bnb.full_trades >= 30) & (bnb.earlier_profit > 0) & (bnb.later_profit > 0)
               & (bnb.unseen_profit >= 0) & (bnb.wf_profit > 0) & (bnb.wf_wins >= 4) & (bnb.usdt_profit > 0))
    print(f"{int(relaxed.sum()):,} survivors if the frequency demand is dropped (still >= 30 trades)")

    cols = ["zone_span_minutes", "full_signals", "full_trades", "per_month", "win_rate", "per_trade",
            "full_profit", "earlier_profit", "later_profit", "unseen_profit", "wf_profit", "wf_wins", "full_dd"]
    show = FAMILY + ["giveback_pct"] + cols
    if keep.any():
        print("\nbest day-trading survivors by profit:")
        print(bnb[keep].sort_values("full_profit", ascending=False)[show].head(20).round(2).to_string(index=False))
    if relaxed.any():
        print("\nbest survivors of the relaxed bar by profit:")
        print(bnb[relaxed].sort_values("full_profit", ascending=False)[show].head(15).round(2).to_string(index=False))

    print("\n=== does sizing the exit to the move help? profit by arm / stop, all settings")
    print(bnb.groupby(["arm_pct", "stop_pct"]).full_profit.median().unstack().round(1).to_string())
    print("\n=== by time exit")
    print(bnb.groupby("hold_minutes").agg(settings=("full_profit", "size"), median_profit=("full_profit", "median"),
        best=("full_profit", "max"), share_profitable=("full_profit", lambda s: round(100 * (s > 0).mean(), 1)),
        median_trades=("full_trades", "median"), win_rate=("win_rate", "median")).round(2).to_string())
    print("\n=== by how often the rule trades")
    bucket = pd.cut(bnb.per_month, [0, 1, 2, 4, 8, 16, 32, 64, 1e9],
                    labels=["<1/mo", "1-2", "2-4", "4-8", "8-16", "16-32", "32-64", "64+/mo"])
    print(bnb.groupby(bucket, observed=True).agg(settings=("full_profit", "size"),
        median_profit=("full_profit", "median"), best=("full_profit", "max"),
        share_profitable=("full_profit", lambda s: round(100 * (s > 0).mean(), 1)),
        per_trade=("per_trade", "median"), win_rate=("win_rate", "median"),
        median_wf=("wf_profit", "median")).round(2).to_string())


if __name__ == "__main__":
    main()
