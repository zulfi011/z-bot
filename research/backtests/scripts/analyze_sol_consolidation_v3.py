"""Score the v3 consolidation grid the strict way: walk-forward first, total profit last.

A combination is only interesting if it makes money in both halves AND in most of the six walk-forward test
windows (each window trades three months with settings that were already fixed beforehand). Total profit breaks
ties. Also prints how each single setting behaves on its own, and how the winner's neighbours do.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_consolidation_v3 as v3

SETTINGS = ["window_minutes", "quietest_pct", "margin_pct", "close_strength", "volume_mult", "trend", "skip_06_12",
            "stop_buffer_pct", "target_x_range", "trail_giveback_pct", "timer_minutes"]
SHOW = SETTINGS + ["full_trades", "full_profit", "earlier_profit", "later_profit", "unseen_profit", "full_dd", "wf_total"]
pd.set_option("display.width", 300)
pd.set_option("display.max_columns", 40)


def describe(row) -> str:
    target = "no target" if pd.isna(row.target_x_range) else f"target {row.target_x_range:g}x the range"
    trail = "no trailing" if pd.isna(row.trail_giveback_pct) else f"trail from break-even giving back {row.trail_giveback_pct:g}%"
    timer = "no timer" if pd.isna(row.timer_minutes) else f"give up after {int(row.timer_minutes)} min"
    volume = "any volume" if row.volume_mult == 0 else f"volume ≥ {row.volume_mult:g}x the last hour"
    strength = "any close" if row.close_strength == 0 else "close in the top third"
    return (f"quiet {int(row.window_minutes)} min in the quietest {int(row.quietest_pct)}% of the last 30 days, "
            f"break by {row.margin_pct:g}%, {strength}, {volume}, "
            f"{'only above 30-day avg' if row.trend == 'above_30d' else 'no trend filter'}, "
            f"{'skip 06–12 UTC' if row.skip_06_12 else 'all hours'} | stop at the range low"
            f"{'' if row.stop_buffer_pct == 0 else f' −{row.stop_buffer_pct:g}%'}, {target}, {trail}, {timer}")


def main() -> None:
    board = pd.read_parquet(v3.RESULT_DIR / "all_combinations.parquet")
    tests = [f"wf{i}_test_profit" for i in range(len(research.TESTS))]
    board["wf_total"] = board[tests].sum(axis=1)
    board["wf_positive"] = (board[tests] > 0).sum(axis=1)
    board["wf_traded"] = (board[[f"wf{i}_test_trades" for i in range(len(research.TESTS))]] > 0).sum(axis=1)
    print({"combinations": len(board), "profitable_full": int((board.full_profit > 0).sum()),
           "profitable_both_periods": int(((board.earlier_profit > 0) & (board.later_profit > 0)).sum()),
           "walk_forward_positive": int((board.wf_total > 0).sum())})

    for name in ("window_minutes", "quietest_pct", "margin_pct", "close_strength", "volume_mult", "trend",
                 "skip_06_12", "stop_buffer_pct", "target_x_range", "trail_giveback_pct", "timer_minutes"):
        summary = board.groupby(name, dropna=False).agg(median_full=("full_profit", "median"),
                                                        median_wf=("wf_total", "median")).round(1)
        print(f"\nby {name}:\n{summary.to_string()}")

    good = board[(board.earlier_profit > 0) & (board.later_profit > 0) & (board.wf_total > 0)
                 & (board.wf_positive >= 4) & (board.wf_traded >= 5)]
    print(f"\n{len(good):,} combinations make money in both halves and in at least 4 of 6 walk-forward windows")
    if good.empty:
        loose = board[(board.earlier_profit > 0) & (board.later_profit > 0)].sort_values("wf_total", ascending=False)
        print("\nBest by walk-forward among those profitable in both halves:")
        print(loose[SHOW].head(10).round(2).to_string(index=False))
        return
    ranked = good.sort_values(["wf_total", "full_profit"], ascending=False)
    print(ranked[SHOW].head(15).round(2).to_string(index=False))
    best = ranked.iloc[0]
    print(f"\nCANDIDATE: {describe(best)}")
    print(f"  full ${best.full_profit:.2f} | earlier ${best.earlier_profit:.2f} | later ${best.later_profit:.2f} | "
          f"unseen ${best.unseen_profit:.2f} | walk-forward ${best.wf_total:.2f} in {int(best.wf_positive)}/6 windows | "
          f"{int(best.full_trades)} trades | win rate {100 * best.full_wins / max(best.full_trades, 1):.0f}% | "
          f"drawdown {best.full_dd:.1f}%")

    print("\nNEIGHBOURS (one setting moved, everything else kept)")
    lines = []
    for name, values in (("window_minutes", v3.WINDOWS_MIN), ("quietest_pct", v3.QUIETEST_PCT),
                         ("margin_pct", v3.MARGINS), ("close_strength", v3.STRENGTH), ("volume_mult", v3.VOLUME_MULTS),
                         ("trend", v3.TRENDS), ("skip_06_12", v3.TIME_FILTERS), ("stop_buffer_pct", v3.STOP_BUFFERS),
                         ("target_x_range", v3.TARGETS), ("trail_giveback_pct", v3.TRAILS), ("timer_minutes", v3.TIMERS)):
        for value in values:
            found = board
            for key in SETTINGS:
                wanted = value if key == name else best[key]
                if wanted is None or (isinstance(wanted, float) and np.isnan(wanted)):
                    found = found[found[key].isna()]
                elif isinstance(wanted, (str, bool, np.bool_)):
                    found = found[found[key] == wanted]
                else:
                    found = found[np.isclose(found[key].astype(float), float(wanted))]
            if len(found):
                row = found.iloc[0]
                lines.append({"setting": name, "value": "none" if value is None else value, "full": row.full_profit,
                              "earlier": row.earlier_profit, "later": row.later_profit, "unseen": row.unseen_profit,
                              "walk_forward": row.wf_total, "trades": row.full_trades, "dd": row.full_dd})
    print(pd.DataFrame(lines).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
