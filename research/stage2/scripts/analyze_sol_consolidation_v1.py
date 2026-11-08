"""Pick and stress-test the SOL consolidation-breakout candidate, on the same bar every coin had to clear.

Reports: how many of the 50,688 combinations make money, the best consistent one, walk-forward (pick the best of
the previous six months, trade the next three), one change at a time, the nearby-settings check, and the candidate
re-run at BNB and stress costs (its exit table is rebuilt for those costs, so fills and fees are exact).
"""

from __future__ import annotations

import multiprocessing as mp

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_consolidation_v1 as strat
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

PARAMS = ["band_pct", "window_minutes", "stop_pct", "trail_mode", "activation_pct", "giveback_pct", "be_trigger",
          "trend", "skip_06_12"]
SHOW = PARAMS + ["full_trades", "full_profit", "earlier_profit", "later_profit", "unseen_profit", "full_dd"]
pd.set_option("display.width", 260)
pd.set_option("display.max_columns", 40)


def describe(row) -> str:
    be = f", break-even stop after +{row['be_trigger']:g}%" if pd.notna(row["be_trigger"]) else ""
    trend = "only above 30-day avg" if row["trend"] == "above_30d" else "no trend filter"
    return (f"band ±{row['band_pct']:g}% held {int(row['window_minutes'])} min, stop −{row['stop_pct']:g}%, "
            f"trail +{row['activation_pct']:g}%/{row['giveback_pct']:g}%{be}, {trend}, "
            f"{'skip 06–12 UTC' if row['skip_06_12'] else 'all hours'}")


def costed(row, entries, feats, times, fee, slip):
    """Re-run one combination end to end at the given fee and slippage."""
    grid.FEE, grid.SLIP = fee / 10_000, slip / 10_000
    keep = feats[row["trend"]] & ~(feats["morning"] & bool(row["skip_06_12"]))
    kept = entries[keep]
    context = mp.get_context("fork")
    with context.Pool(8) as pool:
        parts = pool.map(research.exits_for, np.array_split(kept, 80))
    research.TABLE = tuple(np.concatenate([p[i] for p in parts]) for i in range(3))
    column = [i for i, exit_ in enumerate(research.EXITS)
              if exit_[0] == row["trail_mode"] and np.isclose(exit_[1], row["activation_pct"])
              and np.isclose(exit_[2], row["giveback_pct"]) and np.isclose(exit_[4], row["stop_pct"])
              and ((exit_[3] is None and pd.isna(row["be_trigger"])) or exit_[3] == row["be_trigger"])][0]
    entry_times = times[kept]
    out = {}
    for name in ("full", "earlier", "later", "unseen"):
        start, end = research.WINDOWS[name]
        mask = (entry_times >= start) & (entry_times < end)
        stats = research.simulate(kept[mask], np.arange(len(kept))[mask])
        out[name] = {key: float(value[column]) for key, value in stats.items()}
    return out


