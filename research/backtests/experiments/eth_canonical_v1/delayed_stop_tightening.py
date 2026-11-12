"""ETH experiment: tighten the protective stop after a setup has demonstrably failed."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .confirmation_quality import quality
from .engine import CandidateTrade, MarketData, ReplayResult, replay_portfolio
from .failure_exit import checkpoint_index, setup
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_delayed_stop_tightening_v1.json"
LABELS = {
    "tighten_to_minus_3_0": "Tighten to -3.0%",
    "tighten_to_minus_2_5": "Tighten to -2.5%",
    "swing_low_buffer_capped_3_0": "Swing low -0.25%, capped at -3.0%",
}


def tightened_stop_level(fill: float, original_stop_pct: float, variant: dict,
                         post_entry_low: float) -> float:
    """Return a stop that can only be tighter than the original protective stop."""
    original = fill * (1 - original_stop_pct / 100)
    if variant["type"] == "fixed_from_entry":
        proposed = fill * (1 - float(variant["stop_pct"]) / 100)
    elif variant["type"] == "post_entry_swing_low":
        swing = post_entry_low * (1 - float(variant["buffer_pct"]) / 100)
        cap = fill * (1 - float(variant["maximum_stop_distance_pct"]) / 100)
        proposed = max(swing, cap)
    else:
        raise ValueError(f"Unknown stop type: {variant['type']}")
    return max(original, proposed)


def apply_tightening(candidates: list[CandidateTrade], market: MarketData, references: dict,
                     ema_24h: np.ndarray, experiment: dict, variant: dict
                     ) -> tuple[list[CandidateTrade], pd.DataFrame, dict]:
    """Tighten eligible Dip/Pullback stops from the minute after the 12h checkpoint."""
    grid = baseline_module.grid
    scope = set(experiment["scope"])
    hours = int(experiment["checkpoint_hours"])
    maximum_mfe = float(experiment["eligibility"]["maximum_favorable_excursion_pct_lt"])
    changed: list[CandidateTrade] = []
    diagnostics = []
    funnel = {
        "source_candidates": 0, "survived_to_checkpoint": 0, "unarmed": 0,
        "low_progress": 0, "reference_failed": 0, "tightened_stop_hit": 0,
    }
    by_source = {source: {key: 0 for key in funnel} for source in sorted(scope)}

    for candidate in candidates:
        if candidate.source not in scope:
            changed.append(candidate)
            continue
        source_funnel = by_source[candidate.source]
        funnel["source_candidates"] += 1
        source_funnel["source_candidates"] += 1
        check = checkpoint_index(market.times, candidate.entry, hours)
        if check is None or candidate.exit <= check:
            changed.append(candidate)
            continue
        funnel["survived_to_checkpoint"] += 1
        source_funnel["survived_to_checkpoint"] += 1
        fill = float(grid.OPEN[candidate.entry]) * (1 + grid.SLIP)
        peak = float(np.max(grid.HIGH[candidate.entry:check + 1]))
        mfe_pct = 100 * (peak / fill - 1)
        if candidate.arm_index is not None and candidate.arm_index <= check:
            changed.append(candidate)
            continue
        funnel["unarmed"] += 1
        source_funnel["unarmed"] += 1
        if mfe_pct >= maximum_mfe:
            changed.append(candidate)
            continue
        funnel["low_progress"] += 1
        source_funnel["low_progress"] += 1
        reference = (float(ema_24h[check]) if candidate.source == "pullback"
                     else float(references["dip"][candidate.entry]))
        checkpoint_close = float(grid.CLOSE[check])
        if checkpoint_close >= reference:
            changed.append(candidate)
            continue
        funnel["reference_failed"] += 1
        source_funnel["reference_failed"] += 1
        post_entry_low = float(np.min(grid.LOW[candidate.entry:check + 1]))
        stop = tightened_stop_level(fill, 4.5, variant, post_entry_low)
        start, end = check + 1, candidate.exit + 1
        hits = np.flatnonzero(grid.LOW[start:end] <= stop)
        replacement = candidate
        hit = None
        if len(hits):
            hit = start + int(hits[0])
            replacement = replace(
                candidate, exit=hit, exit_price=min(stop, float(grid.OPEN[hit])),
                exit_code=2, exit_kind="protective_stop",
            )
            funnel["tightened_stop_hit"] += 1
            source_funnel["tightened_stop_hit"] += 1
        changed.append(replacement)
        diagnostics.append({
            "variant": variant["name"], "candidate_id": candidate.candidate_id,
            "source": candidate.source, "entry_index": candidate.entry,
            "entry_time": market.times[candidate.entry], "checkpoint_index": check,
            "checkpoint_time": market.times[check], "mfe_pct": mfe_pct,
            "checkpoint_close": checkpoint_close, "failure_reference": reference,
            "post_entry_low": post_entry_low, "tightened_stop": stop,
            "tightened_stop_distance_pct": 100 * (stop / fill - 1),
            "tightened_exit_index": hit, "tightened_exit_time": market.times[hit] if hit is not None else None,
            "baseline_exit_index": candidate.exit, "baseline_exit_kind": candidate.exit_kind,
        })
    funnel["by_source"] = by_source
    return changed, pd.DataFrame(diagnostics), funnel


def _trade_effects(baseline: ReplayResult, variant: ReplayResult, diagnostics: pd.DataFrame) -> dict:
    triggered = diagnostics[diagnostics.tightened_exit_index.notna()] if len(diagnostics) else diagnostics
    ids = set(triggered.candidate_id) if len(triggered) else set()
    base = baseline.trades[baseline.trades.candidate_id.isin(ids)].set_index("candidate_id")
    changed = variant.trades[variant.trades.candidate_id.isin(ids)].set_index("candidate_id")
    shared = base.index.intersection(changed.index)
    direct = changed.loc[shared, "pnl"] - base.loc[shared, "pnl"]
    baseline_ids, variant_ids = set(baseline.trades.candidate_id), set(variant.trades.candidate_id)
    replacements = variant.trades[variant.trades.candidate_id.isin(variant_ids - baseline_ids)]
    displaced = baseline.trades[baseline.trades.candidate_id.isin(baseline_ids - variant_ids)]
    return {
        "eligible_filled_trades": int(len(shared)),
        "baseline_recoveries_cut": int((base.loc[shared, "pnl"] > 0).sum()),
        "direct_trade_change": float(direct.sum()),
        "direct_improvement": float(direct.clip(lower=0).sum()),
        "direct_damage": float((-direct.clip(upper=0)).sum()),
        "replacement_trades": int(len(replacements)),
        "replacement_pnl": float(replacements.pnl.sum()) if len(replacements) else 0.0,
        "displaced_trades": int(len(displaced)),
        "displaced_baseline_pnl": float(displaced.pnl.sum()) if len(displaced) else 0.0,
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
    market, candidates, windows, references, ema_24h = setup()
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
        "protective_stops": bq["protective_stops"],
        "protective_stop_rate_pct": bq["protective_stop_rate_pct"],
        "max_drawdown_pct": baseline_results["full"].summary["maximum_drawdown_pct"],
        "walk_forward_profit": sum(baseline_results[name].summary["net_profit"] for name in wf_names),
        "post_selection_profit": baseline_results["post_selection_2026_08_09"].summary["net_profit"],
    }

    rows, window_rows, family_rows, diagnostic_frames, trade_frames, funnel_rows = [], [], [], [], [], []
    for variant in experiment["variants"]:
        altered, diagnostics, funnel = apply_tightening(
            candidates, market, references, ema_24h, experiment, variant
        )
        results = {name: replay_portfolio(altered, market, *windows[name], portfolio) for name in names}
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
            "eligible_candidates": funnel["reference_failed"],
            "tightened_stop_hits": funnel["tightened_stop_hit"],
            **_trade_effects(baseline_results["full"], full, diagnostics),
        }
        row["passed"] = _passed(row, baseline, experiment["acceptance"])
        rows.append(row)
        if len(diagnostics):
            diagnostic_frames.append(diagnostics)
        trades = full.trades.copy()
        trades.insert(0, "variant", variant["name"])
        trade_frames.append(trades)
        for source, values in funnel["by_source"].items():
            funnel_rows.append({"variant": variant["name"], "source": source, **values})
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
    pd.DataFrame(funnel_rows).to_csv(output / "condition_funnel.csv", index=False)
    (pd.concat(diagnostic_frames, ignore_index=True) if diagnostic_frames else pd.DataFrame()).to_csv(
        output / "tightened_candidates.csv", index=False
    )
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
        "# ETH delayed stop-tightening experiment", "", f"## Verdict: {verdict}", "",
        f"Baseline: **${baseline['profit']:.2f} profit · {baseline['trades']} trades · "
        f"{baseline['economic_win_rate_pct']:.1f}% economic winners · ${baseline['average_loss']:.2f} "
        f"average loss · {baseline['max_drawdown_pct']:.2f}% drawdown**", "",
        "At 12 hours, only unarmed Dip/Pullback lots with MFE below +0.5% and a failed original setup receive the tighter stop.", "",
        "| Tightened stop | Profit | Change | Trades | Economic wins | Avg win | Avg loss | Stop rate | Drawdown | WF change | WF improved | Eligible / hit | Recoveries cut | Pass |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in frame.itertuples():
        lines.append(
            f"| {row.label} | ${row.profit:.2f} | ${row.profit_change:+.2f} | {row.trades} ({row.trade_change:+d}) | "
            f"{row.economic_win_rate_pct:.1f}% | ${row.average_win:.2f} | ${row.average_loss:.2f} | "
            f"{row.protective_stops}/{row.trades} ({row.protective_stop_rate_pct:.1f}%) | "
            f"{row.max_drawdown_pct:.2f}% | ${row.walk_forward_change:+.2f} | {row.wf_windows_improved}/6 | "
            f"{row.eligible_candidates}/{row.tightened_stop_hits} | {row.baseline_recoveries_cut} | "
            f"{'YES' if row.passed else 'NO'} |"
        )
    best = frame.sort_values("profit_change", ascending=False).iloc[0]
    lines += [
        "", "## Decision", "",
        (f"**Advance `{passed.iloc[0].variant}` to protected forward testing; do not deploy directly.**"
         if len(passed) else "**Keep the live −4.5% Dip/Pullback stop behavior unchanged.**"), "",
        f"The best full-history variant was **{best.label}**: profit changed **${best.profit_change:+.2f}**, "
        f"economic win rate changed **{best.economic_win_rate_pct - baseline['economic_win_rate_pct']:+.1f} points**, "
        f"average loss changed **${best.average_loss - baseline['average_loss']:+.2f}**, drawdown changed "
        f"**{best.max_drawdown_pct - baseline['max_drawdown_pct']:+.2f} points**, and walk-forward profit "
        f"changed **${best.walk_forward_change:+.2f}** across **{int(best.wf_windows_improved)}/6** improved windows.", "",
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
