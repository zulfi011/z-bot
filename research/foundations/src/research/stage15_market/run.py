"""Run Stage 1.5 Step 3 without modifying prior-stage artifacts."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.research.stage15.validation import sha256
from .context import (apply_volatility_bands, calculate_context,
                      fit_volatility_thresholds, reference_context, require)
from .reporting import write_report
from .statistics import (attach_screen_intervals, build_condition_summaries,
                         build_cross_grid_effects, build_stability_screen)


ROOT = Path(__file__).resolve().parents[3]
RUN = "step3_market_conditions_v1"
DATA = ROOT / "data/research/stage15" / RUN
RESULTS = ROOT / "results/stage15" / RUN
STEP2 = ROOT / "data/research/stage15/step2_entry_conditions_v1"
POLICIES = ["first_touch_0m", "bullish_candle_30m"]


def protected_snapshot():
    paths = []
    for folder in ["data", "results", "src", "config", "experiments"]:
        for path in (ROOT / folder).rglob("*"):
            if not path.is_file() or RUN in path.parts or "stage15_market" in path.parts:
                continue
            if "__pycache__" in path.parts or path.name == "v1_stage15_step3_market_conditions.yaml":
                continue
            paths.append(path)
    paths += [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "V1_Stage1_Historical_Engine_Results.md"]
    return {
        str(path.relative_to(ROOT)): {"size": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(set(paths))
    }


def save_csv(name, frame):
    path = RESULTS / f"{name}.csv"
    comparable = frame.copy()
    for column in comparable.select_dtypes(include=["datetimetz", "datetime64"]).columns:
        comparable[column] = comparable[column].astype(str)
    comparable.to_csv(path, index=False)
    loaded = pd.read_csv(path)
    pd.testing.assert_frame_equal(
        comparable.reset_index(drop=True), loaded, check_dtype=False,
        check_exact=False, rtol=1e-9, atol=1e-9,
    )


def validate_context(raw, candles, origins, context, timeframe):
    sample = origins.sample(n=min(160, len(origins)), random_state=1503)
    indexed = context.set_index("episode_id")
    checks = 0
    for origin in sample.itertuples(index=False):
        expected = reference_context(raw, candles, origin, timeframe)
        actual = indexed.loc[origin.episode_id]
        for column, value in zip(
            ["prior_return_24h_pct", "prior_range_24h_pct",
             "average_change_24h_pct", "touch_close_distance_pct"], expected,
        ):
            if pd.isna(value):
                require(pd.isna(actual[column]), f"Expected missing {column}")
            else:
                require(np.isclose(actual[column], value, rtol=1e-12, atol=1e-12),
                        f"Context mismatch: {column}")
        checks += 4
    return checks


def run():
    config_path = ROOT / "config/experiments/v1_stage15_step3_market_conditions.yaml"
    config = yaml.safe_load(config_path.read_text())
    require(config["entry_policies"] == POLICIES, "Unsupported policy set")
    require(config["evaluation"]["split_utc"] == "2025-09-01", "Unsupported split")
    require(config["evaluation"]["require_mean_above_complement_both_periods"],
            "Complement comparison must remain enabled")
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")
    print("Hashing protected Stage 1, Step 1, and Step 2 artifacts...", flush=True)
    before = protected_snapshot()
    DATA.mkdir(parents=True, exist_ok=False)
    RESULTS.mkdir(parents=True, exist_ok=False)
    (RESULTS / "source_manifest_before.json").write_text(json.dumps(before, indent=2) + "\n")
    (RESULTS / "experiment.json").write_text(json.dumps(config, indent=2) + "\n")

    source = yaml.safe_load((ROOT / "config/experiments/v1_stage1.yaml").read_text())
    contexts = []
    selected_sources = {}
    validations = []
    for asset in source["data"]["assets"]:
        raw = pd.read_parquet(
            ROOT / f"data/raw/{asset}/{asset}_1m.parquet",
            columns=["open_time", "open", "high", "low", "close"],
        )
        for timeframe in source["research"]["timeframes"]:
            tag = f"{asset}_{timeframe}"
            print(f"{tag}: calculating context at first-touch boundaries", flush=True)
            candidates = pd.read_parquet(STEP2 / asset / f"{tag}_entry_candidates.parquet")
            selected = candidates.loc[candidates.policy.isin(POLICIES)].copy()
            require(selected.groupby("episode_id").size().eq(2).all(), "Missing entry policy")
            origins = selected.loc[selected.policy.eq("first_touch_0m")].copy().reset_index(drop=True)
            candles = pd.read_parquet(
                ROOT / f"data/processed/{asset}/{tag}_with_averages.parquet",
                columns=["open_time", "open", "high", "low", "close",
                         "average_7d", "average_15d", "average_30d"],
            )
            context = calculate_context(raw, candles, origins, timeframe)
            replay_count = validate_context(raw, candles, origins, context, timeframe)
            contexts.append(context)
            selected_sources[tag] = selected
            validations.append({"dataset": tag, "pass": True,
                                "candidate_rows": len(selected), "episodes": len(origins),
                                "direct_context_values_checked": replay_count})
    context = pd.concat(contexts, ignore_index=True)
    thresholds = fit_volatility_thresholds(context)
    context = apply_volatility_bands(context, thresholds)
    repeated = fit_volatility_thresholds(context)
    pd.testing.assert_frame_equal(thresholds, repeated, check_exact=True)
    require(thresholds.asset.nunique() == 3, "Missing asset thresholds")
    save_csv("volatility_thresholds", thresholds)
    save_csv("market_context", context)

    enriched_parts = []
    for tag, selected in selected_sources.items():
        asset, timeframe = tag.split("_")
        fields = [column for column in context.columns if column not in
                  ["episode_id", "asset", "timeframe", "average_type", "touch_zone",
                   "origin_signal_timestamp", "approach", "origin_regime", "period", "eligible"]]
        enriched = selected.merge(context[["episode_id", *fields]], on="episode_id",
                                  how="left", validate="many_to_one", indicator=True)
        require(enriched._merge.eq("both").all(), "Missing market context")
        enriched = enriched.drop(columns="_merge")
        original_columns = selected.columns.tolist()
        pd.testing.assert_frame_equal(selected.reset_index(drop=True),
                                      enriched[original_columns].reset_index(drop=True), check_exact=True)
        output = DATA / asset
        output.mkdir(exist_ok=True)
        path = output / f"{tag}_market_candidates.parquet"
        enriched.to_parquet(path, index=False)
        persisted = pd.read_parquet(path)
        pd.testing.assert_frame_equal(enriched, persisted, check_exact=True)
        require(not persisted.duplicated(["episode_id", "policy"]).any(), "Duplicate saved candidates")
        enriched_parts.append(persisted)
    all_candidates = pd.concat(enriched_parts, ignore_index=True)
    require(len(all_candidates) == 150313 * 2, "Unexpected candidate total")
    require(all_candidates.loc[all_candidates.eligible & all_candidates.entered,
                               "complete_24h"].eq(True).all(), "Incomplete scored outcomes")

    print("Summarizing conditions and earlier/later stability...", flush=True)
    summary = build_condition_summaries(all_candidates)
    screen = build_stability_screen(summary)
    screen = attach_screen_intervals(screen, all_candidates)
    effects = build_cross_grid_effects(summary)
    save_csv("condition_summary", summary)
    save_csv("stability_screen", screen)
    save_csv("cross_grid_effects", effects)
    save_csv("validation", pd.DataFrame(validations))

    print("Verifying all protected file hashes...", flush=True)
    after = protected_snapshot()
    require(before == after, "Protected prior-stage artifact changed")
    (RESULTS / "source_manifest_after.json").write_text(json.dumps(after, indent=2) + "\n")
    write_report(RESULTS, summary, screen, effects, thresholds, len(before))
    (RESULTS / "SUCCESS.json").write_text(json.dumps({
        "step": 3, "scope": "market_conditions_only", "configurations": 81,
        "entry_policies": POLICIES, "episode_policy_rows": len(all_candidates),
        "condition_summary_rows": len(summary), "stable_hypotheses": int(screen.stability_screen.sum()),
        "protected_files_unchanged": len(before), "validation": "PASS",
    }, indent=2) + "\n")
    print(f"Completed: {RESULTS / 'market_conditions_report.md'}", flush=True)


if __name__ == "__main__":
    run()
