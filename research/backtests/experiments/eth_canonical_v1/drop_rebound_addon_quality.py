"""Test frozen confirmations for the rolling-drop engine as an ETH base add-on."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .confirmation_quality import quality
from .drop_rebound_mode_b import _ratio, drop_candidates, drop_entries
from .engine import CandidateTrade, ReplayResult, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_drop_rebound_addon_quality_v1.json"


def confirmed_entries(open_: np.ndarray, close: np.ndarray, immediate_entries: np.ndarray,
                      variant: dict) -> np.ndarray:
    """Return causal next-open entries after the frozen post-drop confirmation."""
    if variant["type"] == "immediate_next_minute":
        return np.unique(np.asarray(immediate_entries, dtype=np.int64))

    entries: list[int] = []
    seen: set[int] = set()
    maximum_wait = int(variant["maximum_wait_minutes"])
    for immediate in np.asarray(immediate_entries, dtype=np.int64):
        trigger = int(immediate) - 1
        final_confirmation = min(trigger + maximum_wait, len(close) - 2)
        confirmed = None
        for index in range(trigger + 1, final_confirmation + 1):
            if variant["type"] == "first_green_1m":
                passed = float(close[index]) > float(open_[index])
            elif variant["type"] == "rebound_from_trigger":
                target = float(close[trigger]) * (1 + float(variant["rebound_pct"]) / 100)
                passed = float(close[index]) >= target
            else:
                raise ValueError(f"Unknown confirmation type: {variant['type']}")
            if passed:
                confirmed = index + 1
                break
        if confirmed is not None and confirmed not in seen:
            seen.add(confirmed)
            entries.append(confirmed)
    return np.asarray(entries, dtype=np.int64)


def _metrics(result: ReplayResult, threshold: float = 0.25) -> dict:
    summary = result.summary
    measured = quality(result, threshold)
    addon = result.trades[result.trades.source == "drop_rebound"]
    addon_wins = addon[addon.pnl > 0]
    addon_losses = addon[addon.pnl <= 0]
    return {
        "profit": summary["net_profit"],
        "trades": summary["trades"],
        "headline_win_rate_pct": summary["win_rate_pct"],
        "economic_win_rate_pct": measured["economic_win_rate_pct"],
        "average_win": summary["average_win"],
        "average_loss": summary["average_loss"],
        "profit_factor": summary["profit_factor"],
        "max_drawdown_pct": summary["maximum_drawdown_pct"],
        "profit_to_drawdown": _ratio(result),
        "addon_trades": int(len(addon)),
        "addon_profit": float(addon.pnl.sum()),
        "addon_win_rate_pct": 100 * len(addon_wins) / len(addon) if len(addon) else 0.0,
        "addon_average_win": float(addon_wins.pnl.mean()) if len(addon_wins) else 0.0,
        "addon_average_loss": float(addon_losses.pnl.mean()) if len(addon_losses) else 0.0,
    }


def _accepted(row: dict, base: dict, acceptance: dict) -> bool:
    return bool(
        row["headline_win_rate_pct"] >= acceptance["minimum_combined_headline_win_rate_pct"]
        and row["additional_trades"] >= acceptance["minimum_additional_trades"]
        and row["profit_change"] > acceptance["full_profit_change_gt"]
        and row["later_profit_change"] > acceptance["later_profit_change_gt"]
        and row["walk_forward_profit_change"] > acceptance["walk_forward_profit_change_gt"]
        and row["walk_forward_windows_improved"] >= acceptance["minimum_walk_forward_windows_improved"]
        and row["average_loss"] >= base["average_loss"]
        and row["max_drawdown_pct"] >= base["max_drawdown_pct"]
    )


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
    base = _metrics(base_results["full"])
    base_wf_profit = sum(base_results[name].summary["net_profit"] for name in wf_names)

    rule = experiment["frozen_drop_rule"]
    immediate = drop_entries(market.close, int(rule["lookback_minutes"]), float(rule["fall_pct"]))
    cache: dict[tuple[int, float], tuple[int, float, int, int | None]] = {}
    rows, window_rows, trade_frames = [], [], []
    for variant in experiment["entry_variants"]:
        entries = confirmed_entries(market.open, market.close, immediate, variant)
        addon = drop_candidates(
            entries, market, int(rule["lookback_minutes"]), float(rule["fall_pct"]),
            float(rule["protective_stop_pct"]), float(rule["activation_pct"]),
            float(rule["giveback_pct"]), cache,
        )
        combined = base_candidates + addon
        results = {
            name: replay_portfolio(combined, market, *windows[name], portfolio) for name in names
        }
        full_metrics = _metrics(results["full"])
        later_change = (results["later"].summary["net_profit"]
                        - base_results["later"].summary["net_profit"])
        wf_changes = [
            results[name].summary["net_profit"] - base_results[name].summary["net_profit"]
            for name in wf_names
        ]
        row = {
            "variant": variant["name"],
            "candidate_addon_signals": len(addon),
            **full_metrics,
            "profit_change": full_metrics["profit"] - base["profit"],
            "additional_trades": full_metrics["trades"] - base["trades"],
            "later_profit_change": later_change,
            "walk_forward_profit": sum(results[name].summary["net_profit"] for name in wf_names),
            "walk_forward_profit_change": sum(wf_changes),
            "walk_forward_windows_improved": sum(change > 0 for change in wf_changes),
            "post_selection_profit": results["post_selection_2026_08_09"].summary["net_profit"],
        }
        row["accepted"] = _accepted(row, base, experiment["acceptance"])
        rows.append(row)
        trade_frames.append(results["full"].trades.assign(variant=variant["name"]))
        for name in names:
            window_rows.append({
                "variant": variant["name"], "window": name,
                "profit": results[name].summary["net_profit"],
                "base_profit": base_results[name].summary["net_profit"],
                "profit_change": (results[name].summary["net_profit"]
                                  - base_results[name].summary["net_profit"]),
                "trades": results[name].summary["trades"],
                "win_rate_pct": results[name].summary["win_rate_pct"],
            })

    variants = pd.DataFrame(rows)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    variants.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.concat(trade_frames, ignore_index=True).to_csv(output / "variant_trades.csv", index=False)
    accepted = variants[variants.accepted]
    decision = "accept" if len(accepted) else "reject"
    winner = (accepted.sort_values("profit", ascending=False).iloc[0] if len(accepted)
              else variants.sort_values("profit", ascending=False).iloc[0])
    summary = {"decision": decision, "base": base, "best_variant": winner.to_dict()}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(base, variants, decision, base_wf_profit))
    return output


def _report(base: dict, variants: pd.DataFrame, decision: str, base_wf_profit: float) -> str:
    lines = [
        "# ETH rolling-drop add-on confirmation experiment", "",
        f"## Result: **{decision.upper()}**", "",
        "The current ETH strategy remains unchanged and receives same-minute slot priority.", "",
        "| Variant | Profit | Change | Trades | Extra | Win rate | Add-on WR | Avg loss | WF change | WF wins | Pass |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in variants.itertuples(index=False):
        lines.append(
            f"| {row.variant} | ${row.profit:.2f} | ${row.profit_change:+.2f} | {int(row.trades)} | "
            f"{int(row.additional_trades):+d} | {row.headline_win_rate_pct:.1f}% | "
            f"{row.addon_win_rate_pct:.1f}% | ${row.average_loss:.2f} | "
            f"${row.walk_forward_profit_change:+.2f} | {int(row.walk_forward_windows_improved)}/6 | "
            f"{'yes' if row.accepted else 'no'} |"
        )
    lines.extend([
        "", "## Current base", "",
        f"Profit **${base['profit']:.2f}**, {int(base['trades'])} trades, "
        f"{base['headline_win_rate_pct']:.1f}% headline win rate, average loss "
        f"**${base['average_loss']:.2f}**, walk-forward profit **${base_wf_profit:.2f}**.", "",
        "A variant passes only if it keeps combined win rate at 75%+, adds at least 20 trades, "
        "improves full/later/walk-forward profit, improves at least four of six walk-forward "
        "windows, and does not worsen average loss or drawdown.", "",
        "This is local ETH research only; no live files or server deployment were changed.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXPERIMENT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output)
    summary = json.loads((output / "summary.json").read_text())
    print(f"{summary['decision'].upper()}: {summary['best_variant']['variant']}")
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
