"""Pick and stress-test the ETH candidate from run_eth_full_research.

Other coins reuse it by setting run_eth_full_research.SYMBOL / RESULT_DIR first
(see analyze_btc_full_research.py)."""

from __future__ import annotations

import copy
import json
from decimal import Decimal

import numpy as np
import pandas as pd

import run_eth_full_research as eth
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

PARAMS = ["signal_minutes", "average_days", "zone_pct", "stop_pct", "trail_mode", "activation_pct", "giveback_pct",
          "be_trigger", "trend", "skip_06_12"]
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)


def describe(row) -> str:
    be = f", break-even stop after +{row['be_trigger']:g}%" if pd.notna(row["be_trigger"]) else ""
    trend = {"none": "no trend filter", "above_30d": "only above 30-day avg",
             "above_30d_max10": "above 30-day avg (≤ +10%)"}[row["trend"]]
    return (f"{int(row['signal_minutes'])}m, {int(row['average_days'])}-day avg, ±{row['zone_pct']:g}%, stop −{row['stop_pct']:g}%, "
            f"trail +{row['activation_pct']:g}%/{row['giveback_pct']:g}%{be}, {trend}, "
            f"{'skip 06–12 UTC' if row['skip_06_12'] else 'all hours'}")


def select(board: pd.DataFrame, **match) -> pd.DataFrame:
    mask = np.ones(len(board), bool)
    for key, value in match.items():
        if value is None or (isinstance(value, (float, np.floating)) and np.isnan(value)):
            mask &= board[key].isna().to_numpy()
        elif isinstance(value, (bool, np.bool_, str)):
            mask &= (board[key] == value).to_numpy()
        else:
            mask &= np.isclose(board[key].astype(float), float(value))
    return board[mask]


def exact(row: dict, raw: pd.DataFrame, daily_decimal, daily, times, fee=10.0, slip=2.0, zone=None) -> dict:
    strategy = copy.deepcopy(json.loads(replay.STRATEGY_FILES["ETHUSDT"].read_text()))
    minutes, days = int(row["signal_minutes"]), int(row["average_days"])
    zone = zone if zone is not None else float(row["zone_pct"])
    # The ETH v1 file is only a template: every rule that matters is overridden below.
    strategy.update({"strategy_id": f"{eth.SYMBOL.removesuffix('USDT').lower()}_candidate"})
    strategy["market"]["signal_timeframe"] = f"{minutes}m"
    strategy["averages"]["signal_average_days"] = days
    strategy["entry"].update({"touch_zone_pct": zone, "approach": "from_below"})
    strategy["entry"]["market_filter"]["type"] = "avoid_strong_bearish"
    strategy["exit"].update({"protective_stop_pct_from_entry_fill": float(row["stop_pct"]), "maximum_hold_minutes": 10**9})
    strategy["exit"]["trailing_stop"].update({"activation_pct_from_entry_fill": float(row["activation_pct"]),
                                              "giveback_of_open_profit_pct": float(row["giveback_pct"])})
    strategy["portfolio"].update({"maximum_open_positions": 3, "initial_paper_equity_usd": 300.0})
    strategy["execution_model"].update({"fee_bps_per_side": fee, "slippage_bps_per_side": slip})
    candles = replay.signal_candles(raw, minutes, daily_decimal, signal_days=days)
    signals, _ = replay.generate_signals(strategy, candles)
    entry_index = np.array([times.searchsorted(pd.Timestamp(s["entry_time"])) for s in signals])
    frame = pd.DataFrame({"entry_index": entry_index})
    feats = eth.features(frame, minutes, daily, times)
    keep = feats[row["trend"]] & ~(feats["morning"] & bool(row["skip_06_12"]))
    chosen = [s for s, k in zip(signals, keep) if k]
    rule = replay.breakeven_exit(float(row["be_trigger"]), eth.BE_LEVEL) if pd.notna(row["be_trigger"]) else None
    allocate = lambda marked, cash: Decimal("100") if cash >= Decimal("100") else Decimal("0")  # noqa: E731
    out = {}
    for name in ("full", "earlier", "later", "unseen"):
        start, end = eth.WINDOWS[name]
        result = replay.replay_execution(strategy, raw, chosen, start, end, allocate=allocate, exit_rule=rule)
        out[name] = replay.summarize(result, initial=300.0)
    return out


