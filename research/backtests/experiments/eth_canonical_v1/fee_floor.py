"""Experiment 7: test ETH break-even floors under BNB and USDT fee modes."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

import pandas as pd

from . import baseline as baseline_module
from .engine import replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_fee_floor_v1.json"


def build_with_floor(floor_pct: float):
    """Build identical ETH candidates with only the armed Mode-A floor changed."""
    original = baseline_module.floor_arm.COSTS
    baseline_module.floor_arm.COSTS = floor_pct
    try:
        return baseline_module.build_baseline()
    finally:
        baseline_module.floor_arm.COSTS = original


def floor_exit_metrics(trades: pd.DataFrame) -> dict:
    floor_exits = trades[trades.exit_kind == "break_even"]
    return {
        "floor_exits": int(len(floor_exits)),
        "floor_exit_profit": float(floor_exits.pnl.sum()),
        "average_floor_exit": float(floor_exits.pnl.mean()) if len(floor_exits) else 0.0,
        "negative_floor_exits": int((floor_exits.pnl < 0).sum()),
        "positive_floor_exits": int((floor_exits.pnl > 0).sum()),
        "floor_exits_above_025pct": int((floor_exits.return_pct > 0.25).sum()),
    }


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    base_portfolio = _portfolio_config(baseline_config)
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    rows, window_rows, floor_rows = [], [], []
    scenario_results = {}

    for scenario in experiment["scenarios"]:
        market, candidates, windows = build_with_floor(float(scenario["floor_pct"]))
        portfolio = replace(
            base_portfolio,
            fee_per_side=float(scenario["actual_fee_bps"]) / 10_000,
            slippage_per_side=float(scenario["actual_slippage_bps"]) / 10_000,
        )
        results = {name: replay_portfolio(candidates, market, *windows[name], portfolio) for name in names}
        scenario_results[scenario["name"]] = results

    control = scenario_results["bnb_reserve_control"]
    missing = scenario_results["bnb_missing_current_floor"]
    for scenario in experiment["scenarios"]:
        label = scenario["name"]
        results = scenario_results[label]
        full = results["full"]
        floor_stats = floor_exit_metrics(full.trades)
        wf_profit = sum(results[name].summary["net_profit"] for name in wf_names)
        wf_control = sum(control[name].summary["net_profit"] for name in wf_names)
        wf_missing = sum(missing[name].summary["net_profit"] for name in wf_names)
        rows.append({
            "variant": label, "floor_pct": scenario["floor_pct"],
            "actual_fee_bps": scenario["actual_fee_bps"],
            "actual_slippage_bps": scenario["actual_slippage_bps"],
            "profit": full.summary["net_profit"],
            "change_vs_original_baseline": (full.summary["net_profit"]
                                             - control["full"].summary["net_profit"]),
            "change_vs_same_cost_current_floor": (full.summary["net_profit"]
                                                   - missing["full"].summary["net_profit"]
                                                   if scenario["actual_fee_bps"] == 10
                                                   and scenario["actual_slippage_bps"] == 2 else None),
            "trades": full.summary["trades"], "win_rate_pct": full.summary["win_rate_pct"],
            "average_loss": full.summary["average_loss"],
            "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
            "walk_forward_profit": wf_profit, "walk_forward_change_vs_control": wf_profit - wf_control,
            "walk_forward_change_vs_same_cost_current_floor": (
                wf_profit - wf_missing if scenario["actual_fee_bps"] == 10
                and scenario["actual_slippage_bps"] == 2 else None
            ),
            **floor_stats,
        })
        floor_part = full.trades[full.trades.exit_kind == "break_even"].copy()
        if len(floor_part):
            floor_rows.append(floor_part.assign(variant=label))
        for name in names:
            window_rows.append({
                "variant": label, "window": name,
                "profit": results[name].summary["net_profit"],
                "original_baseline_profit": control[name].summary["net_profit"],
                "change_vs_original_baseline": (results[name].summary["net_profit"]
                                                 - control[name].summary["net_profit"]),
            })

    frame = pd.DataFrame(rows)
    reserve = experiment["bnb_reserve"]
    round_trip_usd = (reserve["lot_size_usd"] * experiment["scenarios"][0]["actual_fee_bps"]
                      * 2 / 10_000)
    reserve_summary = {
        "bnb_fee_usd_per_100_round_trip": round_trip_usd,
        "minimum_bnb_value_usd": round_trip_usd * reserve["minimum_round_trips"],
        "recommended_bnb_value_usd": round_trip_usd * reserve["recommended_round_trips_with_safety_margin"],
    }
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.concat(floor_rows, ignore_index=True).to_csv(output / "floor_exits.csv", index=False)
    summary = {"original_baseline": frame.iloc[0].to_dict(), "bnb_reserve": reserve_summary}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(frame, reserve_summary))
    return output


def _report(frame: pd.DataFrame, reserve: dict) -> str:
    base = frame.iloc[0]
    mismatch = frame[frame.variant == "bnb_missing_current_floor"].iloc[0]
    aware = frame[frame.variant == "usdt_fee_aware_floor"].iloc[0]
    buffer = frame[frame.variant == "usdt_fee_plus_2bps_buffer"].iloc[0]
    stress_current = frame[frame.variant == "usdt_slippage_stress_current_floor"].iloc[0]
    stress_aware = frame[frame.variant == "usdt_slippage_stress_aware_floor"].iloc[0]
    return f"""# ETH fee-mode and break-even-floor experiment

