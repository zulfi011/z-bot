"""Run the complete ETH Stage 1.5 audit and create an immutable paper rule."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

from src.research.stage15_exit.statistics import strategy_specs
from .analysis import (
    SCENARIOS,
    exact_scenario_events,
    exact_stop_sensitivity,
    evaluate_decision,
    exit_sweep,
    require,
    scenario_metrics,
    selected_events,
    sensitivity_table,
)
from .reporting import write_report


ROOT = Path(__file__).resolve().parents[3]
RUN = "eth_stage15_freeze_v1"
RESULTS = ROOT / "results/eth_stage15" / RUN
DATA = ROOT / "data/research/eth_stage15" / RUN
SOURCE = ROOT / "data/research/stage15/step5_exits_v1/ETHUSDT"
CONFIG_PATH = ROOT / "config/experiments/eth_stage15_freeze_v1.yaml"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_csv(name: str, frame: pd.DataFrame) -> None:
    path = RESULTS / f"{name}.csv"
    frame.to_csv(path, index=False)
    persisted = pd.read_csv(path)
    pd.testing.assert_frame_equal(
        frame.reset_index(drop=True), persisted,
        check_dtype=False, check_exact=False, rtol=1e-9, atol=1e-9,
    )


def load_candidates() -> tuple[pd.DataFrame, dict[str, dict[str, str | int]]]:
    frames = []
    manifest: dict[str, dict[str, str | int]] = {}
    for timeframe in ["1m", "3m", "5m"]:
        path = SOURCE / f"ETHUSDT_{timeframe}_exit_candidates.parquet"
        require(path.exists(), f"Missing source {path}")
        frame = pd.read_parquet(path)
        require(frame.asset.eq("ETHUSDT").all(), "Non-ETH source row")
        require(frame.timeframe.eq(timeframe).all(), "Source timeframe mismatch")
        require(not frame.duplicated(["episode_id", "policy"]).any(), "Duplicate source candidates")
        frames.append(frame)
        manifest[str(path.relative_to(ROOT))] = {"size": path.stat().st_size, "sha256": sha256(path)}
    return pd.concat(frames, ignore_index=True), manifest


def frozen_rule(config: dict, decision: dict, metrics: pd.DataFrame, source_manifest: dict) -> dict:
    realistic = metrics.loc[metrics.scenario.eq("realistic")].set_index("period")
    return {
        "schema_version": 1,
        "strategy_id": "eth_15d_bullish_bounce_3m_v1",
        "status": decision["decision"],
        "paper_trade_only": True,
        "asset": "ETHUSDT",
        "venue_type": "spot",
        "direction": "long_only",
        "signal": {
            "timeframe": "3m",
            "daily_average_source": "completed_UTC_daily_closes_only",
            "averages": {"type": "simple", "days": [7, 15, 30]},
            "regime": "average_7d > average_15d > average_30d",
            "reference_average": "15d",
            "touch_zone_pct": 1.0,
            "touch_definition": "candle_high >= average*(1-zone) and candle_low <= average*(1+zone)",
            "deduplication": "one_episode_for_consecutive_touching_candles",
            "confirmation": "first_3m_candle_with_close_greater_than_open_within_30_minutes",
            "confirmation_expiry": "first_non_touch_candle_included_or_30_minutes_whichever_first",
        },
        "execution": {
            "entry": "next_raw_1m_open_after_confirmation_close",
            "maximum_open_positions": 1,
            "position_selection": "earliest_eligible_signal_when_flat",
            "protective_stop_pct_from_actual_entry_fill": 5.0,
            "stop_gap_fill": "worse_of_stop_price_or_raw_1m_open",
            "profit_target": None,
            "trailing_stop": None,
            "maximum_hold_minutes": 480,
            "time_exit": "raw_1m_close_at_end_of_480th_minute",
            "same_candle_conflict": "protective_stop_wins",
        },
        "position_sizing": {
            "risk_budget_pct_of_net_liquidation": 1.0,
            "modeled_stop_loss_including_costs_pct": 5.25,
            "maximum_position_notional_pct_of_net_liquidation": 19.0,
            "formula": "min(available_quote_balance, net_liquidation*0.19)",
            "leverage": "none",
            "insufficient_balance_action": "reduce_to_available_quote_balance_or_skip_if_below_exchange_minimum",
        },
        "paper_cost_model": {
            "fee_bps_per_side": 10.0,
            "slippage_bps_per_side": 2.0,
            "adverse_slippage_on_entry_and_exit": True,
        },
        "historical_audit": {
            "data_start_utc": config["source_period"]["start_utc"],
            "data_end_utc": config["source_period"]["end_utc"],
            "split_utc": config["source_period"]["split_utc"],
            "earlier_trades": int(realistic.loc["earlier", "trades"]),
            "later_trades": int(realistic.loc["later", "trades"]),
            "realistic_mean_pct_earlier": float(realistic.loc["earlier", "mean_pct"]),
            "realistic_mean_pct_later": float(realistic.loc["later", "mean_pct"]),
            "realistic_ci95_earlier": [float(realistic.loc["earlier", "ci95_low"]), float(realistic.loc["earlier", "ci95_high"])],
            "realistic_ci95_later": [float(realistic.loc["later", "ci95_low"]), float(realistic.loc["later", "ci95_high"])],
            "strict_historical_validation_pass": decision["strict_historical_validation_pass"],
        },
        "immutability": {
            "rule_changes_require_new_strategy_id": True,
            "historical_source_manifest": source_manifest,
        },
    }


def run() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text())
    require(config["experiment"]["name"] == RUN, "Experiment name mismatch")
    require(config["execution_scenarios"] == {
        name: {"fee_bps_per_side": fee, "slippage_bps_per_side": slip}
        for name, (fee, slip) in SCENARIOS.items()
    }, "Execution scenarios changed")
    require(not RESULTS.exists() and not DATA.exists(), "Run exists; refusing overwrite")
    candidates, source_manifest = load_candidates()
    raw_path = ROOT / "data/processed/ETHUSDT/ETHUSDT_1m_with_averages.parquet"
    raw = pd.read_parquet(raw_path)
    source_manifest[str(raw_path.relative_to(ROOT))] = {
        "size": raw_path.stat().st_size,
        "sha256": sha256(raw_path),
    }
    RESULTS.mkdir(parents=True, exist_ok=False)
    DATA.mkdir(parents=True, exist_ok=False)
    (RESULTS / "experiment.json").write_text(json.dumps(config, indent=2) + "\n")
    (RESULTS / "source_manifest.json").write_text(json.dumps(source_manifest, indent=2) + "\n")

    strategy = "time_480_stop_4"
    events = exact_scenario_events(candidates, raw, stop_pct=5.0)
    realistic_events = events.loc[events.scenario.eq("realistic")].copy()
    require(len(realistic_events.loc[realistic_events.analysis_period.eq("earlier")]) == 69, "Earlier event count changed")
    require(len(realistic_events.loc[realistic_events.analysis_period.eq("later")]) == 48, "Later event count changed")
    metrics, quarters, months = scenario_metrics(events, 10_000, 1531)
    sensitivity = sensitivity_table(candidates, raw, 10_000, 1531)
    stop_sensitivity = exact_stop_sensitivity(candidates, raw)
    exits = exit_sweep(candidates, [item[0] for item in strategy_specs()])
    decision = evaluate_decision(metrics, quarters, sensitivity)

    event_columns = [
        "episode_id", "origin_signal_timestamp", "entry_timestamp", "analysis_period", "scenario",
        "timeframe", "average_type", "touch_zone", "policy", "origin_regime",
        "entry_fill", "exit_fill", "net_return_pct", "exact_duration_minutes", "exact_exit_type",
    ]
    event_path = DATA / "frozen_candidate_events.parquet"
    realistic_events[event_columns].to_parquet(event_path, index=False)
    pd.testing.assert_frame_equal(realistic_events[event_columns].reset_index(drop=True), pd.read_parquet(event_path), check_exact=True)
    save_csv("scenario_metrics", metrics)
    save_csv("quarterly", quarters)
    save_csv("monthly", months)
    save_csv("parameter_sensitivity", sensitivity)
    save_csv("protective_stop_sensitivity", stop_sensitivity)
    save_csv("exit_sweep", exits)
    (RESULTS / "DECISION.json").write_text(json.dumps(decision, indent=2) + "\n")

    rule = frozen_rule(config, decision, metrics, source_manifest)
    rule_text = json.dumps(rule, indent=2, allow_nan=False) + "\n"
    (RESULTS / "frozen_strategy.json").write_text(rule_text)
    (RESULTS / "frozen_strategy.sha256").write_text(
        hashlib.sha256(rule_text.encode()).hexdigest() + "  frozen_strategy.json\n"
    )
    write_report(
        RESULTS / "ETH_STAGE15_FINAL_REPORT.md", metrics, quarters,
        sensitivity, stop_sensitivity, exits, decision,
    )
    (RESULTS / "SUCCESS.json").write_text(json.dumps({
        "experiment": RUN,
        "source_rows": len(candidates),
        "frozen_event_rows": len(realistic_events),
        "exit_rules_compared": len(exits),
        "sensitivity_configurations": len(sensitivity),
        "bootstrap_repetitions_per_period_and_scenario": 10_000,
        "decision": decision["decision"],
        "validation": "PASS",
    }, indent=2) + "\n")
    print(f"Completed: {RESULTS / 'ETH_STAGE15_FINAL_REPORT.md'}")


if __name__ == "__main__":
    run()