def main() -> None:
    board = pd.read_parquet(strat.RESULT_DIR / "all_combinations.parquet")
    both = board[(board.earlier_profit > 0) & (board.later_profit > 0)]
    print({"combinations": len(board), "profitable_full": int((board.full_profit > 0).sum()),
           "profitable_both_periods": len(both)})
    for name in ("band_pct", "window_minutes", "stop_pct", "giveback_pct", "trend", "skip_06_12"):
        best = board.groupby(name).full_profit.median().round(1).to_dict()
        print(f"median full profit by {name}: {best}")

    ranked = both.sort_values("full_profit", ascending=False)
    print("\nTOP 15 consistent (profit in both periods)")
    print(ranked[SHOW].head(15).round(2).to_string(index=False))
    if ranked.empty:
        print("\nNO COMBINATION IS PROFITABLE IN BOTH PERIODS — TOP 15 BY FULL PERIOD")
        print(board.sort_values("full_profit", ascending=False)[SHOW].head(15).round(2).to_string(index=False))
        return
    candidate = ranked.iloc[0]
    print(f"\nCANDIDATE: {describe(candidate)}")

    print("\nWALK-FORWARD (pick best of previous 6 months, trade next 3)")
    rows = []
    for i, (start, end) in enumerate(research.TESTS):
        pick = board.loc[board[f"wf{i}_train_profit"].idxmax()]
        rows.append({"test": f"{start}→{end}", "train_profit": pick[f"wf{i}_train_profit"],
                     "test_profit": pick[f"wf{i}_test_profit"], "test_trades": pick[f"wf{i}_test_trades"],
                     "candidate_test_profit": candidate[f"wf{i}_test_profit"],
                     "median_all_test_profit": board[f"wf{i}_test_profit"].median()})
    walk = pd.DataFrame(rows)
    print(walk.round(2).to_string(index=False))
    print(f"walk-forward total ${walk.test_profit.sum():.2f} | candidate in same windows ${walk.candidate_test_profit.sum():.2f}")

    print("\nONE CHANGE AT A TIME FROM THE CANDIDATE")
    lines = []
    for name, values in (("band_pct", strat.BANDS), ("window_minutes", strat.MINUTES), ("stop_pct", research.STOPS),
                         ("giveback_pct", research.GIVEBACKS), ("trend", strat.TRENDS), ("skip_06_12", [False, True])):
        for value in values:
            match = {key: candidate[key] for key in PARAMS if key != name}
            match[name] = value
            if name == "giveback_pct":   # the trailing start moves with the giveback
                match["activation_pct"] = round(research.gb.break_even_activation(float(value)) + 1, 3)
            found = board
            for key, wanted in match.items():
                if pd.isna(wanted):
                    found = found[found[key].isna()]
                elif isinstance(wanted, (str, bool, np.bool_)):
                    found = found[found[key] == wanted]
                else:
                    found = found[np.isclose(found[key].astype(float), float(wanted))]
            if len(found):
                row = found.iloc[0]
                lines.append({"idea": name, "value": value, "full": row.full_profit, "earlier": row.earlier_profit,
                              "later": row.later_profit, "unseen": row.unseen_profit, "trades": row.full_trades,
                              "dd": row.full_dd})
    print(pd.DataFrame(lines).round(2).to_string(index=False))

    print("\nNEARBY SETTINGS (same exits, band and window moved one step)")
    bands, windows = strat.BANDS, strat.MINUTES
    b, w = bands.index(candidate.band_pct), windows.index(int(candidate.window_minutes))
    for db, dw in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        if 0 <= b + db < len(bands) and 0 <= w + dw < len(windows):
            match = {key: candidate[key] for key in PARAMS}
            match["band_pct"], match["window_minutes"] = bands[b + db], windows[w + dw]
            found = board
            for key, wanted in match.items():
                if pd.isna(wanted):
                    found = found[found[key].isna()]
                elif isinstance(wanted, (str, bool, np.bool_)):
                    found = found[found[key] == wanted]
                else:
                    found = found[np.isclose(found[key].astype(float), float(wanted))]
            row = found.iloc[0]
            print(f"  band ±{row.band_pct:g}% / {int(row.window_minutes)}m: full {row.full_profit:8.2f} "
                  f"earlier {row.earlier_profit:7.2f} later {row.later_profit:7.2f} unseen {row.unseen_profit:6.2f}")

    print("\nEXACT RE-RUN AT OTHER COSTS")
    raw = replay.load_raw(strat.SYMBOL, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals)
             for d, vals in replay.daily_averages(raw).items()}
    entries = strat.breakouts(grid.HIGH, grid.LOW, grid.OPEN, grid.CLOSE, float(candidate.band_pct),
                              int(candidate.window_minutes))
    feats = research.features(pd.DataFrame({"entry_index": entries}), 1, daily, times)
    for label, (fee, slip) in (("10/2 bps", (10.0, 2.0)), ("7.5/2 bps BNB", (7.5, 2.0)), ("15/5 bps stress", (15.0, 5.0))):
        result = costed(candidate, entries, feats, times, fee, slip)
        for window, stats in result.items():
            print(f"  {label:16s} {window:8s} trades {stats['trades']:6.0f}  profit {stats['profit']:8.2f}  "
                  f"win rate {100 * stats['wins'] / max(stats['trades'], 1):5.1f}%  drawdown {stats['dd']:6.2f}%")


if __name__ == "__main__":
    main()
