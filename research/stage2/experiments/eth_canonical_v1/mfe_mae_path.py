"""ETH experiment: exit unarmed trades with weak MFE and substantial MAE."""

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
from .failure_exit import checkpoint_index
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_mfe_mae_path_v1.json"
CONTROL = "baseline"
EXIT_CODE = 9


def apply_path_failure(
    candidates: list[CandidateTrade], market: MarketData, hours: int,
    maximum_mfe_pct: float, minimum_mae_pct: float,
) -> tuple[list[CandidateTrade], pd.DataFrame]:
    changed, rows = [], []
    grid = baseline_module.grid
    for candidate in candidates:
        check = checkpoint_index(market.times, candidate.entry, hours)
        still_unarmed = bool(
            check is not None and candidate.exit > check
            and (candidate.arm_index is None or candidate.arm_index > check)
        )
        if not still_unarmed:
            changed.append(candidate)
            continue
        fill = float(grid.OPEN[candidate.entry]) * (1 + grid.SLIP)
        mfe = 100 * (float(np.max(grid.HIGH[candidate.entry:check + 1])) / fill - 1)
        mae = 100 * (float(np.min(grid.LOW[candidate.entry:check + 1])) / fill - 1)
        if not (mfe < maximum_mfe_pct and mae <= -minimum_mae_pct):
            changed.append(candidate)
            continue
        exit_index = int(check + 1)
        changed.append(replace(
            candidate, exit=exit_index, exit_price=float(market.open[exit_index]),
            exit_code=EXIT_CODE, exit_kind="path_failure",
        ))
        rows.append({
            "candidate_id": candidate.candidate_id, "source": candidate.source,
            "entry_time": market.times[candidate.entry], "checkpoint_hours": hours,
            "mfe_pct": mfe, "mae_pct": mae,
            "later_armed": candidate.arm_index is not None and candidate.arm_index > check,
            "original_exit_kind": candidate.exit_kind,
        })
    return changed, pd.DataFrame(rows)


def _ratio(result: ReplayResult) -> float:
    drawdown = abs(float(result.summary["maximum_drawdown_usd"]))
    return float(result.summary["net_profit"]) / drawdown if drawdown else float("inf")


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    market, candidates, windows = baseline_module.build_baseline()
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    threshold = float(experiment["economic_winner_threshold_pct"])
    books = {CONTROL: candidates}
    diagnostics = {}
    for variant in experiment["variants"]:
        books[variant["name"]], diagnostics[variant["name"]] = apply_path_failure(
            candidates, market, int(variant["checkpoint_hours"]),
            float(variant["maximum_favorable_excursion_below_pct"]),
            float(variant["maximum_adverse_excursion_at_least_pct"]),
        )
    results = {
        label: {name: replay_portfolio(book, market, *windows[name], portfolio) for name in names}
        for label, book in books.items()
    }
    _assert_expected(results[CONTROL]["full"].summary, baseline_config["acceptance"],
                     float(baseline_config["acceptance_tolerance"]))
    control = results[CONTROL]["full"]
    control_quality = quality(control, threshold)
    control_wf = sum(results[CONTROL][name].summary["net_profit"] for name in wf_names)
    acceptance = experiment["acceptance"]
    rows, window_rows = [], []
    for label, by_window in results.items():
        full = by_window["full"]
        q = quality(full, threshold)
        wf = sum(by_window[name].summary["net_profit"] for name in wf_names)
        changes = [by_window[name].summary["net_profit"] - results[CONTROL][name].summary["net_profit"]
                   for name in wf_names]
        diagnostic = diagnostics.get(label, pd.DataFrame())
        filled_ids = set(full.trades.candidate_id)
        triggered = diagnostic[diagnostic.candidate_id.isin(filled_ids)] if len(diagnostic) else diagnostic
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
            "path_exits_filled": int((full.trades.exit_kind == "path_failure").sum()),
            "eligible_candidates": len(diagnostic),
            "eligible_later_arm_rate_pct": 100 * diagnostic.later_armed.mean() if len(diagnostic) else 0.0,
            "triggered_later_arm_rate_pct": 100 * triggered.later_armed.mean() if len(triggered) else 0.0,
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
    frame = pd.DataFrame(rows)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    for label, diagnostic in diagnostics.items():
        diagnostic.assign(variant=label).to_csv(output / f"{label}_eligible.csv", index=False)
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    (output / "summary.json").write_text(json.dumps({
        "accepted_variants": accepted, "decision": "accept" if accepted else "reject_all",
    }, indent=2) + "\n")
    (output / "REPORT.md").write_text(_report(frame))
    return output


def _report(frame: pd.DataFrame) -> str:
    rows = []
    for row in frame.itertuples():
        decision = "CONTROL" if row.variant == CONTROL else ("PASS" if row.accepted else "FAIL")
        rows.append(
            f"| {row.variant} | ${row.profit:.2f} | ${row.profit_change:+.2f} | {row.trades} | "
            f"{row.economic_win_rate_pct:.1f}% | ${row.average_win:.2f} | ${row.average_loss:.2f} | "
            f"{row.max_drawdown_pct:.2f}% | ${row.walk_forward_change:+.2f} | "
            f"{row.walk_forward_windows_improved}/6 | {row.path_exits_filled} | "
            f"{row.triggered_later_arm_rate_pct:.1f}% | {decision} |"
        )
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    decision = f"Advance {', '.join(accepted)}." if accepted else "Reject both path-failure exits."
    return f"""# ETH MFE/MAE path experiment

## Result

**{decision}**

| Rule | Profit | vs base | Trades | Economic win | Avg win | Avg loss | Drawdown | WF change | WF improved | Path exits | Later armed | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(rows)}
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
