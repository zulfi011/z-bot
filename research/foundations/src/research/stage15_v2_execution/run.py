"""Run realistic long-only spot execution analysis."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.research.stage15.validation import sha256
from src.research.stage15_robustness.analysis import select_nonoverlap
from .analysis import MARKET_FILTERS, build_analysis, market_mask, screen
from .reporting import write_report
from .simulator import SCENARIOS, SpotExecutionEngine, require


ROOT = Path(__file__).resolve().parents[3]
RUN = "step4_realistic_execution_v1"
DATA = ROOT / "data/research/stage15_v2" / RUN
RESULTS = ROOT / "results/stage15_v2" / RUN
STEP5 = ROOT / "data/research/stage15/step5_exits_v1/SOLUSDT"


def protected_snapshot():
    paths = []
    for folder in ["data", "results", "src", "config", "experiments", "tests"]:
        for path in (ROOT / folder).rglob("*"):
            if not path.is_file() or RUN in path.parts or "__pycache__" in path.parts:
                continue
            paths.append(path)
    paths += [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "V1_Stage1_Historical_Engine_Results.md"]
    return {str(path.relative_to(ROOT)): {"size": path.stat().st_size, "sha256": sha256(path)}
            for path in sorted(set(paths)) if path.exists()}


def save_csv(name, frame):
    path = RESULTS / f"{name}.csv"; frame.to_csv(path, index=False)
    pd.testing.assert_frame_equal(frame.reset_index(drop=True), pd.read_csv(path), check_dtype=False,
                                  check_exact=False, rtol=1e-9, atol=1e-9)


def reference_audit(candidates):
    rows = []
    definitions = [("5m", "all_market_conditions"), ("3m", "avoid_strong_bearish")]
    for timeframe, market_filter in definitions:
        setup = candidates.loc[candidates.timeframe.eq(timeframe) & candidates.average_type.eq("15d")
                               & candidates.touch_zone.eq(.5) & candidates.eligible & candidates.entered
                               & candidates.execution_window_complete]
        setup = setup.loc[market_mask(setup, market_filter)]
        for scenario in SCENARIOS:
            for period, current in setup.groupby("period", sort=True):
                selected = select_nonoverlap(current, f"{scenario}_duration_minutes").copy()
                selected["market_filter"] = market_filter; selected["scenario"] = scenario
                selected["return_pct"] = selected[f"{scenario}_return_pct"]
                rows.append(selected[["episode_id", "timeframe", "market_filter", "scenario", "period",
                                      "origin_signal_timestamp", "entry_timestamp", "raw_entry_open",
                                      f"{scenario}_entry_fill", f"{scenario}_exit_fill", "return_pct",
                                      f"{scenario}_duration_minutes", f"{scenario}_exit_type"]].rename(columns={
                                          f"{scenario}_entry_fill": "entry_fill",
                                          f"{scenario}_exit_fill": "exit_fill",
                                          f"{scenario}_duration_minutes": "duration_minutes",
                                          f"{scenario}_exit_type": "exit_type"}))
    return pd.concat(rows, ignore_index=True)


def run():
    config = yaml.safe_load((ROOT / "config/experiments/v1_stage15_v2_step4_realistic_execution.yaml").read_text())
    configured = {name: (values["fee_bps_per_side"], values["slippage_bps_per_side"])
                  for name, values in config["execution_scenarios"].items()}
    require(configured == SCENARIOS, "Execution scenarios changed")
    require(config["portfolio"]["maximum_open_positions"] == 1, "Position limit changed")
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")
    print("Hashing all pre-existing research artifacts...", flush=True)
    before = protected_snapshot(); DATA.mkdir(parents=True, exist_ok=False); RESULTS.mkdir(parents=True, exist_ok=False)
    (RESULTS / "source_manifest_before.json").write_text(json.dumps(before, indent=2) + "\n")
    (RESULTS / "experiment.json").write_text(json.dumps(config, indent=2) + "\n")

    source_parts = []
    for timeframe in ["1m", "3m", "5m"]:
        source = pd.read_parquet(STEP5 / f"SOLUSDT_{timeframe}_exit_candidates.parquet")
        selected = source.loc[source.policy.eq("bullish_candle_30m") & source.approach.eq("from_below")].copy()
        require(not selected.duplicated("episode_id").any(), "Duplicate source episode")
        source_parts.append(selected)
    candidates = pd.concat(source_parts, ignore_index=True)
    raw = pd.read_parquet(ROOT / "data/raw/SOLUSDT/SOLUSDT_1m.parquet",
                          columns=["open_time", "open", "high", "low", "close"])
    engine = SpotExecutionEngine(raw)
    entries = pd.DatetimeIndex(candidates.entry_timestamp.dropna().unique()).sort_values()
    print(f"Replaying five fee/slippage scenarios for {len(entries):,} unique spot entries...", flush=True)
    outcomes = engine.calculate(entries); replay_checks = engine.validate_samples(outcomes)
    candidates = candidates.merge(outcomes, on="entry_timestamp", how="left", validate="many_to_one")
    eligible = candidates.eligible & candidates.entered & candidates.execution_window_complete
    difference = (candidates.loc[eligible, "gross_return_pct"]
                  - candidates.loc[eligible, "target_4_stop_4_return_pct"]).abs().max()
    require(difference < 1e-10, "Zero-cost replay does not match validated fixed exit")
    for timeframe, frame in candidates.groupby("timeframe", sort=True):
        output = DATA / "SOLUSDT"; output.mkdir(parents=True, exist_ok=True)
        path = output / f"SOLUSDT_{timeframe}_execution_candidates.parquet"
        frame.to_parquet(path, index=False)
        pd.testing.assert_frame_equal(frame.reset_index(drop=True), pd.read_parquet(path), check_exact=True)

    print("Applying one-position rule and calculating cost sensitivity...", flush=True)
    summary, quarterly = build_analysis(candidates); summary = screen(summary)
    require(len(summary) == 27 * 2 * len(SCENARIOS), "Unexpected comparison count")
    gross = summary.loc[summary.timeframe.eq("5m") & summary.average_type.eq("15d")
                        & summary.touch_zone.eq(.5) & summary.market_filter.eq("all_market_conditions")
                        & summary.scenario.eq("gross")].iloc[0]
    require(gross.nonoverlap_trades_earlier == 62 and gross.nonoverlap_trades_later == 55
            and np.isclose(gross.mean_return_pct_earlier, .40865806149924594)
            and np.isclose(gross.mean_return_pct_later, .4400611604397945), "Gross baseline bridge failed")
    audit = reference_audit(candidates); audit_path = DATA / "reference_execution_events.parquet"
    audit.to_parquet(audit_path, index=False)
    pd.testing.assert_frame_equal(audit, pd.read_parquet(audit_path), check_exact=True)
    save_csv("summary", summary); save_csv("quarterly", quarterly)
    save_csv("validation", pd.DataFrame([{"direct_execution_checks": replay_checks,
                                          "zero_cost_bridge_max_abs_difference": difference,
                                          "candidate_rows": len(candidates), "pass": True}]))
    print("Verifying that all earlier research files remain byte-identical...", flush=True)
    after = protected_snapshot(); require(before == after, "A protected pre-existing file changed")
    (RESULTS / "source_manifest_after.json").write_text(json.dumps(after, indent=2) + "\n")
    write_report(RESULTS, summary, len(before), len(audit))
    realistic = summary.loc[summary.scenario.eq("realistic")]
    (RESULTS / "SUCCESS.json").write_text(json.dumps({
        "step": "stage15_v2_step4", "scope": "realistic_spot_execution",
        "comparisons": len(summary), "realistic_execution_passes": int(realistic.execution_pass.sum()),
        "realistic_robust_passes": int(realistic.robust_pass.sum()), "audit_rows": len(audit),
        "protected_files_unchanged": len(before), "validation": "PASS",
    }, indent=2) + "\n")
    print(f"Completed: {RESULTS / 'realistic_execution_report.md'}", flush=True)


if __name__ == "__main__":
    run()

