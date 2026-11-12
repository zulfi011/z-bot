"""ETH experiment: measure and exit positions that remain unarmed by fixed ages."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .confirmation_quality import quality
from .engine import CandidateTrade, MarketData, PortfolioConfig, ReplayResult, replay_portfolio
from .failure_exit import checkpoint_index
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_time_to_arm_v1.json"
CONTROL = "baseline"
EXIT_CODE = 8


def apply_unarmed_timeout(candidates: list[CandidateTrade], market: MarketData,
                          hours: int) -> tuple[list[CandidateTrade], pd.DataFrame]:
    """Exit still-open, never-yet-armed candidates at the first tradable minute after the checkpoint."""
    changed, rows = [], []
    for candidate in candidates:
        check = checkpoint_index(market.times, candidate.entry, hours)
        eligible = bool(
            check is not None and candidate.exit > check
            and (candidate.arm_index is None or candidate.arm_index > check)
        )
        if not eligible:
            changed.append(candidate)
            continue
        exit_index = int(check + 1)
        changed.append(replace(
            candidate, exit=exit_index, exit_price=float(market.open[exit_index]),
            exit_code=EXIT_CODE, exit_kind="unarmed_timeout",
        ))
        rows.append({
            "candidate_id": candidate.candidate_id, "source": candidate.source,
            "entry_index": candidate.entry, "entry_time": market.times[candidate.entry],
            "checkpoint_hours": hours, "checkpoint_index": check,
            "checkpoint_time": market.times[check], "timeout_exit_index": exit_index,
            "timeout_exit_time": market.times[exit_index],
            "later_armed": candidate.arm_index is not None and candidate.arm_index > check,
            "original_exit_kind": candidate.exit_kind,
        })
    return changed, pd.DataFrame(rows)


def _direct_diagnostics(
    baseline: ReplayResult, candidates: list[CandidateTrade], eligible: pd.DataFrame,
    market: MarketData, config: PortfolioConfig, threshold: float,
) -> pd.DataFrame:
    if eligible.empty:
        return pd.DataFrame()
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    filled = baseline.trades.merge(eligible, on=["candidate_id", "source"], how="inner")
    if filled.empty:
        return pd.DataFrame()
    exit_raw = market.open[filled.timeout_exit_index.to_numpy(dtype=int)]
    exit_proceeds = (filled.quantity.to_numpy(float) * exit_raw
                     * (1 - config.slippage_per_side) * (1 - config.fee_per_side))
    filled["timeout_pnl"] = exit_proceeds - filled.spend
    filled["direct_pnl_change"] = filled.timeout_pnl - filled.pnl
    filled["eventual_economic_winner"] = filled.return_pct > threshold
    filled["eventual_economic_loser"] = filled.return_pct < -threshold
    filled["eventual_flat"] = ~(filled.eventual_economic_winner | filled.eventual_economic_loser)
    filled["eventual_protective_stop"] = filled.exit_kind == "protective_stop"
    # Recompute from the original candidates to guard against a stale diagnostic column.
    filled["later_armed"] = [
        by_id[row.candidate_id].arm_index is not None
        and by_id[row.candidate_id].arm_index > row.checkpoint_index
        for row in filled.itertuples()
    ]
    return filled


def _cohort_rows(frame: pd.DataFrame, hours: int) -> list[dict]:
    rows = []
    for source, part in [("all", frame), *list(frame.groupby("source", sort=True))]:
        count = len(part)
        rows.append({
            "checkpoint_hours": hours, "source": source, "filled_unarmed": count,
            "later_arm_rate_pct": 100 * part.later_armed.mean() if count else 0.0,
            "eventual_economic_win_rate_pct": 100 * part.eventual_economic_winner.mean() if count else 0.0,
            "eventual_flat_rate_pct": 100 * part.eventual_flat.mean() if count else 0.0,
            "eventual_economic_loss_rate_pct": 100 * part.eventual_economic_loser.mean() if count else 0.0,
            "eventual_protective_stop_rate_pct": 100 * part.eventual_protective_stop.mean() if count else 0.0,
            "baseline_pnl": float(part.pnl.sum()) if count else 0.0,
            "timeout_pnl": float(part.timeout_pnl.sum()) if count else 0.0,
            "direct_pnl_change": float(part.direct_pnl_change.sum()) if count else 0.0,
        })
    return rows


def _ratio(result: ReplayResult) -> float:
    loss = abs(float(result.summary["maximum_drawdown_usd"]))
    return float(result.summary["net_profit"]) / loss if loss else float("inf")


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    market, candidates, windows = baseline_module.build_baseline()
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    threshold = float(experiment["economic_winner_threshold_pct"])

    books = {CONTROL: candidates}
    eligible_frames = {}
    for hours in experiment["checkpoints_hours"]:
        label = f"unarmed_{hours}h"
        books[label], eligible_frames[label] = apply_unarmed_timeout(candidates, market, int(hours))
    results = {
        label: {name: replay_portfolio(book, market, *windows[name], portfolio) for name in names}
        for label, book in books.items()
    }
    _assert_expected(
        results[CONTROL]["full"].summary, baseline_config["acceptance"],
        float(baseline_config["acceptance_tolerance"]),
    )
    control = results[CONTROL]["full"]
    control_quality = quality(control, threshold)
    control_wf = sum(results[CONTROL][name].summary["net_profit"] for name in wf_names)
    acceptance = experiment["acceptance"]
    rows, cohort_rows, direct_frames, window_rows = [], [], [], []
    for label, by_window in results.items():
        full = by_window["full"]
        q = quality(full, threshold)
        wf = sum(by_window[name].summary["net_profit"] for name in wf_names)
        changes = [by_window[name].summary["net_profit"] - results[CONTROL][name].summary["net_profit"]
                   for name in wf_names]
        row = {
            "variant": label, "profit": full.summary["net_profit"],
            "profit_change": full.summary["net_profit"] - control.summary["net_profit"],
            "trades": full.summary["trades"], "trade_change": full.summary["trades"] - control.summary["trades"],
            "economic_win_rate_pct": q["economic_win_rate_pct"],
            "average_win": full.summary["average_win"], "average_loss": full.summary["average_loss"],
            "profit_factor": full.summary["profit_factor"],
            "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
            "profit_to_drawdown": _ratio(full), "walk_forward_profit": wf,
            "walk_forward_change": wf - control_wf,
            "walk_forward_windows_improved": sum(change > 0 for change in changes),
            "timeouts_filled": int((full.trades.exit_kind == "unarmed_timeout").sum()),
        }
        row["accepted"] = bool(
            label != CONTROL
            and row["profit_change"] > acceptance["full_profit_change_gt"]
            and row["walk_forward_change"] > acceptance["walk_forward_profit_change_gt"]
            and row["walk_forward_windows_improved"] >= acceptance["minimum_walk_forward_windows_improved"]
            and row["economic_win_rate_pct"] >= control_quality["economic_win_rate_pct"]
            and row["average_loss"] >= control.summary["average_loss"]
            and row["max_drawdown_pct"] >= control.summary["maximum_drawdown_pct"]
        )
        rows.append(row)
        for name in names:
            window_rows.append({
                "variant": label, "window": name,
                "profit": by_window[name].summary["net_profit"],
                "profit_change": by_window[name].summary["net_profit"]
                                 - results[CONTROL][name].summary["net_profit"],
            })
        if label != CONTROL:
            hours = int(label.removeprefix("unarmed_").removesuffix("h"))
            direct = _direct_diagnostics(control, candidates, eligible_frames[label], market, portfolio, threshold)
            if len(direct):
                direct_frames.append(direct.assign(variant=label))
                cohort_rows.extend(_cohort_rows(direct, hours))

    frame = pd.DataFrame(rows)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(cohort_rows).to_csv(output / "time_to_arm_cohorts.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    if direct_frames:
        pd.concat(direct_frames, ignore_index=True).to_csv(output / "eligible_trade_diagnostics.csv", index=False)
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    (output / "summary.json").write_text(json.dumps({
        "accepted_variants": accepted, "decision": "accept" if accepted else "reject_all",
    }, indent=2) + "\n")
    (output / "REPORT.md").write_text(_report(frame, pd.DataFrame(cohort_rows)))
    return output


def _report(frame: pd.DataFrame, cohorts: pd.DataFrame) -> str:
    rows = []
    for row in frame.itertuples():
        decision = "CONTROL" if row.variant == CONTROL else ("PASS" if row.accepted else "FAIL")
        rows.append(
            f"| {row.variant} | ${row.profit:.2f} | ${row.profit_change:+.2f} | {row.trades} | "
            f"{row.economic_win_rate_pct:.1f}% | ${row.average_win:.2f} | ${row.average_loss:.2f} | "
            f"{row.max_drawdown_pct:.2f}% | ${row.walk_forward_change:+.2f} | "
            f"{row.walk_forward_windows_improved}/6 | {row.timeouts_filled} | {decision} |"
        )
    all_rows = cohorts[cohorts.source == "all"]
    cohort_lines = []
    for row in all_rows.itertuples():
        cohort_lines.append(
            f"| {row.checkpoint_hours}h | {row.filled_unarmed} | {row.later_arm_rate_pct:.1f}% | "
            f"{row.eventual_economic_win_rate_pct:.1f}% | {row.eventual_protective_stop_rate_pct:.1f}% | "
            f"${row.direct_pnl_change:+.2f} |"
        )
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    decision = f"Advance {', '.join(accepted)}." if accepted else "Reject every unconditional unarmed time-stop."
    return f"""# ETH time-to-arm experiment

## Result

**{decision}**

| Rule | Profit | vs base | Trades | Economic win | Avg win | Avg loss | Drawdown | WF change | WF improved | Timeout fills | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(rows)}

## What historically happened to filled trades still unarmed

| Still unarmed after | Trades | Later armed | Eventual economic winners | Eventual stops | Direct P&L if exited there |
|---|---:|---:|---:|---:|---:|
{chr(10).join(cohort_lines)}

The direct P&L column ignores replacement trades; the portfolio table above includes freed-slot effects and is the decision source.
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
