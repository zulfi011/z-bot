"""Run Stage 1.5 v2 ATR exit research on long-only SOL spot trades."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.research.stage15.validation import sha256
from src.research.stage15_robustness.analysis import select_nonoverlap
from .analysis import MARKET_FILTERS, all_strategy_names, build_analysis, market_mask, screen
from .atr import attach_entry_atr, hourly_candles, require, wilder_atr
from .reporting import write_report
from .simulator import AtrExitEngine, strategy_specs


ROOT = Path(__file__).resolve().parents[3]
RUN = "step3_atr_exits_v1"
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


def validate_atr_reference(context, hourly, atr_values, count=160):
    lookup = pd.Series(atr_values, index=pd.DatetimeIndex(hourly.open_time))
    sample = context.sample(n=min(count, len(context)), random_state=1523)
    checks = 0
    for row in sample.itertuples(index=False):
        expected_hour = row.entry_timestamp.floor("1h") - pd.Timedelta("1h")
        require(row.atr_reference_hour == expected_hour, "ATR used an incomplete hour")
        require(np.isclose(row.atr_14_1h, lookup.loc[expected_hour], equal_nan=True), "ATR lookup mismatch")
        checks += 2
    return checks


def reference_audit(candidates):
    reference = candidates.loc[candidates.average_type.eq("15d") & candidates.touch_zone.eq(.5)
                               & candidates.timeframe.isin(["3m", "5m"])
                               & candidates.eligible & candidates.entered & candidates.atr_window_complete]
    rows = []
    for timeframe in ["3m", "5m"]:
        setup = reference.loc[reference.timeframe.eq(timeframe)]
        for market_filter in MARKET_FILTERS:
            filtered = setup.loc[market_mask(setup, market_filter)]
            for strategy in all_strategy_names():
                for period, current in filtered.groupby("period", sort=True):
                    selected = select_nonoverlap(current, f"{strategy}_duration_minutes").copy()
                    selected["market_filter"] = market_filter; selected["strategy"] = strategy
                    selected["gross_return_pct"] = selected[f"{strategy}_return_pct"]
                    selected["net_0_2_return_pct"] = selected.gross_return_pct - .2
                    rows.append(selected[["episode_id", "timeframe", "market_filter", "strategy", "period",
                                          "origin_signal_timestamp", "entry_timestamp", "atr_reference_hour",
                                          "atr_14_1h", "atr_pct_of_entry", "gross_return_pct",
                                          "net_0_2_return_pct", f"{strategy}_duration_minutes",
                                          f"{strategy}_exit_type"]].rename(columns={
                                              f"{strategy}_duration_minutes": "duration_minutes",
                                              f"{strategy}_exit_type": "exit_type"}))
    return pd.concat(rows, ignore_index=True)


def run():
    config = yaml.safe_load((ROOT / "config/experiments/v1_stage15_v2_step3_atr_exits.yaml").read_text())
    require(config["universe"]["market_variants"] == MARKET_FILTERS, "Unsupported market variants")
    require(config["spot_constraints"]["direction"] == "long_only"
            and config["spot_constraints"]["leverage"] == "none", "Spot constraints changed")
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")
    print("Hashing all pre-existing research artifacts...", flush=True)
    before = protected_snapshot(); DATA.mkdir(parents=True, exist_ok=False); RESULTS.mkdir(parents=True, exist_ok=False)
    (RESULTS / "source_manifest_before.json").write_text(json.dumps(before, indent=2) + "\n")
    (RESULTS / "experiment.json").write_text(json.dumps(config, indent=2) + "\n")

    print("Building completed one-hour candles and causal Wilder ATR(14)...", flush=True)
    raw = pd.read_parquet(ROOT / "data/raw/SOLUSDT/SOLUSDT_1m.parquet",
                          columns=["open_time", "open", "high", "low", "close"])
    hourly = hourly_candles(raw); atr_values, true_range = wilder_atr(hourly, 14)
    require(np.isfinite(atr_values[13:]).all() and (true_range > 0).all(), "Invalid ATR series")
    source_parts = []
    for timeframe in ["1m", "3m", "5m"]:
        source = pd.read_parquet(STEP5 / f"SOLUSDT_{timeframe}_exit_candidates.parquet")
        selected = source.loc[source.policy.eq("bullish_candle_30m") & source.approach.eq("from_below")].copy()
        require(not selected.duplicated("episode_id").any(), "Duplicate source episode")
        source_parts.append(selected)
    candidates = pd.concat(source_parts, ignore_index=True)
    unique_entries = pd.DatetimeIndex(candidates.entry_timestamp.dropna().unique()).sort_values()
    entry_context = attach_entry_atr(unique_entries, hourly, atr_values)
    atr_checks = validate_atr_reference(entry_context, hourly, atr_values)
    print(f"Simulating nine ATR exits for {len(entry_context):,} unique spot entries...", flush=True)
    engine = AtrExitEngine(raw); outcomes = engine.calculate(entry_context)
    exit_checks = engine.validate_samples(outcomes)
    candidates = candidates.merge(outcomes, on="entry_timestamp", how="left", validate="many_to_one")
    candidates["fixed_target_4_stop_4_return_pct"] = candidates.target_4_stop_4_return_pct
    candidates["fixed_target_4_stop_4_duration_minutes"] = candidates.target_4_stop_4_duration_minutes
    candidates["fixed_target_4_stop_4_exit_type"] = candidates.target_4_stop_4_exit_type
    candidates["fixed_target_4_stop_4_stop_distance_pct"] = 4.0
    candidates["fixed_target_4_stop_4_target_distance_pct"] = 4.0
    require(candidates.loc[candidates.eligible & candidates.entered, "atr_window_complete"].eq(True).all(),
            "Eligible entry lacks ATR outcome")
    for timeframe, frame in candidates.groupby("timeframe", sort=True):
        output = DATA / "SOLUSDT"; output.mkdir(parents=True, exist_ok=True)
        path = output / f"SOLUSDT_{timeframe}_atr_exit_candidates.parquet"
        frame.to_parquet(path, index=False)
        pd.testing.assert_frame_equal(frame.reset_index(drop=True), pd.read_parquet(path), check_exact=True)

    print("Comparing ATR exits with fixed ±4% under overlap and cost controls...", flush=True)
    summary, quarterly = build_analysis(candidates); summary = screen(summary)
    require(len(summary) == 27 * 2 * 10, "Unexpected comparison count")
    fixed = summary.loc[summary.timeframe.eq("5m") & summary.average_type.eq("15d")
                        & summary.touch_zone.eq(.5) & summary.market_filter.eq("all_market_conditions")
                        & summary.strategy.eq("fixed_target_4_stop_4")].iloc[0]
    require(fixed.nonoverlap_trades_earlier == 62 and fixed.nonoverlap_trades_later == 55
            and np.isclose(fixed.net_0_2_mean_pct_earlier, .20865806149924584)
            and np.isclose(fixed.net_0_2_mean_pct_later, .24006116043979434), "Fixed baseline bridge failed")
    audit = reference_audit(candidates); audit_path = DATA / "reference_atr_events.parquet"
    audit.to_parquet(audit_path, index=False)
    pd.testing.assert_frame_equal(audit, pd.read_parquet(audit_path), check_exact=True)
    atr_stats = {"median_atr_pct": candidates.atr_pct_of_entry.median(),
                 "p10_atr_pct": candidates.atr_pct_of_entry.quantile(.1),
                 "p90_atr_pct": candidates.atr_pct_of_entry.quantile(.9)}
    save_csv("summary", summary); save_csv("quarterly", quarterly)
    save_csv("atr_distribution", pd.DataFrame([atr_stats]))
    save_csv("validation", pd.DataFrame([{"atr_reference_values_checked": atr_checks,
                                          "direct_strategy_exit_replays": exit_checks,
                                          "candidate_rows": len(candidates), "pass": True}]))
    print("Verifying that all earlier research files remain byte-identical...", flush=True)
    after = protected_snapshot(); require(before == after, "A protected pre-existing file changed")
    (RESULTS / "source_manifest_after.json").write_text(json.dumps(after, indent=2) + "\n")
    write_report(RESULTS, summary, atr_stats, len(before), len(audit))
    (RESULTS / "SUCCESS.json").write_text(json.dumps({
        "step": "stage15_v2_step3", "scope": "spot_long_atr_exits", "comparisons": len(summary),
        "provisional_passes": int(summary.provisional_pass.sum()),
        "robust_passes": int(summary.robust_pass.sum()), "reference_audit_rows": len(audit),
        "protected_files_unchanged": len(before), "validation": "PASS",
    }, indent=2) + "\n")
    print(f"Completed: {RESULTS / 'atr_exit_report.md'}", flush=True)


if __name__ == "__main__":
    run()
