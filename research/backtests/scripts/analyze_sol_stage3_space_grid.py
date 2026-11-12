"""Select SOL candidates from the grid on the earlier period only, then judge
them once with the exact Stage 3 replay on later and the unseen holdout."""

from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd

import run_sol_stage3_space_grid as grid
import stage3_replay as replay

RESULT_DIR = grid.RESULT_DIR
MIN_EARLIER_TRADES = 30
MAX_EARLIER_DD = -15.0
FINALISTS = 15
NO_LIMIT_MINUTES = 10**9
FULL = (pd.Timestamp("2024-10-01", tz="UTC"), pd.Timestamp("2026-08-01", tz="UTC"))
PARAMS = ["signal_minutes", "average_days", "zone_pct", "approach", "market_filter",
          "stop_pct", "activation_pct", "giveback_pct", "hold_hours", "lots", "fraction"]


def strategy_for(row: dict) -> dict:
    strategy = copy.deepcopy(json.loads(replay.STRATEGY_FILES[grid.SYMBOL].read_text()))
    strategy["strategy_id"] = "sol_candidate"
    strategy["market"]["signal_timeframe"] = f"{int(row['signal_minutes'])}m"
    strategy["averages"]["signal_average_days"] = int(row["average_days"])
    strategy["entry"]["touch_zone_pct"] = float(row["zone_pct"])
    strategy["entry"]["approach"] = row["approach"]
    strategy["entry"]["market_filter"]["type"] = row["market_filter"]
    strategy["exit"]["protective_stop_pct_from_entry_fill"] = float(row["stop_pct"])
    strategy["exit"]["trailing_stop"]["activation_pct_from_entry_fill"] = float(row["activation_pct"])
    strategy["exit"]["trailing_stop"]["giveback_of_open_profit_pct"] = float(row["giveback_pct"])
    hold = int(row["hold_hours"])
    strategy["exit"]["maximum_hold_minutes"] = hold * 60 if hold else NO_LIMIT_MINUTES
    strategy["portfolio"]["maximum_open_positions"] = int(row["lots"])
    strategy["portfolio"]["equity_fraction_per_entry"] = float(row["fraction"])
    return strategy


class ExactReplay:
    def __init__(self) -> None:
        self.raw = replay.load_raw(grid.SYMBOL, include_holdout=True)
        self.averages = replay.daily_averages(self.raw)
        self.candles: dict[int, list] = {}
        self.signals: dict[tuple, list] = {}

    def run(self, row: dict) -> dict[str, dict]:
        strategy = strategy_for(row)
        minutes = int(row["signal_minutes"])
        if minutes not in self.candles:
            self.candles = {minutes: replay.signal_candles(self.raw, minutes, self.averages)}
        key = tuple(row[name] for name in PARAMS[:5])
        if key not in self.signals:
            self.signals[key], _ = replay.generate_signals(strategy, self.candles[minutes])
        periods = {"full": FULL, **grid.PERIODS}
        return {
            period: replay.summarize(replay.replay_execution(
                strategy, self.raw, self.signals[key], start, end))
            for period, (start, end) in periods.items()
        }


def describe(row: dict) -> str:
    hold = int(row["hold_hours"])
    return (f"{int(row['signal_minutes'])}m candles, {int(row['average_days'])}-day average, "
            f"±{row['zone_pct']:g}% zone, {row['approach'].replace('_', ' ')}, "
            f"{row['market_filter'].replace('_', ' ')}; stop −{row['stop_pct']:g}%, trail from "
            f"+{row['activation_pct']:g}% with {row['giveback_pct']:g}% giveback, "
            f"{f'{hold}h' if hold else 'no'} hold limit; {int(row['lots'])} lot(s) × "
            f"{row['fraction'] * 100:.0f}%")


