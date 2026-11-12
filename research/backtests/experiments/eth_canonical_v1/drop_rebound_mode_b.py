"""Search ETH rolling-drop entries with a fixed +0.19% Mode B trailing activation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .confirmation_quality import quality
from .engine import CandidateTrade, MarketData, ReplayResult, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_drop_rebound_mode_b_v1.json"
CONTROL = "current_eth_base"


def drop_entries(close: np.ndarray, lookback_minutes: int, fall_pct: float) -> np.ndarray:
    """Buy next minute after the first close crossing below a prior rolling-high drawdown level."""
    series = pd.Series(np.asarray(close, dtype=float))
    reference = series.shift(1).rolling(int(lookback_minutes), min_periods=int(lookback_minutes)).max()
    condition = series <= reference * (1 - float(fall_pct) / 100)
    onset = condition & ~condition.shift(1, fill_value=False)
    signals = np.flatnonzero(onset.to_numpy())
    entries = signals + 1
    return entries[entries < len(series) - 1].astype(np.int64)


def _exit_kind(code: int) -> str:
    return {1: "trailing_stop", 2: "protective_stop", 3: "data_endpoint"}.get(int(code), "unknown")


def drop_candidates(
    entries: np.ndarray, market: MarketData, lookback: int, fall_pct: float, stop_pct: float,
    activation_pct: float, giveback_pct: float,
    cache: dict[tuple[int, float], tuple[int, float, int, int | None]],
) -> list[CandidateTrade]:
    grid = baseline_module.grid
    resolver = baseline_module.floor_arm.w.resolve
    candidates = []
    for ordinal, entry_value in enumerate(entries):
        entry = int(entry_value)
        key = entry, float(stop_pct)
        if key not in cache:
            exit_at, price, code = resolver(
                entry, float(activation_pct), float(giveback_pct), float(stop_pct), None,
            )
            fill = float(grid.OPEN[entry]) * (1 + grid.SLIP)
            armed = baseline_module.research.first_hit(
                entry, fill * (1 + float(activation_pct) / 100), True,
            )
            arm_index = int(armed) if armed >= 0 and armed <= int(exit_at) else None
            cache[key] = int(exit_at), float(price), int(code), arm_index
        exit_at, price, code, arm_index = cache[key]
        candidates.append(CandidateTrade(
            entry=entry, exit=exit_at, exit_price=price, source="drop_rebound",
            exit_code=code,
            candidate_id=f"drop:{lookback}m:{fall_pct:g}%:{stop_pct:g}%:{market.times[entry].isoformat()}:{ordinal}",
            exit_kind=_exit_kind(code), arm_index=arm_index,
        ))
    return candidates


def _ratio(result: ReplayResult) -> float:
    drawdown = abs(float(result.summary["maximum_drawdown_usd"]))
    return float(result.summary["net_profit"]) / drawdown if drawdown else float("inf")


def _grid_row(result: ReplayResult, lookback: int, fall_pct: float, stop_pct: float) -> dict:
    trades = result.trades
    return {
        "lookback_minutes": lookback, "fall_pct": fall_pct, "stop_pct": stop_pct,
        "signals": result.summary["candidate_count"], "trades": result.summary["trades"],
        "profit": result.summary["net_profit"], "win_rate_pct": result.summary["win_rate_pct"],
        "average_win": result.summary["average_win"], "average_loss": result.summary["average_loss"],
        "profit_factor": result.summary["profit_factor"],
        "max_drawdown_pct": result.summary["maximum_drawdown_pct"],
        "max_drawdown_usd": result.summary["maximum_drawdown_usd"],
        "profit_to_drawdown": _ratio(result),
        "arm_rate_pct": 100 * trades.arm_index.notna().mean() if len(trades) else 0.0,
    }


def _neighbour_keys(selected: tuple[int, float, float], lookbacks: list[int], falls: list[float],
                    stops: list[float]) -> set[tuple[int, float, float]]:
    li, fi, si = lookbacks.index(selected[0]), falls.index(selected[1]), stops.index(selected[2])
    keys = {selected}
    for axis, position, values in ((0, li, lookbacks), (1, fi, falls), (2, si, stops)):
        for offset in (-1, 1):
            other = position + offset
            if 0 <= other < len(values):
                key = list(selected)
                key[axis] = values[other]
                keys.add(tuple(key))
    return keys


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    market, base_candidates, windows = baseline_module.build_baseline()
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    base_results = {
        name: replay_portfolio(base_candidates, market, *windows[name], portfolio) for name in names
    }
    _assert_expected(base_results["full"].summary, baseline_config["acceptance"],
                     float(baseline_config["acceptance_tolerance"]))

    signal = experiment["signal"]
    exit_rule = experiment["exit"]
    search = experiment["search"]
    lookbacks = [int(value) for value in signal["lookback_minutes"]]
    falls = [float(value) for value in signal["fall_percentages"]]
    stops = [float(value) for value in exit_rule["protective_stop_percentages"]]
    activation = float(exit_rule["activation_pct_from_entry_fill"])
    giveback = float(exit_rule["giveback_of_open_profit_pct"])
    entries_by_signal = {
        (lookback, fall): drop_entries(market.close, lookback, fall)
        for lookback in lookbacks for fall in falls
    }
    cache: dict[tuple[int, float], tuple[int, float, int, int | None]] = {}
    books: dict[tuple[int, float, float], list[CandidateTrade]] = {}
    grid_rows = []
    selection_start, selection_end = windows[str(search["selection_window"])]
    total = len(lookbacks) * len(falls) * len(stops)
    completed = 0
    for lookback in lookbacks:
        for fall in falls:
            entries = entries_by_signal[(lookback, fall)]
            for stop in stops:
                key = lookback, fall, stop
                book = drop_candidates(
                    entries, market, lookback, fall, stop, activation, giveback, cache,
                )
                books[key] = book
                result = replay_portfolio(book, market, selection_start, selection_end, portfolio)
                grid_rows.append(_grid_row(result, *key))
                completed += 1
                if completed % 100 == 0:
                    print(f"Selection grid: {completed}/{total}", flush=True)

    grid = pd.DataFrame(grid_rows)
    eligible = grid[grid.trades >= int(search["minimum_selection_trades"])].copy()
    if eligible.empty:
        raise AssertionError("No drop-rebound combination met the minimum selection-trade count")
    eligible = eligible.sort_values(
        ["profit_to_drawdown", "profit", "max_drawdown_pct", "lookback_minutes"],
        ascending=[False, False, False, False],
    )
    winner = eligible.iloc[0]
    selected = int(winner.lookback_minutes), float(winner.fall_pct), float(winner.stop_pct)
    validation_keys = _neighbour_keys(selected, lookbacks, falls, stops)

    validation_rows, window_rows, trade_frames = [], [], []
    evaluated: dict[tuple[int, float, float], dict[str, ReplayResult]] = {}
    for key in sorted(validation_keys):
        evaluated[key] = {
            name: replay_portfolio(books[key], market, *windows[name], portfolio) for name in names
        }
        full = evaluated[key]["full"]
        q = quality(full, 0.25)
        wf_profit = sum(evaluated[key][name].summary["net_profit"] for name in wf_names)
        wf_changes = [evaluated[key][name].summary["net_profit"]
                      - base_results[name].summary["net_profit"] for name in wf_names]
        row = {
            "selected": key == selected, "lookback_minutes": key[0], "fall_pct": key[1],
            "stop_pct": key[2], "profit": full.summary["net_profit"],
            "profit_change": full.summary["net_profit"] - base_results["full"].summary["net_profit"],
            "trades": full.summary["trades"], "headline_win_rate_pct": full.summary["win_rate_pct"],
            "economic_win_rate_pct": q["economic_win_rate_pct"],
            "average_win": full.summary["average_win"], "average_loss": full.summary["average_loss"],
            "profit_factor": full.summary["profit_factor"],
            "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
            "profit_to_drawdown": _ratio(full),
            "later_profit": evaluated[key]["later"].summary["net_profit"],
            "later_change": (evaluated[key]["later"].summary["net_profit"]
                             - base_results["later"].summary["net_profit"]),
            "walk_forward_profit": wf_profit,
            "walk_forward_change": wf_profit - sum(base_results[name].summary["net_profit"] for name in wf_names),
            "walk_forward_windows_improved": sum(change > 0 for change in wf_changes),
            "post_selection_profit": evaluated[key]["post_selection_2026_08_09"].summary["net_profit"],
            "arm_rate_pct": q["arm_rate_pct"],
        }
        acceptance = experiment["acceptance"]
        row["accepted"] = bool(
            key == selected
            and row["profit_change"] > acceptance["full_profit_change_gt"]
            and row["later_change"] > acceptance["later_profit_change_gt"]
            and row["walk_forward_change"] > acceptance["walk_forward_profit_change_gt"]
            and row["walk_forward_windows_improved"] >= acceptance["minimum_walk_forward_windows_improved"]
            and row["average_loss"] >= base_results["full"].summary["average_loss"]
            and row["max_drawdown_pct"] >= base_results["full"].summary["maximum_drawdown_pct"]
        )
        validation_rows.append(row)
        trade_frames.append(full.trades.assign(
            lookback_minutes=key[0], fall_pct=key[1], stop_pct=key[2], selected=key == selected,
        ))
        for name in names:
            window_rows.append({
                "lookback_minutes": key[0], "fall_pct": key[1], "stop_pct": key[2],
                "selected": key == selected, "window": name,
                "profit": evaluated[key][name].summary["net_profit"],
                "base_profit": base_results[name].summary["net_profit"],
                "profit_change": (evaluated[key][name].summary["net_profit"]
                                  - base_results[name].summary["net_profit"]),
            })

    validation = pd.DataFrame(validation_rows).sort_values(
        ["selected", "profit"], ascending=[False, False]
    )
    selected_row = validation[validation.selected].iloc[0]
    base = base_results["full"].summary
    base_quality = quality(base_results["full"], 0.25)
    base_row = {
        "variant": CONTROL, "profit": base["net_profit"], "trades": base["trades"],
        "headline_win_rate_pct": base["win_rate_pct"],
        "economic_win_rate_pct": base_quality["economic_win_rate_pct"],
        "average_win": base["average_win"], "average_loss": base["average_loss"],
        "profit_factor": base["profit_factor"], "max_drawdown_pct": base["maximum_drawdown_pct"],
        "profit_to_drawdown": _ratio(base_results["full"]),
    }
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    grid.to_csv(output / "selection_grid.csv", index=False)
    validation.to_csv(output / "selected_and_neighbours.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.concat(trade_frames, ignore_index=True).to_csv(output / "validation_trades.csv", index=False)
    summary = {
        "base": base_row, "selected": selected_row.to_dict(),
        "selection_combinations": len(grid), "eligible_selection_combinations": len(eligible),
        "decision": "accept" if bool(selected_row.accepted) else "reject",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(base_row, selected_row, validation, activation, giveback))
    return output


def _report(base: dict, selected: pd.Series, neighbours: pd.DataFrame,
            activation: float, giveback: float) -> str:
    decision = "ACCEPT" if bool(selected.accepted) else "REJECT"
    neighbour_pass = int((neighbours.profit_change > 0).sum())
    return f"""# ETH rolling-drop + Mode B experiment

