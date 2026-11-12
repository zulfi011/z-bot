"""The honest test: choose the exit settings using ONLY data before each test window, then score them on it.

For each of the six three-month test windows, the settings are picked from the six months immediately before
it and never with any knowledge of the window they are scored on. Several selection rules are compared, plus
the deployed rule (which needs no selection) and the oracle (chosen with full hindsight - not achievable).

Usage: walk_forward_selection.py eth
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid

KEY = ["style", "value", "arm_pct", "stop_pct"]
TESTS = [f"wf{i}_test" for i in range(len(research.TESTS))]
TRAINS = [f"wf{i}_train" for i in range(len(research.TESTS))]
MIN_TRAIN_TRADES = 15


def describe(row):
    kind = row["style"]
    what = f"give back {row.value:g}%" if kind == "giveback" else \
        f"EMA {row.value / 60:g}h" + (" in uptrend" if kind == "ema_uptrend" else "")
    return f"{what}, arm {row.arm_pct:g}%, stop -{row.stop_pct:g}%"


def main() -> None:
    coin = (sys.argv[1] if len(sys.argv) > 1 else "eth").lower()
    rule = live.load_rule(coin)
    board = pd.read_parquet(grid.ROOT / "results" / f"{coin}_ema_exit_grid_wf.parquet")
    board = board[board.fees == "BNB"].reset_index(drop=True)
    for i in range(len(TESTS)):
        for tag in (f"wf{i}_train", f"wf{i}_test"):
            board[f"{tag}_win"] = board[f"{tag}_wins"] / board[f"{tag}_trades"].replace(0, np.nan) * 100
    deployed = board[(board["style"] == "giveback") & (board.value == rule["giveback_pct"])
                     & np.isclose(board.arm_pct, rule["activation_pct"], atol=0.01)
                     & (board.stop_pct == rule["stop_pct"])].iloc[0]

    # a robustness score: the median training profit of a setting's neighbours (same style and stop,
    # one step either side in the EMA length / giveback), so a lone spike cannot win
    board["_group"] = board["style"] + "|" + board.arm_pct.astype(str) + "|" + board.stop_pct.astype(str)
    picks = {name: [] for name in ("max train profit", "max train profit, 75%+ win rate",
                                   "best neighbourhood (robust)", "deployed (no choice made)", "oracle (hindsight)")}
    rows = []
    for i in range(len(TESTS)):
        train, test = f"wf{i}_train", f"wf{i}_test"
        eligible = board[board[f"{train}_trades"] >= MIN_TRAIN_TRADES].copy()
        if eligible.empty:
            eligible = board.copy()
        eligible["neighbour_score"] = eligible.groupby("_group")[f"{train}_profit"].transform("median")
        choices = {
            "max train profit": eligible.loc[eligible[f"{train}_profit"].idxmax()],
            "max train profit, 75%+ win rate": (
                eligible[eligible[f"{train}_win"] >= 75].pipe(
                    lambda f: f.loc[f[f"{train}_profit"].idxmax()] if len(f) else eligible.loc[eligible[f"{train}_profit"].idxmax()])),
            "best neighbourhood (robust)": eligible.loc[eligible["neighbour_score"].idxmax()],
            "deployed (no choice made)": deployed,
            "oracle (hindsight)": board.loc[board[f"{test}_profit"].idxmax()],
        }
        for name, row in choices.items():
            picks[name].append(float(row[f"{test}_profit"]))
        rows.append({"window": f"{research.TESTS[i][0]} to {research.TESTS[i][1]}",
                     "train_trades": int(choices["max train profit"][f"{train}_trades"]),
                     **{name: float(row[f"{test}_profit"]) for name, row in choices.items()}})
        if i == 0:
            print(f"{coin.upper()}: settings chosen per window\n")
        for name in ("max train profit", "max train profit, 75%+ win rate", "best neighbourhood (robust)"):
            print(f"  {research.TESTS[i][0]}  {name:<32s} -> {describe(choices[name])}")
        print()

    frame = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print("=== profit in each test window ($300 as 3 x $100 lots, BNB fees)")
    print(frame.round(2).to_string(index=False))
    totals = {name: sum(values) for name, values in picks.items()}
    wins = {name: sum(v > 0 for v in values) for name, values in picks.items()}
    print("\n=== totals across the six out-of-sample windows")
    summary = pd.DataFrame([{"selection rule": name, "total": totals[name], "windows positive": f"{wins[name]}/6",
                             "vs deployed": totals[name] - totals["deployed (no choice made)"]}
                            for name in picks])
    print(summary.round(2).to_string(index=False))
    frame.to_csv(grid.ROOT / "results" / f"{coin}_walk_forward_selection.csv", index=False)


if __name__ == "__main__":
    main()
