"""Best exit settings per coin, subject to keeping a win rate of at least 75%."""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid

WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
KEY = ["style", "value", "arm_pct", "stop_pct"]
FLOOR = 75.0


def board_for(coin):
    board = pd.read_parquet(grid.ROOT / "results" / f"{coin}_ema_exit_grid.parquet")
    board["wf_profit"] = board[[f"{w}_profit" for w in WF]].sum(axis=1)
    board["wf_wins"] = sum((board[f"{w}_profit"] > 0).astype(int) for w in WF)
    board["win_rate"] = board.full_wins / board.full_trades.replace(0, np.nan) * 100
    board["avg_win"] = board.full_gross_win / board.full_wins.replace(0, np.nan)
    board["avg_loss"] = -board.full_gross_loss / (board.full_trades - board.full_wins).replace(0, np.nan)
    bnb, usdt = board[board.fees == "BNB"].copy(), board[board.fees == "USDT"].copy()
    bnb["usdt"] = usdt.set_index(KEY).full_profit.reindex(pd.MultiIndex.from_frame(bnb[KEY])).to_numpy()
    return bnb


def main() -> None:
    pd.set_option("display.width", 250)
    summary, details = [], []
    for coin in ("sol", "eth", "trx", "aave", "btc"):
        rule = live.load_rule(coin)
        bnb = board_for(coin)
        dep = bnb[(bnb["style"] == "giveback") & (bnb.value == rule["giveback_pct"])
                  & np.isclose(bnb.arm_pct, rule["activation_pct"], atol=0.01) & (bnb.stop_pct == rule["stop_pct"])]
        dep = dep.iloc[0]
        passes = ((bnb.full_profit > 0) & (bnb.earlier_profit > 0) & (bnb.later_profit > 0)
                  & (bnb.unseen_profit >= 0) & (bnb.wf_profit > 0) & (bnb.wf_wins >= 4) & (bnb.usdt > 0))
        good = bnb[passes & (bnb.win_rate >= FLOOR) & (bnb.full_profit > dep.full_profit)]
        row = {"coin": coin.upper(), "deployed_profit": dep.full_profit, "deployed_win": dep.win_rate,
               "deployed_dd": dep.full_dd, "settings_at_75pct": len(good)}
        if len(good):
            best = good.sort_values("full_profit", ascending=False).iloc[0]
            style = "give back" if best["style"] == "giveback" else ("EMA" + ("" if best["style"] == "ema_always" else " in uptrend"))
            value = f"{best.value:g}%" if best["style"] == "giveback" else f"{best.value / 60:g}h"
            row |= {"best": f"{style} {value}, arm {best.arm_pct:g}%, stop -{best.stop_pct:g}%",
                    "profit": best.full_profit, "win": best.win_rate, "avg_win": best.avg_win,
                    "avg_loss": best.avg_loss, "unseen": best.unseen_profit, "wf": best.wf_profit,
                    "wf_windows": f"{int(best.wf_wins)}/6", "dd": best.full_dd}
            top = good.sort_values("full_profit", ascending=False).head(5).copy()
            top.insert(0, "coin", coin.upper())
            details.append(top)
        summary.append(row)
    frame = pd.DataFrame(summary)
    print("=== best setting per coin with a win rate of 75% or better (and beating the deployed rule)")
    print(frame.round(2).to_string(index=False))
    cols = ["coin", "style", "value", "arm_pct", "stop_pct", "full_trades", "win_rate", "avg_win", "avg_loss",
            "full_profit", "usdt", "earlier_profit", "later_profit", "unseen_profit", "wf_profit", "wf_wins", "full_dd"]
    print("\n=== top 5 per coin at the 75% floor")
    print(pd.concat(details, ignore_index=True)[cols].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
