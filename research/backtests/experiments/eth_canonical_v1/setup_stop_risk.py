"""ETH experiment: Dip stops below episode structure with capped fixed-dollar-risk sizing."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .confirmation_quality import dip_signals, quality
from .engine import CandidateTrade, ReplayResult, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_setup_stop_risk_v1.json"
LABELS = {
    "episode_low_buffer_0_20": "Episode low −0.20%",
    "episode_low_buffer_0_25": "Episode low −0.25%",
    "episode_low_buffer_0_30": "Episode low −0.30%",
}


def structural_stop(fill: float, episode_low: float, buffer_pct: float,
                    minimum_distance_pct: float, maximum_distance_pct: float
                    ) -> tuple[float | None, float]:
    """Return (stop, distance). A distance wider than the frozen maximum rejects the setup."""
    structural_level = episode_low * (1 - buffer_pct / 100)
    structural_distance = 100 * (1 - structural_level / fill)
    if structural_distance > maximum_distance_pct:
        return None, structural_distance
    distance = max(minimum_distance_pct, structural_distance)
    return fill * (1 - distance / 100), distance


def _dip_episode_ranges(raw: pd.DataFrame, strategy: dict) -> dict[int, tuple[int, int]]:
    signals, _ = dip_signals(raw, strategy, "current_green")
    ranges = {}
    for signal in signals:
        start = signal.entry - (signal.confirmation - signal.origin + 1) * strategy["minutes"]
        ranges[signal.entry] = (int(start), int(signal.entry))
    return ranges


def build_variant(candidates: list[CandidateTrade], raw: pd.DataFrame, strategy: dict,
                  experiment: dict, variant: dict
                  ) -> tuple[list[CandidateTrade], dict[str, float], dict[str, float], pd.DataFrame, dict]:
    """Replace accepted Dip stops and return candidate-specific order targets and stop distances."""
    grid = baseline_module.grid
    ranges = _dip_episode_ranges(raw, strategy)
    expected = {candidate.entry for candidate in candidates if candidate.source == "dip"}
    if set(ranges) != expected:
        raise AssertionError("Structural Dip episodes do not match the frozen baseline candidates")
    accepted: list[CandidateTrade] = []
    sizes: dict[str, float] = {}
    distances: dict[str, float] = {}
    diagnostics = []
    counts = {"dip_candidates": 0, "accepted": 0, "rejected_wider_than_4_5": 0,
              "minimum_distance_applied": 0, "structural_stop_hits": 0}
    minimum = float(experiment["minimum_stop_distance_pct"])
    maximum = float(experiment["maximum_stop_distance_pct"])
    risk = float(experiment["planned_risk_usd"])
    cap = float(experiment["maximum_order_usd"])
    buffer_pct = float(variant["buffer_pct"])

    for candidate in candidates:
        if candidate.source != "dip":
            accepted.append(candidate)
            sizes[candidate.candidate_id] = 100.0
            continue
        counts["dip_candidates"] += 1
        start, entry = ranges[candidate.entry]
        episode_low = float(np.min(grid.LOW[start:entry]))
        fill = float(grid.OPEN[entry]) * (1 + grid.SLIP)
        raw_distance = 100 * (1 - episode_low * (1 - buffer_pct / 100) / fill)
        stop, distance = structural_stop(fill, episode_low, buffer_pct, minimum, maximum)
        if stop is None:
            counts["rejected_wider_than_4_5"] += 1
            diagnostics.append({
                "variant": variant["name"], "candidate_id": candidate.candidate_id,
                "entry_index": entry, "entry_time": grid.TIMES[entry], "episode_start_index": start,
                "episode_start_time": grid.TIMES[start], "episode_low": episode_low,
                "entry_fill": fill, "raw_structural_distance_pct": raw_distance,
                "used_stop_distance_pct": None, "stop_price": None, "target_order_usd": None,
                "status": "rejected_wider_than_4_5", "structural_stop_hit_index": None,
            })
            continue
        counts["accepted"] += 1
        if raw_distance < minimum:
            counts["minimum_distance_applied"] += 1
        target_size = min(cap, risk / (distance / 100))
        hit = None
        replacement = candidate
        hits = np.flatnonzero(grid.LOW[entry + 1:candidate.exit + 1] <= stop)
        if len(hits):
            hit = entry + 1 + int(hits[0])
            replacement = replace(
                candidate, exit=hit, exit_price=min(stop, float(grid.OPEN[hit])),
                exit_code=2, exit_kind="protective_stop",
            )
            counts["structural_stop_hits"] += 1
        accepted.append(replacement)
        sizes[candidate.candidate_id] = target_size
        distances[candidate.candidate_id] = distance
        diagnostics.append({
            "variant": variant["name"], "candidate_id": candidate.candidate_id,
            "entry_index": entry, "entry_time": grid.TIMES[entry], "episode_start_index": start,
            "episode_start_time": grid.TIMES[start], "episode_low": episode_low,
            "entry_fill": fill, "raw_structural_distance_pct": raw_distance,
            "used_stop_distance_pct": distance, "stop_price": stop,
            "target_order_usd": target_size, "status": "accepted",
            "structural_stop_hit_index": hit,
        })
    return accepted, sizes, distances, pd.DataFrame(diagnostics), counts


def _sizer(sizes: dict[str, float]):
    return lambda candidate: sizes[candidate.candidate_id]


def _effects(baseline: ReplayResult, variant: ReplayResult, diagnostics: pd.DataFrame) -> dict:
    rejected_ids = set(diagnostics.loc[diagnostics.status == "rejected_wider_than_4_5", "candidate_id"])
    hit_ids = set(diagnostics.loc[diagnostics.structural_stop_hit_index.notna(), "candidate_id"])
    base_rejected = baseline.trades[baseline.trades.candidate_id.isin(rejected_ids)]
    rejected_winners = base_rejected[base_rejected.pnl > 0]
    base_hits = baseline.trades[baseline.trades.candidate_id.isin(hit_ids)].set_index("candidate_id")
    variant_hits = variant.trades[variant.trades.candidate_id.isin(hit_ids)].set_index("candidate_id")
    shared = base_hits.index.intersection(variant_hits.index)
    cut = base_hits.loc[shared]
    baseline_ids, variant_ids = set(baseline.trades.candidate_id), set(variant.trades.candidate_id)
    replacements = variant.trades[variant.trades.candidate_id.isin(variant_ids - baseline_ids)]
    displaced = baseline.trades[baseline.trades.candidate_id.isin(baseline_ids - variant_ids)]
    return {
        "rejected_baseline_fills": int(len(base_rejected)),
        "rejected_profitable_baseline_fills": int(len(rejected_winners)),
        "rejected_profitable_baseline_pnl": float(rejected_winners.pnl.sum()),
        "structural_stop_filled_trades": int(len(shared)),
        "recoveries_cut_by_structural_stop": int((cut.pnl > 0).sum()),
        "replacement_trades": int(len(replacements)),
        "replacement_pnl": float(replacements.pnl.sum()) if len(replacements) else 0.0,
        "displaced_trades": int(len(displaced)),
        "displaced_baseline_pnl": float(displaced.pnl.sum()) if len(displaced) else 0.0,
    }


def _risk_metrics(result: ReplayResult, distances: dict[str, float]) -> dict:
    dip = result.trades[result.trades.source == "dip"].copy()
    dip["stop_distance_pct"] = dip.candidate_id.map(distances)
    dip["planned_stop_risk"] = dip.spend * dip.stop_distance_pct / 100
    return {
        "average_dip_order_usd": float(dip.spend.mean()) if len(dip) else 0.0,
        "average_dip_stop_distance_pct": float(dip.stop_distance_pct.mean()) if len(dip) else 0.0,
        "average_dip_planned_risk_usd": float(dip.planned_stop_risk.mean()) if len(dip) else 0.0,
        "maximum_dip_planned_risk_usd": float(dip.planned_stop_risk.max()) if len(dip) else 0.0,
    }


def _passed(row: dict, baseline: dict, acceptance: dict) -> bool:
    return bool(
        row["profit_change"] > acceptance["full_profit_change_gt"]
        and row["walk_forward_change"] > acceptance["walk_forward_change_gt"]
        and row["wf_windows_improved"] >= acceptance["minimum_walk_forward_windows_improved"]
        and row["economic_win_rate_pct"] >= baseline["economic_win_rate_pct"]
        and row["average_loss"] >= baseline["average_loss"]
        and row["max_drawdown_pct"] >= baseline["max_drawdown_pct"]
    )


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    threshold = float(experiment["economic_winner_threshold_pct"])
    market, candidates, windows = baseline_module.build_baseline()
    raw, _ = baseline_module.compare.load("ETHUSDT")
    strategy = baseline_module.live.load_rule("eth")
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    baseline_results = {
        name: replay_portfolio(candidates, market, *windows[name], portfolio) for name in names
    }
    _assert_expected(
        baseline_results["full"].summary, baseline_config["acceptance"],
        float(baseline_config["acceptance_tolerance"]),
    )
    bq = quality(baseline_results["full"], threshold)
    baseline = {
        "profit": baseline_results["full"].summary["net_profit"],
        "trades": baseline_results["full"].summary["trades"],
        "win_rate_pct": baseline_results["full"].summary["win_rate_pct"],
        "economic_win_rate_pct": bq["economic_win_rate_pct"],
        "average_win": baseline_results["full"].summary["average_win"],
        "average_loss": baseline_results["full"].summary["average_loss"],
        "profit_factor": baseline_results["full"].summary["profit_factor"],
        "max_drawdown_pct": baseline_results["full"].summary["maximum_drawdown_pct"],
        "walk_forward_profit": sum(baseline_results[name].summary["net_profit"] for name in wf_names),
        "post_selection_profit": baseline_results["post_selection_2026_08_09"].summary["net_profit"],
    }

    rows, window_rows, family_rows, diagnostic_frames, trade_frames = [], [], [], [], []
    for variant in experiment["variants"]:
        altered, sizes, distances, diagnostics, counts = build_variant(
            candidates, raw, strategy, experiment, variant
        )
        results = {
            name: replay_portfolio(altered, market, *windows[name], portfolio, lot_sizer=_sizer(sizes))
            for name in names
        }
        full = results["full"]
        q = quality(full, threshold)
        wf_diffs = [results[name].summary["net_profit"] - baseline_results[name].summary["net_profit"]
                    for name in wf_names]
        row = {
            "variant": variant["name"], "label": LABELS[variant["name"]],
            "profit": full.summary["net_profit"],
            "profit_change": full.summary["net_profit"] - baseline["profit"],
            "trades": full.summary["trades"], "trade_change": full.summary["trades"] - baseline["trades"],
            "win_rate_pct": full.summary["win_rate_pct"],
            "economic_win_rate_pct": q["economic_win_rate_pct"],
            "average_win": full.summary["average_win"], "average_loss": full.summary["average_loss"],
            "profit_factor": full.summary["profit_factor"],
            "protective_stops": q["protective_stops"],
            "protective_stop_rate_pct": q["protective_stop_rate_pct"],
            "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
            "walk_forward_profit": sum(results[name].summary["net_profit"] for name in wf_names),
            "walk_forward_change": sum(wf_diffs),
            "wf_windows_improved": sum(value > 0 for value in wf_diffs),
            "post_selection_change": (
                results["post_selection_2026_08_09"].summary["net_profit"]
                - baseline["post_selection_profit"]
            ),
            **counts, **_risk_metrics(full, distances),
            **_effects(baseline_results["full"], full, diagnostics),
        }
        row["passed"] = _passed(row, baseline, experiment["acceptance"])
        rows.append(row)
        diagnostic_frames.append(diagnostics)
        trades = full.trades.copy()
        trades.insert(0, "variant", variant["name"])
        trade_frames.append(trades)
        for source, part in full.trades.groupby("source", sort=True):
            winners, losses = part[part.pnl > 0], part[part.pnl <= 0]
            stops = part[part.exit_kind == "protective_stop"]
            family_rows.append({
                "variant": variant["name"], "source": source, "trades": len(part),
                "profit": part.pnl.sum(), "win_rate_pct": 100 * len(winners) / len(part),
                "average_win": winners.pnl.mean() if len(winners) else 0.0,
                "average_loss": losses.pnl.mean() if len(losses) else 0.0,
                "protective_stops": len(stops), "protective_stop_rate_pct": 100 * len(stops) / len(part),
            })
        for name in names:
            window_rows.append({
                "variant": variant["name"], "window": name,
                "profit": results[name].summary["net_profit"],
                "profit_change": results[name].summary["net_profit"] - baseline_results[name].summary["net_profit"],
                "trades": results[name].summary["trades"],
                "win_rate_pct": results[name].summary["win_rate_pct"],
                "max_drawdown_pct": results[name].summary["maximum_drawdown_pct"],
            })

    frame = pd.DataFrame(rows)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.DataFrame(family_rows).to_csv(output / "results_by_entry_family.csv", index=False)
    pd.concat(diagnostic_frames, ignore_index=True).to_csv(output / "structural_stop_candidates.csv", index=False)
    pd.concat(trade_frames, ignore_index=True).to_csv(output / "variant_trades.csv", index=False)
    (output / "summary.json").write_text(json.dumps({
        "baseline": baseline, "variants": frame.to_dict(orient="records"),
        "accepted_variants": frame.loc[frame.passed, "variant"].tolist(),
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(baseline, frame))
    return output


def _report(baseline: dict, frame: pd.DataFrame) -> str:
    passed = frame[frame.passed]
    verdict = "IMPROVES" if len(passed) else "DOES NOT ROBUSTLY IMPROVE"
    lines = [
        "# ETH setup-based Dip stop with fixed maximum dollar risk", "", f"## Verdict: {verdict}", "",
        f"Baseline: **${baseline['profit']:.2f} profit · {baseline['trades']} trades · "
        f"{baseline['economic_win_rate_pct']:.1f}% economic winners · ${baseline['average_loss']:.2f} "
        f"average loss · {baseline['max_drawdown_pct']:.2f}% drawdown**", "",
        "Each Dip stop sits below the episode low, is restricted to 1.5%–4.5%, and sizes toward $4.50 planned price risk with a $130 cap. Mode C and Pullback remain unchanged.", "",
        "| Structural rule | Profit | Change | Trades | Economic wins | Avg win | Avg loss | Stop rate | Drawdown | WF change | WF improved | Rejected setups | Avg Dip order / risk | Pass |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in frame.itertuples():
        lines.append(
            f"| {row.label} | ${row.profit:.2f} | ${row.profit_change:+.2f} | {row.trades} ({row.trade_change:+d}) | "
            f"{row.economic_win_rate_pct:.1f}% | ${row.average_win:.2f} | ${row.average_loss:.2f} | "
            f"{row.protective_stops}/{row.trades} ({row.protective_stop_rate_pct:.1f}%) | "
            f"{row.max_drawdown_pct:.2f}% | ${row.walk_forward_change:+.2f} | {row.wf_windows_improved}/6 | "
            f"{row.rejected_wider_than_4_5} | ${row.average_dip_order_usd:.2f} / "
            f"${row.average_dip_planned_risk_usd:.2f} | {'YES' if row.passed else 'NO'} |"
        )
    best = frame.sort_values("profit_change", ascending=False).iloc[0]
    lines += [
        "", "## Decision", "",
        (f"**Advance `{passed.iloc[0].variant}` to protected forward testing; do not deploy directly.**"
         if len(passed) else "**Keep the live fixed −4.5% Dip stop and $100 order size unchanged.**"), "",
        f"The best full-history variant was **{best.label}**: profit changed **${best.profit_change:+.2f}**, "
        f"economic win rate changed **{best.economic_win_rate_pct - baseline['economic_win_rate_pct']:+.1f} points**, "
        f"average loss changed **${best.average_loss - baseline['average_loss']:+.2f}**, drawdown changed "
        f"**{best.max_drawdown_pct - baseline['max_drawdown_pct']:+.2f} points**, and walk-forward profit "
        f"changed **${best.walk_forward_change:+.2f}** across **{int(best.wf_windows_improved)}/6** improved windows.", "",
        f"For that variant, the 1.5% minimum distance controlled **{int(best.minimum_distance_applied)}/{int(best.dip_candidates)}** Dip candidates. "
        f"Its structural stop cut **{int(best.recoveries_cut_by_structural_stop)}** baseline recoveries and admitted "
        f"**{int(best.replacement_trades)}** replacement trades.", "",
        "The August–September 2026 period is diagnostic only and was not used for acceptance.",
    ]
    return "\n".join(lines) + "\n"


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