def main() -> None:
    board = pd.read_parquet(RESULT_DIR / "all_combinations.parquet")
    board["key"] = np.arange(len(board))
    base_mask = np.ones(len(board), dtype=bool)
    for name, value in grid.BASELINE.items():
        base_mask &= np.isclose(board[name], value) if isinstance(value, float) else board[name] == value
    baseline_row = board[base_mask].iloc[0].to_dict()

    eligible = board[(board.earlier_trades >= MIN_EARLIER_TRADES)
                     & (board.earlier_profit_factor > 1)
                     & (board.earlier_approx_dd_pct >= MAX_EARLIER_DD)].copy()
    eligible["earlier_return_to_dd"] = eligible.earlier_return_pct / -eligible.earlier_approx_dd_pct.clip(upper=-0.01)
    rules = {
        "A_highest_earlier_return": eligible.sort_values("earlier_return_pct", ascending=False),
        "B_best_earlier_return_per_drawdown": eligible.sort_values("earlier_return_to_dd", ascending=False),
    }

    exact = ExactReplay()
    baseline_exact = exact.run(baseline_row)
    picks = {}
    for rule, ranked in rules.items():
        # Finalists re-run exactly; the first whose exact earlier drawdown stays
        # inside the limit is the rule's candidate.
        for row in ranked.head(FINALISTS).to_dict("records"):
            result = exact.run(row)
            if result["earlier"]["max_drawdown_pct"] >= MAX_EARLIER_DD:
                picks[rule] = (row, result)
                break
        print(f"{rule}: {describe(picks[rule][0])}", flush=True)

    # How well does "good in earlier" carry into later across the whole grid?
    generalisation = []
    for rule, ranked in rules.items():
        for top in (10, 100, 1000):
            head = ranked.head(top)
            generalisation.append({
                "rule": rule, "top_n": top,
                "median_earlier_return_pct": head.earlier_return_pct.median(),
                "median_later_return_pct": head.later_return_pct.median(),
                "share_positive_later_pct": (head.later_return_pct > 0).mean() * 100,
                "share_beating_baseline_later_pct": (
                    head.later_return_pct > baseline_row["later_return_pct"]).mean() * 100,
            })
    generalisation = pd.DataFrame(generalisation)
    counts = {
        "combinations": len(board),
        "eligible_in_earlier": len(eligible),
        "positive_earlier": int((board.earlier_return_pct > 0).sum()),
        "positive_later": int((board.later_return_pct > 0).sum()),
        "positive_both": int(((board.earlier_return_pct > 0) & (board.later_return_pct > 0)).sum()),
        "beat_baseline_earlier_and_later": int(
            ((board.earlier_return_pct > baseline_row["earlier_return_pct"])
             & (board.later_return_pct > baseline_row["later_return_pct"])).sum()),
        "baseline_earlier_rank_pct": float((board.earlier_return_pct > baseline_row["earlier_return_pct"]).mean() * 100),
        "baseline_later_rank_pct": float((board.later_return_pct > baseline_row["later_return_pct"]).mean() * 100),
    }
    in_sample = board.assign(full_proxy=(1 + board.earlier_return_pct / 100) * (1 + board.later_return_pct / 100))
    in_sample_best = in_sample.sort_values("full_proxy", ascending=False).iloc[0].to_dict()
    in_sample_exact = exact.run(in_sample_best)

    payload = {
        "selection": {"period": "earlier only", "min_trades": MIN_EARLIER_TRADES,
                      "min_profit_factor": 1.0, "max_drawdown_pct": MAX_EARLIER_DD},
        "grid_counts": counts,
        "baseline": {"rules": {k: baseline_row[k] for k in PARAMS}, "exact": baseline_exact,
                     "grid_row": {k: v for k, v in baseline_row.items() if k.startswith(("earlier_", "later_", "holdout_"))}},
        "candidates": {rule: {"rules": {k: row[k] for k in PARAMS}, "description": describe(row),
                              "exact": result, "proposed_strategy_json": strategy_for(row)}
                       for rule, (row, result) in picks.items()},
        "in_sample_best_not_selectable": {"rules": {k: in_sample_best[k] for k in PARAMS},
                                          "description": describe(in_sample_best), "exact": in_sample_exact},
    }
    (RESULT_DIR / "selection.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    generalisation.to_csv(RESULT_DIR / "generalisation.csv", index=False)
    for rule, ranked in rules.items():
        ranked.head(1000).drop(columns="key").to_csv(RESULT_DIR / f"top1000_{rule}.csv", index=False)
    print(json.dumps(counts, indent=2))
    print(generalisation.round(2).to_string(index=False))
    for name, (rules_, result) in {"BASELINE": (baseline_row, baseline_exact),
                                   **{r: p for r, p in picks.items()},
                                   "IN-SAMPLE BEST": (in_sample_best, in_sample_exact)}.items():
        print(f"\n== {name}: {describe(rules_)}")
        print(pd.DataFrame(result).T[["trades", "wins", "losses", "win_rate_pct", "final_equity_usd",
                                      "return_pct", "profit_factor", "max_drawdown_pct",
                                      "trailing_exits", "stop_exits", "time_exits",
                                      "average_hold_hours", "open_positions_at_end"]].round(2).to_string())


if __name__ == "__main__":
    main()
