"""Screen the full ETH consolidation grid: who survives, and do the survivors cluster?"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid

BOARD = grid.ROOT / "results" / "eth_consolidation_full" / "all_combinations.parquet"
KEYS = ["chart_minutes", "zone_bars", "zone_pct", "confirm_minutes", "stop_pct", "trail_start_pct", "giveback_pct"]
WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
MIN_TRADES = 30


def main() -> None:
    board = pd.read_parquet(BOARD)
    board["wf_profit"] = board[[f"{w}_profit" for w in WF]].sum(axis=1)
    board["wf_wins"] = sum((board[f"{w}_profit"] > 0).astype(int) for w in WF)
    board["win_rate"] = board.full_wins / board.full_trades.replace(0, np.nan) * 100
    pd.set_option("display.width", 220, "display.max_columns", 40)

    print(f"{len(board):,} rows, {len(board) // 2:,} settings at each fee level\n")
    bnb = board[board.fees == "bnb_7.5bps"].set_index(KEYS)
    usdt = board[board.fees == "usdt_10bps"].set_index(KEYS)

    print("how many settings clear each hurdle (BNB fees):")
    steps = {
        "makes money overall": bnb.full_profit > 0,
        "+ at least 30 trades": (bnb.full_profit > 0) & (bnb.full_trades >= MIN_TRADES),
        "+ both halves positive": None, "+ unseen weeks not negative": None,
        "+ walk-forward positive": None, "+ 4 of 6 walk-forward windows": None,
        "+ profitable on USDT fees too": None,
    }
    keep = (bnb.full_profit > 0) & (bnb.full_trades >= MIN_TRADES)
    for label, extra in [("+ both halves positive", (bnb.earlier_profit > 0) & (bnb.later_profit > 0)),
                         ("+ unseen weeks not negative", bnb.unseen_profit >= 0),
                         ("+ walk-forward positive", bnb.wf_profit > 0),
                         ("+ 4 of 6 walk-forward windows", bnb.wf_wins >= 4),
                         ("+ profitable on USDT fees too", usdt.full_profit.reindex(bnb.index) > 0)]:
        keep = keep & extra
        steps[label] = keep
    for label, mask in steps.items():
        print(f"  {label:<34} {int(mask.sum()):>7,}")
    survivors = bnb[keep]
    print(f"\n{len(survivors):,} survivors\n")
    if survivors.empty:
        print("nothing survives - best few by walk-forward among settings that at least make money overall:")
        loose = bnb[(bnb.full_profit > 0) & (bnb.full_trades >= MIN_TRADES)]
        cols = ["full_trades", "win_rate", "full_profit", "earlier_profit", "later_profit", "unseen_profit",
                "wf_profit", "wf_wins", "full_dd"]
        print(loose.sort_values("wf_profit", ascending=False)[cols].head(15).round(2))
        return

    cols = ["full_trades", "win_rate", "full_profit", "earlier_profit", "later_profit", "unseen_profit",
            "wf_profit", "wf_wins", "full_dd"]
    print("best 20 survivors by walk-forward profit:")
    print(survivors.sort_values("wf_profit", ascending=False)[cols].head(20).round(2))
    print("\nwhere the survivors sit:")
    flat = survivors.reset_index()
    for key in KEYS:
        counts = flat[key].value_counts().sort_index()
        print(f"  {key:<16} " + "  ".join(f"{value}:{count}" for value, count in counts.items()))
    flat.to_csv(grid.ROOT / "results" / "eth_consolidation_survivors.csv", index=False)
    print(f"\nsaved {grid.ROOT / 'results' / 'eth_consolidation_survivors.csv'}")


if __name__ == "__main__":
    main()
