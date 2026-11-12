"""Run Stage 1.5 v2 market-filter analysis without overwriting prior work."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.research.stage15.validation import sha256
from src.research.stage15_robustness.analysis import select_nonoverlap
from .analysis import CONFIG_KEYS, build_analysis, screen
from .context import (VARIANTS, apply_extreme_threshold, attach_joint_context,
                      filter_mask, fit_extreme_threshold, require)
from .reporting import write_report


ROOT = Path(__file__).resolve().parents[3]
RUN = "step2_market_filters_v1"
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
    path = RESULTS / f"{name}.csv"
    frame.to_csv(path, index=False)
    loaded = pd.read_csv(path)
    pd.testing.assert_frame_equal(frame.reset_index(drop=True), loaded, check_dtype=False,
                                  check_exact=False, rtol=1e-9, atol=1e-9)


def validate_context(frame, sol_candles, btc_candles, timeframe, count=100):
    sample = frame.sample(n=min(count, len(frame)), random_state=1522)
    sol = sol_candles.set_index("open_time").average_15d
    btc = btc_candles.set_index("open_time").average_15d
    delta = pd.Timedelta(timeframe)
    checks = 0
    for row in sample.itertuples(index=False):
        current = row.origin_signal_timestamp - delta
        prior = current - pd.Timedelta("1D")
        expected_sol = (sol.loc[current] / sol.loc[prior] - 1) * 100
        expected_btc = (btc.loc[current] / btc.loc[prior] - 1) * 100
        require(np.isclose(row.sol_15d_change_24h_pct, expected_sol, equal_nan=True), "SOL slope mismatch")
        require(np.isclose(row.btc_15d_change_24h_pct, expected_btc, equal_nan=True), "BTC slope mismatch")
        checks += 2
    return checks


def reference_events(candidates):
    main = candidates.loc[
        candidates.average_type.eq("15d") & candidates.timeframe.eq("5m")
        & candidates.touch_zone.eq(.5) & candidates.eligible & candidates.entered
        & candidates.complete_24h
    ]
    rows = []
    for variant in VARIANTS:
        accepted = main.loc[filter_mask(main, variant)]
        for period, current in accepted.groupby("period", sort=True):
            selected = select_nonoverlap(current, "duration_minutes").copy()
            selected["filter_variant"] = variant
            selected["net_0_2_return_pct"] = selected.gross_return_pct - .2
            rows.append(selected[["episode_id", "filter_variant", "period", "origin_signal_timestamp",
                                  "entry_timestamp", "sol_15d_change_24h_pct", "btc_15d_change_24h_pct",
                                  "origin_regime", "prior_range_24h_pct", "extreme_volatility",
                                  "exit_type", "duration_minutes", "gross_return_pct",
                                  "net_0_2_return_pct"]])
    return pd.concat(rows, ignore_index=True)


def run():
    config = yaml.safe_load((ROOT / "config/experiments/v1_stage15_v2_step2_market_filters.yaml").read_text())
    require(config["filters"]["variants"] == VARIANTS, "Unsupported filter grid")
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")
    print("Hashing all pre-existing research artifacts...", flush=True)
    before = protected_snapshot()
    DATA.mkdir(parents=True, exist_ok=False); RESULTS.mkdir(parents=True, exist_ok=False)
    (RESULTS / "source_manifest_before.json").write_text(json.dumps(before, indent=2) + "\n")
    (RESULTS / "experiment.json").write_text(json.dumps(config, indent=2) + "\n")

    parts, validations = [], []
    for timeframe in ["1m", "3m", "5m"]:
        print(f"SOLUSDT_{timeframe}: attaching causal SOL and BTC context", flush=True)
        source = pd.read_parquet(STEP5 / f"SOLUSDT_{timeframe}_exit_candidates.parquet")
        selected = source.loc[source.policy.eq("bullish_candle_30m") & source.approach.eq("from_below")].copy()
        require(not selected.duplicated("episode_id").any(), "Duplicate source episodes")
        selected["gross_return_pct"] = selected.target_4_stop_4_return_pct
        selected["duration_minutes"] = selected.target_4_stop_4_duration_minutes
        selected["exit_type"] = selected.target_4_stop_4_exit_type
        selected["complete_24h"] = selected.exit_window_complete_24h
        candle_columns = ["open_time", "average_15d"]
        sol = pd.read_parquet(ROOT / f"data/processed/SOLUSDT/SOLUSDT_{timeframe}_with_averages.parquet",
                              columns=candle_columns)
        btc = pd.read_parquet(ROOT / f"data/processed/BTCUSDT/BTCUSDT_{timeframe}_with_averages.parquet",
                              columns=candle_columns)
        enriched = attach_joint_context(selected, sol, btc, timeframe)
        checks = validate_context(enriched, sol, btc, timeframe)
        parts.append(enriched)
        validations.append({"dataset": f"SOLUSDT_{timeframe}", "source_rows": len(selected),
                            "direct_slope_values_checked": checks, "pass": True})
    candidates = pd.concat(parts, ignore_index=True)
    threshold, training_origins = fit_extreme_threshold(candidates)
    candidates = apply_extreme_threshold(candidates, threshold)
    repeated, repeated_count = fit_extreme_threshold(candidates)
    require(threshold == repeated and training_origins == repeated_count, "Volatility fit is not deterministic")
    require(candidates.groupby(["timeframe", "average_type", "touch_zone"], observed=True).ngroups == 27,
            "Missing SOL configurations")
    for timeframe, frame in candidates.groupby("timeframe", sort=True):
        output = DATA / "SOLUSDT"
        output.mkdir(parents=True, exist_ok=True)
        path = output / f"SOLUSDT_{timeframe}_market_filter_candidates.parquet"
        frame.to_parquet(path, index=False)
        pd.testing.assert_frame_equal(frame.reset_index(drop=True), pd.read_parquet(path), check_exact=True)

    print("Comparing individual filters and predefined combinations...", flush=True)
    summary, quarterly, complements = build_analysis(candidates)
    summary = screen(summary)
    require(len(summary) == 27 * len(VARIANTS), "Unexpected summary cardinality")
    main = summary.loc[summary.timeframe.eq("5m") & summary.average_type.eq("15d")
                       & summary.touch_zone.eq(.5) & summary.filter_variant.eq("all_market_conditions")].iloc[0]
    require(main.nonoverlap_trades_earlier == 62 and main.nonoverlap_trades_later == 55,
            "Current-candidate trade-count bridge failed")
    require(np.isclose(main.net_0_2_mean_pct_earlier, .20865806149924584)
            and np.isclose(main.net_0_2_mean_pct_later, .24006116043979434),
            "Current-candidate return bridge failed")
    audit = reference_events(candidates)
    audit_path = DATA / "reference_filter_events.parquet"
    audit.to_parquet(audit_path, index=False)
    pd.testing.assert_frame_equal(audit, pd.read_parquet(audit_path), check_exact=True)

    save_csv("summary", summary)
    save_csv("quarterly", quarterly)
    save_csv("accepted_vs_rejected", complements)
    save_csv("volatility_threshold", pd.DataFrame([{"asset": "SOLUSDT", "percentile": .9,
                                                     "prior_range_24h_threshold_pct": threshold,
                                                     "unique_earlier_training_origins": training_origins}]))
    save_csv("validation", pd.DataFrame(validations))
    print("Verifying that all earlier research files remain byte-identical...", flush=True)
    after = protected_snapshot(); require(before == after, "A protected pre-existing file changed")
    (RESULTS / "source_manifest_after.json").write_text(json.dumps(after, indent=2) + "\n")
    write_report(RESULTS, summary, threshold, training_origins, len(before), len(audit))
    (RESULTS / "SUCCESS.json").write_text(json.dumps({
        "step": "stage15_v2_step2", "scope": "causal_market_filters",
        "configurations": 27, "filter_variants": len(VARIANTS),
        "evaluated_comparisons": len(summary), "provisional_passes": int(summary.provisional_pass.sum()),
        "robust_passes": int(summary.robust_pass.sum()), "reference_audit_rows": len(audit),
        "protected_files_unchanged": len(before), "validation": "PASS",
    }, indent=2) + "\n")
    print(f"Completed: {RESULTS / 'market_filter_report.md'}", flush=True)


if __name__ == "__main__":
    run()

