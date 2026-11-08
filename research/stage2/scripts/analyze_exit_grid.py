"""Screen one coin's full exit grid. Usage: analyze_exit_grid.py trx"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid

WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
KEY = ["style", "value", "arm_pct", "stop_pct"]
COLS = ["style", "value", "arm_pct", "stop_pct", "full_trades", "win_rate", "avg_win", "avg_loss",
        "full_profit", "usdt", "earlier_profit", "later_profit", "unseen_profit", "wf_profit", "wf_wins", "full_dd"]


def main() -> None:
    coin = (sys.argv[1] if len(sys.argv) > 1 else "trx").lower()
    rule = live.load_rule(coin)
    board = pd.read_parquet(grid.ROOT / "results" / f"{coin}_ema_exit_grid.parquet")
    board["wf_profit"] = board[[f"{w}_profit" for w in WF]].sum(axis=1)
    board["wf_wins"] = sum((board[f"{w}_profit"] > 0).astype(int) for w in WF)
    board["win_rate"] = board.full_wins / board.full_trades.replace(0, np.nan) * 100
    board["avg_win"] = board.full_gross_win / board.full_wins.replace(0, np.nan)
    board["avg_loss"] = -board.full_gross_loss / (board.full_trades - board.full_wins).replace(0, np.nan)
    bnb, usdt = board[board.fees == "BNB"].copy(), board[board.fees == "USDT"].copy()
    bnb["usdt"] = usdt.set_index(KEY).full_profit.reindex(pd.MultiIndex.from_frame(bnb[KEY])).to_numpy()
    pd.set_option("display.width", 250)

    deployed = bnb[(bnb["style"] == "giveback") & (bnb.value == rule["giveback_pct"])
                   & np.isclose(bnb.arm_pct, rule["activation_pct"]) & (bnb.stop_pct == rule["stop_pct"])]
    print(f"=== {coin.upper()} deployed rule: give back {rule['giveback_pct']:g}%, "
          f"arm +{rule['activation_pct']}%, stop -{rule['stop_pct']:g}%")
    print(deployed[COLS].round(2).to_string(index=False))
    base = float(deployed.full_profit.iloc[0]) if len(deployed) else float("nan")

    keep = ((bnb.full_profit > 0) & (bnb.earlier_profit > 0) & (bnb.later_profit > 0) & (bnb.unseen_profit >= 0)
            & (bnb.wf_profit > 0) & (bnb.wf_wins >= 4) & (bnb.usdt > 0))
    print(f"\n{len(bnb):,} combinations; {int(keep.sum()):,} pass every test; "
          f"{int((keep & (bnb.full_profit > base)).sum()):,} of those also beat the deployed rule")

    print("\n=== best 15 that pass everything, by profit")
    print(bnb[keep].sort_values("full_profit", ascending=False)[COLS].head(15).round(2).to_string(index=False))

    print("\n=== best retune with NO engine change (giveback style only)")
    g = bnb[(bnb["style"] == "giveback") & keep]
    print(g.sort_values("full_profit", ascending=False)[COLS].head(10).round(2).to_string(index=False))

    print("\n=== median profit by EMA length (hours)")
    for style in ("ema_always", "ema_uptrend"):
        part = bnb[bnb["style"] == style].copy()
        part["hours"] = part.value / 60
        summary = part.groupby("hours").agg(median=("full_profit", "median"), best=("full_profit", "max"),
                                            median_later=("later_profit", "median"),
                                            median_unseen=("unseen_profit", "median"))
        print(f"-- {style}")
        print(summary.round(1).to_string())

    print("\n=== median profit by arm point and stop (all styles)")
    print(bnb.pivot_table(index="arm_pct", columns="stop_pct", values="full_profit", aggfunc="median").round(1).to_string())


if __name__ == "__main__":
    main()
