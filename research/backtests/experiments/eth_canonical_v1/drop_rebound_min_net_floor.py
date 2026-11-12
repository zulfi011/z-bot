"""Test causal post-cost minimum exits for the ETH rolling-drop Mode B add-on."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .drop_rebound_addon_quality import _metrics
from .drop_rebound_mode_b import drop_candidates, drop_entries
from .drop_rebound_uptrend import _evaluate, _row
from .engine import CandidateTrade
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = (
    STAGE2_ROOT / "config" / "experiments" / "eth_drop_rebound_min_net_floor_v1.json"
)


def raw_exit_for_net_return(entry_fill: float, net_return_pct: float, fee: float,
                            slippage: float) -> float:
    """Raw sell price that produces the requested return after modeled round-trip costs."""
    return (
        float(entry_fill) * (1 + float(fee)) * (1 + float(net_return_pct) / 100)
        / ((1 - float(slippage)) * (1 - float(fee)))
    )


def resolve_with_net_floor(entry: int, activation_pct: float, giveback_pct: float,
                           stop_pct: float, net_floor_pct: float, fee: float,
                           slippage: float) -> tuple[int, float, int, int | None]:
    """Resolve one trade without pretending an above-market floor can fill immediately."""
    grid = baseline_module.grid
    research = baseline_module.research
    last = len(grid.CLOSE) - 1
    fill = float(grid.OPEN[entry]) * (1 + slippage)
    stop_level = fill * (1 - stop_pct / 100)
    armed = int(research.first_hit(entry, fill * (1 + activation_pct / 100), True))
    arm_index = armed if armed >= 0 else None
    first_stop = int(research.first_hit(entry, stop_level, False, None if armed < 0 else armed))
    if first_stop >= 0 and (armed < 0 or first_stop <= armed):
        return first_stop, min(stop_level, float(grid.OPEN[first_stop])), 2, arm_index
    if armed < 0:
        return last, float(grid.CLOSE[last]), 3, None

    floor_level = raw_exit_for_net_return(fill, net_floor_pct, fee, slippage)
    floor_reached = int(research.first_hit(armed, floor_level, True))
    stop_until = None if floor_reached < 0 else floor_reached
    post_arm_stop = int(research.first_hit(armed + 1, stop_level, False, stop_until))
    if post_arm_stop >= 0:
        return post_arm_stop, min(stop_level, float(grid.OPEN[post_arm_stop])), 2, arm_index
    if floor_reached < 0:
        return last, float(grid.CLOSE[last]), 3, arm_index

    # The floor is known only after the candle closes and therefore becomes executable next minute.
    position = floor_reached + 1
    peak = float(np.max(grid.HIGH[armed:position]))
    keep = 1 - giveback_pct / 100
    while position <= last:
        end = min(position + 2048, last + 1)
        chunk_high = grid.HIGH[position:end]
        prior_peaks = np.maximum.accumulate(np.r_[peak, chunk_high[:-1]])
        trail_levels = fill + (prior_peaks - fill) * keep
        levels = np.maximum(trail_levels, floor_level)
        hits = np.flatnonzero(grid.LOW[position:end] <= levels)
        if len(hits):
            offset = int(hits[0])
            index = position + offset
            return index, min(float(levels[offset]), float(grid.OPEN[index])), 1, arm_index
        peak = max(peak, float(np.max(chunk_high)))
        position = end
    return last, float(grid.CLOSE[last]), 3, arm_index


def floor_candidates(entries: np.ndarray, net_floor_pct: float, rule: dict,
                     fee: float, slippage: float) -> list[CandidateTrade]:
    market_times = baseline_module.grid.TIMES
    candidates = []
    for ordinal, value in enumerate(entries):
        entry = int(value)
        exit_at, price, code, arm_index = resolve_with_net_floor(
            entry, float(rule["activation_pct"]), float(rule["giveback_pct"]),
            float(rule["protective_stop_pct"]), net_floor_pct, fee, slippage,
        )
        candidates.append(CandidateTrade(
            entry=entry, exit=exit_at, exit_price=price, source="drop_rebound",
            exit_code=code,
            candidate_id=(f"drop:min-net-{net_floor_pct:g}:{market_times[entry].isoformat()}:{ordinal}"),
            exit_kind={1: "minimum_net_or_trailing", 2: "protective_stop", 3: "data_endpoint"}[code],
            arm_index=arm_index,
        ))
    return candidates


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    market, base_candidates, windows = baseline_module.build_baseline()
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    base_results = _evaluate(base_candidates, market, windows, names, portfolio)
    _assert_expected(base_results["full"].summary, baseline_config["acceptance"],
                     float(baseline_config["acceptance_tolerance"]))
    base = _metrics(base_results["full"])

    rule = experiment["frozen_drop_rule"]
    entries = drop_entries(market.close, int(rule["lookback_minutes"]), float(rule["fall_pct"]))
    reference_cache: dict[tuple[int, float], tuple[int, float, int, int | None]] = {}
    reference_addon = drop_candidates(
        entries, market, int(rule["lookback_minutes"]), float(rule["fall_pct"]),
        float(rule["protective_stop_pct"]), float(rule["activation_pct"]),
        float(rule["giveback_pct"]), reference_cache,
    )
    candidate_sets = {"current_no_net_floor": base_candidates + reference_addon}
    for net_floor in experiment["minimum_net_exit_percentages"]:
        label = f"minimum_net_{float(net_floor):.2f}pct"
        candidate_sets[label] = base_candidates + floor_candidates(
            entries, float(net_floor), rule, portfolio.fee_per_side, portfolio.slippage_per_side,
        )

    results = {
        label: _evaluate(candidates, market, windows, names, portfolio)
        for label, candidates in candidate_sets.items()
    }
    rows = []
    for label, variant_results in results.items():
        row = _row(
            label, variant_results, base_results, base, wf_names,
            label != "current_no_net_floor", experiment["acceptance"],
        )
        addon = variant_results["full"].trades[
            variant_results["full"].trades.source == "drop_rebound"
        ]
        row["floor_or_trailing_exits"] = int(
            (addon.exit_kind == "minimum_net_or_trailing").sum()
        )
        row["protective_stops"] = int((addon.exit_kind == "protective_stop").sum())
        rows.append(row)
    variants = pd.DataFrame(rows)
    accepted = variants[variants.accepted]
    decision = "accept" if len(accepted) else "reject"
    tested = variants[variants.variant != "current_no_net_floor"]
    winner = (accepted.sort_values("profit", ascending=False).iloc[0] if len(accepted)
              else tested.sort_values("profit", ascending=False).iloc[0])

    window_rows = []
    for label, variant_results in results.items():
        for window in names:
            window_rows.append({
                "variant": label, "window": window,
                "profit": variant_results[window].summary["net_profit"],
                "base_profit": base_results[window].summary["net_profit"],
                "profit_change": (variant_results[window].summary["net_profit"]
                                  - base_results[window].summary["net_profit"]),
                "trades": variant_results[window].summary["trades"],
                "win_rate_pct": variant_results[window].summary["win_rate_pct"],
            })

    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    variants.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    for label, variant_results in results.items():
        variant_results["full"].trades.to_csv(output / f"trades_{label}.csv", index=False)
    summary = {"decision": decision, "base": base, "best_variant": winner.to_dict()}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(base, variants, decision))
    return output


def _report(base: dict, variants: pd.DataFrame, decision: str) -> str:
    lines = [
        "# ETH drop-rebound minimum-net exit experiment", "", f"## Result: **{decision.upper()}**", "",
        "All variants are additions behind the unchanged current ETH strategy. A floor becomes active "
        "only after its price is actually reached; this avoids assuming an impossible above-market stop fill.", "",
        "| Variant | Extra trades | Profit | Change | Overall WR | Add-on WR | Add-on avg win | Add-on avg loss | Later | WF change | WF wins | Pass |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in variants.itertuples(index=False):
        lines.append(
            f"| {row.variant} | {int(row.additional_trades):+d} | ${row.profit:.2f} | "
            f"${row.profit_change:+.2f} | {row.headline_win_rate_pct:.1f}% | "
            f"{row.addon_win_rate_pct:.1f}% | ${row.addon_average_win:.2f} | "
            f"${row.addon_average_loss:.2f} | ${row.later_profit_change:+.2f} | "
            f"${row.walk_forward_profit_change:+.2f} | {int(row.walk_forward_windows_improved)}/6 | "
            f"{'yes' if row.accepted else 'no'} |"
        )
    lines.extend([
        "", "## Current ETH base", "",
        f"Profit **${base['profit']:.2f}**, {int(base['trades'])} trades, "
        f"{base['headline_win_rate_pct']:.1f}% headline win rate, average win "
        f"**${base['average_win']:.2f}** and average loss **${base['average_loss']:.2f}**.", "",
        "A variant passes only if it keeps overall win rate at 75%+, adds at least 20 trades, "
        "improves full/later/walk-forward profit and at least four of six walk-forward windows, "
        "without worsening average loss or drawdown.", "",
        "This is local ETH research only. No live bot or server files were changed.",
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
