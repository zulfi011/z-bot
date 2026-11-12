"""BTC: rank combinations by how well their neighbours do (average ±1 day, zone ±0.1%).

A real edge should survive nearby settings; the top single result (5-day average) did not.
Score = worst full-period profit among the combination and its 4 entry neighbours.
"""

import numpy as np
import pandas as pd

import analyze_eth_full_research as analysis
import run_btc_full_research  # noqa: F401
import run_eth_full_research as research

board = pd.read_parquet(research.RESULT_DIR / "all_combinations.parquet")
exit_keys = ["signal_minutes", "stop_pct", "trail_mode", "activation_pct", "giveback_pct", "be_trigger", "trend", "skip_06_12"]
board["be_trigger"] = board.be_trigger.fillna(-1)
keyed = board.set_index(exit_keys + ["average_days", "zone_pct"])
full = keyed.full_profit
rows = []
for shift in [(-1, 0.0), (1, 0.0), (0, -0.1), (0, 0.1)]:
    moved = board.assign(average_days=board.average_days + shift[0], zone_pct=(board.zone_pct + shift[1]).round(1))
    idx = pd.MultiIndex.from_frame(moved[exit_keys + ["average_days", "zone_pct"]])
    rows.append(full.reindex(idx).to_numpy())
neigh = np.vstack(rows)
board["neighbour_min"] = np.nanmin(np.vstack([neigh, board.full_profit.to_numpy()]), axis=0)
board["neighbour_mean"] = np.nanmean(neigh, axis=0)
board["neighbours"] = (~np.isnan(neigh)).sum(0)
ok = board[(board.neighbours == 4) & (board.earlier_profit > 0) & (board.later_profit > 0)]
ranked = ok.sort_values("neighbour_min", ascending=False)
cols = analysis.PARAMS + ["full_trades", "full_profit", "earlier_profit", "later_profit", "unseen_profit", "full_dd", "neighbour_min", "neighbour_mean"]
pd.set_option("display.width", 260)
print(f"{len(ok):,} combos profitable in both periods with all 4 neighbours present; "
      f"{int((ok.neighbour_min > 0).sum())} have every neighbour profitable over the full period")
print(ranked[cols].head(20).round(2).to_string(index=False))
print("\nBy average days (combos whose worst neighbour is still > 0):",
      ok[ok.neighbour_min > 0].groupby("average_days").size().to_dict())
print("By timeframe:", ok[ok.neighbour_min > 0].groupby("signal_minutes").size().to_dict())
ranked.head(300).to_csv(research.RESULT_DIR / "top300_robust.csv", index=False)