## Result: MAINTAINING THE BNB RESERVE IS BEST

| Scenario | Profit | Change vs original | Floor exits | Negative floor exits | Floor-exit P&L |
|---|---:|---:|---:|---:|---:|
| Original: BNB fee + 0.19% floor | ${base.profit:.2f} | $0.00 | {base.floor_exits} | {base.negative_floor_exits} | ${base.floor_exit_profit:.2f} |
| BNB missing; old 0.19% floor | ${mismatch.profit:.2f} | ${mismatch.change_vs_original_baseline:+.2f} | {mismatch.floor_exits} | {mismatch.negative_floor_exits} | ${mismatch.floor_exit_profit:.2f} |
| USDT-fee-aware 0.24% floor | ${aware.profit:.2f} | ${aware.change_vs_original_baseline:+.2f} | {aware.floor_exits} | {aware.negative_floor_exits} | ${aware.floor_exit_profit:.2f} |
| USDT floor + 2bps buffer | ${buffer.profit:.2f} | ${buffer.change_vs_original_baseline:+.2f} | {buffer.floor_exits} | {buffer.negative_floor_exits} | ${buffer.floor_exit_profit:.2f} |
| USDT + 5bps slippage; old floor | ${stress_current.profit:.2f} | ${stress_current.change_vs_original_baseline:+.2f} | {stress_current.floor_exits} | {stress_current.negative_floor_exits} | ${stress_current.floor_exit_profit:.2f} |
| USDT + 5bps slippage; 0.30% floor | ${stress_aware.profit:.2f} | ${stress_aware.change_vs_original_baseline:+.2f} | {stress_aware.floor_exits} | {stress_aware.negative_floor_exits} | ${stress_aware.floor_exit_profit:.2f} |

## What changed

- Losing the BNB discount while keeping the old floor reduces total profit by **${-mismatch.change_vs_original_baseline:.2f}**.
- At normal 2bps slippage, changing the USDT-fee floor from 0.19% to 0.24% recovers **${aware.change_vs_same_cost_current_floor:.2f}** and prevents all {int(mismatch.negative_floor_exits)} floor exits from being small losses.
- The extra 2bps buffer performs **${buffer.change_vs_same_cost_current_floor:+.2f}** versus the same-cost old floor and exits more trades early. It is not supported.
- Under the 5bps slippage stress, the 0.30% floor prevents negative floor exits but total profit is **${stress_aware.profit:.2f}** because higher costs affect every trade.

## BNB reserve

- One $100 ETH round trip uses approximately **${reserve['bnb_fee_usd_per_100_round_trip']:.2f}** of BNB fees.
- Five simultaneous ETH lots require at least **${reserve['minimum_bnb_value_usd']:.2f}** of BNB for their round trips.
- A simple two-times safety reserve is **${reserve['recommended_bnb_value_usd']:.2f}** of BNB.

## Decision

Keep the trading rules unchanged and maintain the BNB reserve. Also report all `break_even` exits as **floor exits**, never as profitable winners. A fee-aware 0.24% floor is a sensible fallback when USDT fees are expected, but it still finishes **${-aware.change_vs_original_baseline:.2f} below the BNB baseline** because the higher fee applies to every trade. Do not add the extra floor buffer from this test.
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