def main() -> None:
    RESULT_DIR = eth.RESULT_DIR
    board = pd.read_parquet(RESULT_DIR / "all_combinations.parquet")
    board["full_pf"] = board.full_gross_win / board.full_gross_loss.replace(0, np.nan)
    both = board[(board.earlier_profit > 0) & (board.later_profit > 0)]
    report = {"combinations": len(board), "profitable_full": int((board.full_profit > 0).sum()),
              "profitable_both_periods": len(both)}
    print(report)
    for name in ["signal_minutes", "average_days", "zone_pct", "stop_pct", "trail_mode", "giveback_pct", "be_trigger", "trend", "skip_06_12"]:
        grouped = board.groupby(name, dropna=False)
        print(name, {str(k): (round(float(v), 1), int(c)) for (k, v), c in
                     zip(grouped.full_profit.median().items(), (grouped.full_profit.apply(lambda x: (x > 0).sum())).values)})

    ranked = both.sort_values("full_profit", ascending=False)
    heading = "TOP 15 consistent (profit in both periods)"
    if ranked.empty:
        # No combination made money in both periods: study the best full-period result instead.
        ranked = board.sort_values("full_profit", ascending=False)
        heading = "NO COMBINATION IS PROFITABLE IN BOTH PERIODS — TOP 15 BY FULL-PERIOD PROFIT"
    candidate = ranked.iloc[0].to_dict()
    print("\n" + heading)
    print(ranked[PARAMS + ["full_trades", "full_profit", "earlier_profit", "later_profit", "unseen_profit", "unseen_trades", "full_dd", "full_pf"]].head(15).round(2).to_string(index=False))
    print("\nCANDIDATE:", describe(candidate))

    eligible = board[(board.earlier_trades >= 20) & (board.earlier_dd >= -15)]
    earlier_pick = eligible.sort_values("earlier_profit", ascending=False).iloc[0].to_dict()
    top_earlier = eligible.sort_values("earlier_profit", ascending=False).head(100)
    print("\nEARLIER-ONLY PICK:", describe(earlier_pick), {k: round(float(earlier_pick[k]), 2) for k in ["earlier_profit", "later_profit", "unseen_profit", "full_profit"]})
    print(f"   top-100 by earlier: median later {top_earlier.later_profit.median():.2f}, {int((top_earlier.later_profit > 0).sum())}/100 positive later")
    top_both = ranked.head(100)
    print(f"   top-100 consistent: median unseen {top_both.unseen_profit.median():.2f}, {int((top_both.unseen_profit > 0).sum())}/100 positive unseen")

    folds, wf_total, cand_total = [], 0.0, 0.0
    for i, (start, end) in enumerate(eth.TESTS):
        train = board[(board[f"wf{i}_train_trades"] >= 8) & (board[f"wf{i}_train_gross_win"] > board[f"wf{i}_train_gross_loss"])]
        pick = train.sort_values(f"wf{i}_train_profit", ascending=False).iloc[0]
        cand_row = select(board, **{k: candidate[k] for k in PARAMS}).iloc[0]
        folds.append({"test": f"{start}→{end}", "picked": describe(pick), "train_profit": round(float(pick[f"wf{i}_train_profit"]), 2),
                      "test_profit": round(float(pick[f"wf{i}_test_profit"]), 2), "test_trades": int(pick[f"wf{i}_test_trades"]),
                      "candidate_test_profit": round(float(cand_row[f"wf{i}_test_profit"]), 2),
                      "median_all_test_profit": round(float(board[f"wf{i}_test_profit"].median()), 2)})
        wf_total += float(pick[f"wf{i}_test_profit"])
        cand_total += float(cand_row[f"wf{i}_test_profit"])
    folds = pd.DataFrame(folds)
    print("\nWALK-FORWARD (pick best of previous 6 months, trade next 3)")
    print(folds.drop(columns="picked").to_string(index=False))
    print(f"walk-forward total ${wf_total:.2f} | candidate in same windows ${cand_total:.2f}")

    ideas = []
    base = {k: candidate[k] for k in PARAMS}
    variations = {"trend": eth.TRENDS, "skip_06_12": [False, True], "stop_pct": eth.STOPS,
                  "zone_pct": eth.ZONES, "average_days": sorted({max(1, int(candidate["average_days"]) + d) for d in (-2, -1, 0, 1, 2)} & set(eth.AVERAGE_DAYS)),
                  "signal_minutes": eth.TIMEFRAMES}
    for name, values in variations.items():
        for value in values:
            match = {**base, name: value}
            rows = select(board, **match)
            if len(rows):
                r = rows.iloc[0]
                ideas.append({"idea": name, "value": value, "full": round(float(r.full_profit), 2), "earlier": round(float(r.earlier_profit), 2),
                              "later": round(float(r.later_profit), 2), "unseen": round(float(r.unseen_profit), 2),
                              "trades": int(r.full_trades), "dd": round(float(r.full_dd), 2)})
    if candidate["trail_mode"] == "plus_1pct":
        for be in (None, 0.5, 0.75):
            r = select(board, **{**base, "be_trigger": be}).iloc[0]
            ideas.append({"idea": "be_trigger", "value": be, "full": round(float(r.full_profit), 2), "earlier": round(float(r.earlier_profit), 2),
                          "later": round(float(r.later_profit), 2), "trades": int(r.full_trades), "dd": round(float(r.full_dd), 2)})
    for mode in ("break_even", "plus_1pct"):
        act = [a for m, a, g in eth.PAIRS if m == mode and g == candidate["giveback_pct"]][0]
        rows = select(board, **{**base, "trail_mode": mode, "activation_pct": act, "be_trigger": None if mode == "break_even" else base["be_trigger"]})
        if len(rows):
            r = rows.iloc[0]
            ideas.append({"idea": "trail_start", "value": act, "full": round(float(r.full_profit), 2), "earlier": round(float(r.earlier_profit), 2),
                          "later": round(float(r.later_profit), 2), "trades": int(r.full_trades), "dd": round(float(r.full_dd), 2)})
    ideas = pd.DataFrame(ideas)
    print("\nONE CHANGE AT A TIME FROM THE CANDIDATE\n" + ideas.to_string(index=False))

    raw = replay.load_raw(eth.SYMBOL, include_holdout=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    daily_decimal = replay.daily_averages(raw)
    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals) for d, vals in daily_decimal.items()}
    checks = []
    for label, kwargs in {"10/2 bps": {}, "7.5/2 bps BNB": {"fee": 7.5}, "15/5 bps stress": {"fee": 15.0, "slip": 5.0},
                          f"zone ±{candidate['zone_pct'] - 0.05:.2f}%": {"zone": round(candidate["zone_pct"] - 0.05, 2)},
                          f"zone ±{candidate['zone_pct'] + 0.05:.2f}%": {"zone": round(candidate["zone_pct"] + 0.05, 2)}}.items():
        result = exact(candidate, raw, daily_decimal, daily, times, **kwargs)
        for period, summary in result.items():
            checks.append({"run": label, "period": period, **{k: summary[k] for k in
                           ["trades", "win_rate_pct", "net_profit_usd", "max_drawdown_pct", "profit_factor", "average_winner_pct",
                            "average_loser_pct", "fees_usd", "slippage_usd", "trailing_exits", "stop_exits", "breakeven_exits",
                            "average_hold_hours", "trades_per_month"]}})
        print(f"exact: {label}", flush=True)
    checks = pd.DataFrame(checks)
    print("\nEXACT (fast grid said full/earlier/later = "
          f"{candidate['full_profit']:.2f}/{candidate['earlier_profit']:.2f}/{candidate['later_profit']:.2f})")
    print(checks.round(2).to_string(index=False))

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    ranked.head(500).to_csv(RESULT_DIR / "top500_consistent.csv", index=False)
    folds.to_csv(RESULT_DIR / "walk_forward.csv", index=False)
    ideas.to_csv(RESULT_DIR / "one_change_at_a_time.csv", index=False)
    checks.to_csv(RESULT_DIR / "exact_checks.csv", index=False)
    (RESULT_DIR / "candidate.json").write_text(json.dumps(
        {"rules": describe(candidate), **{k: (None if pd.isna(v) else v) for k, v in candidate.items() if k in PARAMS},
         "summary": report, "walk_forward_total_usd": wf_total, "candidate_in_wf_windows_usd": cand_total,
         "earlier_only_pick": describe(earlier_pick)}, indent=2, default=str))


if __name__ == "__main__":
    main()
