"""Why intraday consolidation breakouts fail on SOL: frequency vs edge, straight from the grid."""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid

WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
MONTHS = 22.0


def main() -> None:
    board = pd.read_parquet(grid.ROOT / "results" / "sol_daytrade_v1" / "all_combinations.parquet")
    board = board[board.fees == "bnb_7.5bps"].copy()
    board["wf_profit"] = board[[f"{w}_profit" for w in WF]].sum(axis=1)
    board["per_month"] = board.full_trades / MONTHS
    board["win_rate"] = board.full_wins / board.full_trades.replace(0, np.nan) * 100
    board["per_trade_pct"] = board.full_profit / board.full_trades.replace(0, np.nan)   # $ per trade on a $100 lot
    board["stopped_pct"] = board.full_stop / board.full_trades.replace(0, np.nan) * 100
    pd.set_option("display.width", 240, "display.max_columns", 40)

    print("=== profit against how often the rule trades (all 158,880 settings, BNB fees)")
    bucket = pd.cut(board.per_month, [0, 1, 2, 4, 8, 16, 32, 64, 1e9],
                    labels=["<1/mo", "1-2", "2-4", "4-8", "8-16", "16-32", "32-64", "64+/mo"])
    print(board.groupby(bucket, observed=True).agg(settings=("full_profit", "size"),
        median_profit=("full_profit", "median"), best_profit=("full_profit", "max"),
        share_profitable=("full_profit", lambda s: round(100 * (s > 0).mean(), 1)),
        median_per_trade=("per_trade_pct", "median"), win_rate=("win_rate", "median"),
        stopped_out=("stopped_pct", "median"), median_wf=("wf_profit", "median")).round(2).to_string())

    print("\n=== profit against how long the zone is")
    span = pd.cut(board.zone_span_minutes, [0, 30, 60, 120, 240, 480],
                  labels=["<=30 min", "30-60", "1-2 h", "2-4 h", "4-8 h"])
    print(board.groupby(span, observed=True).agg(settings=("full_profit", "size"),
        median_profit=("full_profit", "median"), best_profit=("full_profit", "max"),
        share_profitable=("full_profit", lambda s: round(100 * (s > 0).mean(), 1)),
        median_trades=("full_trades", "median"), median_per_trade=("per_trade_pct", "median"),
        win_rate=("win_rate", "median")).round(2).to_string())

    print("\n=== profit against the zone width")
    print(board.groupby("zone_pct").agg(settings=("full_profit", "size"),
        median_profit=("full_profit", "median"), best_profit=("full_profit", "max"),
        share_profitable=("full_profit", lambda s: round(100 * (s > 0).mean(), 1)),
        median_trades=("full_trades", "median"), median_per_trade=("per_trade_pct", "median"),
        win_rate=("win_rate", "median"), stopped_out=("stopped_pct", "median")).round(2).to_string())

    print("\n=== the money per trade, best 15 settings by profit")
    cols = ["chart_minutes", "zone_span_minutes", "zone_pct", "confirm_minutes", "stop_pct", "giveback_pct",
            "full_trades", "per_month", "win_rate", "per_trade_pct", "stopped_pct", "full_profit", "wf_profit"]
    print(board.sort_values("full_profit", ascending=False)[cols].head(15).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