## Result: {decision}

The earlier-period search selected: **{int(selected.lookback_minutes)}-minute rolling high, {selected.fall_pct:g}% fall, −{selected.stop_pct:g}% stop**. Buy at the next minute open; arm the Mode B trail at **+{activation:g}%** and give back **{giveback:g}%** of peak open profit.

| Metric | Current ETH base | Selected drop-rebound | Change |
|---|---:|---:|---:|
| Profit | ${base['profit']:.2f} | ${selected.profit:.2f} | ${selected.profit_change:+.2f} |
| Trades | {base['trades']} | {int(selected.trades)} | {int(selected.trades) - int(base['trades']):+d} |
| Headline win rate | {base['headline_win_rate_pct']:.1f}% | {selected.headline_win_rate_pct:.1f}% | {selected.headline_win_rate_pct - base['headline_win_rate_pct']:+.1f} pp |
| Economic win rate | {base['economic_win_rate_pct']:.1f}% | {selected.economic_win_rate_pct:.1f}% | {selected.economic_win_rate_pct - base['economic_win_rate_pct']:+.1f} pp |
| Average win | ${base['average_win']:.2f} | ${selected.average_win:.2f} | ${selected.average_win - base['average_win']:+.2f} |
| Average loss | ${base['average_loss']:.2f} | ${selected.average_loss:.2f} | ${selected.average_loss - base['average_loss']:+.2f} |
| Drawdown | {base['max_drawdown_pct']:.2f}% | {selected.max_drawdown_pct:.2f}% | {selected.max_drawdown_pct - base['max_drawdown_pct']:+.2f} pp |
| Profit / drawdown | {base['profit_to_drawdown']:.2f} | {selected.profit_to_drawdown:.2f} | {selected.profit_to_drawdown - base['profit_to_drawdown']:+.2f} |

Validation: later-period change **${selected.later_change:+.2f}**; walk-forward change **${selected.walk_forward_change:+.2f}**, improving **{int(selected.walk_forward_windows_improved)}/6** windows. The selected setting and its immediate neighbours produced positive full-history changes in **{neighbour_pass}/{len(neighbours)}** cases.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXPERIMENT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output)
    print((output / "REPORT.md").read_text())
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
