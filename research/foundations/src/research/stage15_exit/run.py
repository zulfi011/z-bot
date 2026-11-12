"""Run Stage 1.5 Step 5 while preserving every earlier artifact."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.research.stage15.validation import sha256
from .reporting import write_report
from .simulator import ExitEngine, HOLD_MINUTES, TARGETS, TRAIL_GIVEBACKS, require
from .statistics import build_cross_grid, build_stability_screen, build_summaries, strategy_specs


ROOT = Path(__file__).resolve().parents[3]
RUN = "step5_exits_v1"
DATA = ROOT / "data/research/stage15" / RUN
RESULTS = ROOT / "results/stage15" / RUN
STEP4 = ROOT / "data/research/stage15/step4_downside_protection_v1"
POLICIES = ["first_touch_0m", "bullish_candle_30m"]


def protected_snapshot():
    paths = []
    excluded = {"v1_stage15_step5_exits.yaml", "test_stage15_exits.py"}
    for folder in ["data", "results", "src", "config", "experiments", "tests"]:
        for path in (ROOT / folder).rglob("*"):
            if not path.is_file() or RUN in path.parts or "stage15_exit" in path.parts:
                continue
            if "__pycache__" in path.parts or path.name in excluded:
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


def run():
    config_path = ROOT / "config/experiments/v1_stage15_step5_exits.yaml"
    config = yaml.safe_load(config_path.read_text())
    require(config["entry_policies"] == POLICIES, "Unsupported policy set")
    require(config["exit_families"]["fixed_time_minutes"] == HOLD_MINUTES, "Unsupported holds")
    require(config["exit_families"]["target_then_24h_pct"] == TARGETS, "Unsupported targets")
    require(config["exit_families"]["trailing"]["giveback_of_open_profit_pct"] == TRAIL_GIVEBACKS, "Unsupported trails")
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")

    print("Hashing all protected Stage 1 through Step 4 artifacts...", flush=True)
    before = protected_snapshot()
    DATA.mkdir(parents=True, exist_ok=False)
    RESULTS.mkdir(parents=True, exist_ok=False)
    (RESULTS / "source_manifest_before.json").write_text(json.dumps(before, indent=2) + "\n")
    (RESULTS / "experiment.json").write_text(json.dumps(config, indent=2) + "\n")

    stage1 = yaml.safe_load((ROOT / "config/experiments/v1_stage1.yaml").read_text())
    all_parts, validations = [], []
    for asset in stage1["data"]["assets"]:
        raw = pd.read_parquet(
            ROOT / f"data/raw/{asset}/{asset}_1m.parquet",
            columns=["open_time", "open", "high", "low", "close"],
        )
        engine = ExitEngine(raw)
        sources = {}
        entry_times = []
        for timeframe in stage1["research"]["timeframes"]:
            tag = f"{asset}_{timeframe}"
            source = pd.read_parquet(STEP4 / asset / f"{tag}_downside_candidates.parquet")
            selected = source.loc[source.policy.isin(POLICIES)].copy()
            require(selected.groupby("episode_id").size().eq(2).all(), "Missing inherited entry policy")
            sources[timeframe] = selected
            entry_times.append(selected.loc[selected.entered, "entry_timestamp"].dropna())
        unique_times = pd.concat(entry_times).drop_duplicates().sort_values()
        print(f"{asset}: simulating exits for {len(unique_times):,} unique entries", flush=True)
        outcomes = engine.calculate(unique_times)
        replay_count = engine.validate_samples(outcomes)

        for timeframe, selected in sources.items():
            tag = f"{asset}_{timeframe}"
            enriched = selected.merge(
                outcomes, on="entry_timestamp", how="left", validate="many_to_one", indicator=True
            )
            require(enriched.loc[enriched.entered, "_merge"].eq("both").all(), "Missing exit outcome")
            enriched = enriched.drop(columns="_merge")
            inherited = selected.columns.tolist()
            pd.testing.assert_frame_equal(
                selected.reset_index(drop=True), enriched[inherited].reset_index(drop=True), check_exact=True
            )
            scored = enriched.eligible & enriched.entered
            require(enriched.loc[scored, "exit_window_complete_24h"].eq(True).all(), "Incomplete eligible path")
            require(np.allclose(enriched.loc[scored, "entry_price"], enriched.loc[scored, "exit_audit_entry_price"], rtol=1e-12, atol=1e-12), "Entry mismatch")
            require(np.allclose(enriched.loc[scored, "return_1440m_pct"], enriched.loc[scored, "hold_1440m_return_pct"], rtol=1e-12, atol=1e-12), "Baseline mismatch")
            # The exact same 4% stop must bridge Step 4 into Step 5.
            require(np.allclose(enriched.loc[scored, "stop_4_fill_return_pct"], enriched.loc[scored, "exit_stop_4_fill_return_pct"], equal_nan=True, rtol=1e-12, atol=1e-12), "Step 4 stop bridge mismatch")
            output = DATA / asset
            output.mkdir(exist_ok=True)
            path = output / f"{tag}_exit_candidates.parquet"
            enriched.to_parquet(path, index=False)
            persisted = pd.read_parquet(path)
            pd.testing.assert_frame_equal(enriched, persisted, check_exact=True)
            require(not persisted.duplicated(["episode_id", "policy"]).any(), "Duplicate candidate")
            all_parts.append(persisted)
            validations.append({"dataset": tag, "pass": True, "candidate_rows": len(selected),
                                "asset_unique_entries": len(outcomes), "direct_paths_checked": replay_count})

    candidates = pd.concat(all_parts, ignore_index=True)
    require(len(candidates) == 150313 * 2, "Unexpected candidate total")
    print("Summarizing exit families and temporal stability...", flush=True)
    summary = build_summaries(candidates)
    expected = 81 * len(POLICIES) * 2 * 3 * len(strategy_specs())
    require(len(summary) == expected, "Unexpected summary cardinality")
    screen = build_stability_screen(summary, candidates)
    cross = build_cross_grid(summary)
    save_csv("exit_summary", summary)
    save_csv("stability_screen", screen)
    save_csv("cross_grid_effects", cross)
    save_csv("validation", pd.DataFrame(validations))

    print("Verifying protected-file hashes...", flush=True)
    after = protected_snapshot()
    require(before == after, "Protected prior-stage artifact changed")
    (RESULTS / "source_manifest_after.json").write_text(json.dumps(after, indent=2) + "\n")
    write_report(RESULTS, summary, screen, cross, len(before), len(candidates))
    (RESULTS / "SUCCESS.json").write_text(json.dumps({
        "step": 5, "scope": "exit_and_holding_time", "configurations": 81,
        "entry_policies": POLICIES, "exit_strategies": len(strategy_specs()),
        "candidate_rows": len(candidates), "summary_rows": len(summary),
        "stable_combinations": int(screen.stability_screen.sum()),
        "positive_block_ci_both": int(screen.positive_block_ci_both.sum()),
        "protected_files_unchanged": len(before), "validation": "PASS",
    }, indent=2) + "\n")
    print(f"Completed: {RESULTS / 'exit_holding_report.md'}", flush=True)


if __name__ == "__main__":
    run()
