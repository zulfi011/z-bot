"""Run Stage 1.5 Step 4 without modifying any prior-stage artifact."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.research.stage15.validation import sha256
from .reporting import write_report
from .simulator import FixedStopEngine, STOP_LEVELS, require
from .statistics import build_cross_grid, build_stability_screen, build_summaries


ROOT = Path(__file__).resolve().parents[3]
RUN = "step4_downside_protection_v1"
DATA = ROOT / "data/research/stage15" / RUN
RESULTS = ROOT / "results/stage15" / RUN
STEP3 = ROOT / "data/research/stage15/step3_market_conditions_v1"
POLICIES = ["first_touch_0m", "bullish_candle_30m"]


def protected_snapshot():
    paths = []
    excluded_names = {
        "v1_stage15_step4_downside_protection.yaml",
        "test_stage15_downside_protection.py",
    }
    for folder in ["data", "results", "src", "config", "experiments", "tests"]:
        for path in (ROOT / folder).rglob("*"):
            if not path.is_file() or RUN in path.parts or "stage15_risk" in path.parts:
                continue
            if "__pycache__" in path.parts or path.name in excluded_names:
                continue
            paths.append(path)
    paths += [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "V1_Stage1_Historical_Engine_Results.md"]
    return {
        str(path.relative_to(ROOT)): {"size": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(set(paths))
    }


def save_csv(name: str, frame: pd.DataFrame):
    path = RESULTS / f"{name}.csv"
    comparable = frame.copy()
    for column in comparable.select_dtypes(include=["datetimetz", "datetime64"]).columns:
        comparable[column] = comparable[column].astype(str)
    comparable.to_csv(path, index=False)
    loaded = pd.read_csv(path)
    pd.testing.assert_frame_equal(
        comparable.reset_index(drop=True),
        loaded,
        check_dtype=False,
        check_exact=False,
        rtol=1e-9,
        atol=1e-9,
    )


def run():
    config_path = ROOT / "config/experiments/v1_stage15_step4_downside_protection.yaml"
    config = yaml.safe_load(config_path.read_text())
    require(config["entry_policies"] == POLICIES, "Unsupported policy set")
    require(config["stop_levels_pct"] == STOP_LEVELS, "Unsupported stop grid")
    require(config["evaluation"]["split_utc"] == "2025-09-01", "Unsupported split")
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")

    print("Hashing all protected Stage 1 through Step 3 artifacts...", flush=True)
    before = protected_snapshot()
    DATA.mkdir(parents=True, exist_ok=False)
    RESULTS.mkdir(parents=True, exist_ok=False)
    (RESULTS / "source_manifest_before.json").write_text(json.dumps(before, indent=2) + "\n")
    (RESULTS / "experiment.json").write_text(json.dumps(config, indent=2) + "\n")

    stage1 = yaml.safe_load((ROOT / "config/experiments/v1_stage1.yaml").read_text())
    all_parts = []
    validations = []
    for asset in stage1["data"]["assets"]:
        raw = pd.read_parquet(
            ROOT / f"data/raw/{asset}/{asset}_1m.parquet",
            columns=["open_time", "open", "high", "low", "close"],
        )
        engine = FixedStopEngine(raw)
        for timeframe in stage1["research"]["timeframes"]:
            tag = f"{asset}_{timeframe}"
            print(f"{tag}: simulating eight stop levels", flush=True)
            source = pd.read_parquet(STEP3 / asset / f"{tag}_market_candidates.parquet")
            selected = source.loc[source.policy.isin(POLICIES)].copy()
            require(
                selected.groupby("episode_id").size().eq(2).all(),
                "Missing inherited entry policy",
            )
            entered_times = selected.loc[selected.entered, "entry_timestamp"].dropna()
            outcomes = engine.calculate(entered_times)
            replay_count = engine.validate_samples(outcomes)
            enriched = selected.merge(
                outcomes, on="entry_timestamp", how="left", validate="many_to_one", indicator=True
            )
            require(
                enriched.loc[enriched.entered, "_merge"].eq("both").all(),
                "Entered candidate missing stop outcome",
            )
            enriched = enriched.drop(columns="_merge")
            inherited = selected.columns.tolist()
            pd.testing.assert_frame_equal(
                selected.reset_index(drop=True),
                enriched[inherited].reset_index(drop=True),
                check_exact=True,
            )
            scored = enriched.eligible & enriched.entered
            require(enriched.loc[scored, "stop_window_complete_24h"].eq(True).all(), "Incomplete eligible path")
            require(
                np.allclose(
                    enriched.loc[scored, "entry_price"],
                    enriched.loc[scored, "audit_entry_price"],
                    rtol=1e-12,
                    atol=1e-12,
                ),
                "Inherited entry price mismatch",
            )
            require(
                np.allclose(
                    enriched.loc[scored, "return_1440m_pct"],
                    enriched.loc[scored, "audit_hold_return_24h_pct"],
                    rtol=1e-12,
                    atol=1e-12,
                ),
                "Inherited hold return mismatch",
            )
            output = DATA / asset
            output.mkdir(exist_ok=True)
            path = output / f"{tag}_downside_candidates.parquet"
            enriched.to_parquet(path, index=False)
            persisted = pd.read_parquet(path)
            pd.testing.assert_frame_equal(enriched, persisted, check_exact=True)
            require(
                not persisted.duplicated(["episode_id", "policy"]).any(),
                "Duplicate saved candidate",
            )
            all_parts.append(persisted)
            validations.append(
                {
                    "dataset": tag,
                    "pass": True,
                    "candidate_rows": len(selected),
                    "unique_entries": len(outcomes),
                    "direct_paths_checked": replay_count,
                }
            )

    candidates = pd.concat(all_parts, ignore_index=True)
    require(len(candidates) == 150313 * 2, "Unexpected candidate total")
    print("Summarizing paired protection outcomes and stability...", flush=True)
    summary = build_summaries(candidates)
    screen = build_stability_screen(summary, candidates)
    cross_grid = build_cross_grid(summary)
    expected_rows = 81 * len(POLICIES) * 2 * 3 * (len(STOP_LEVELS) + 1)
    require(len(summary) == expected_rows, "Unexpected summary cardinality")
    save_csv("protection_summary", summary)
    save_csv("stability_screen", screen)
    save_csv("cross_grid_effects", cross_grid)
    save_csv("validation", pd.DataFrame(validations))

    print("Verifying protected-file hashes...", flush=True)
    after = protected_snapshot()
    require(before == after, "Protected prior-stage artifact changed")
    (RESULTS / "source_manifest_after.json").write_text(json.dumps(after, indent=2) + "\n")
    write_report(RESULTS, summary, screen, cross_grid, len(before), len(candidates))
    (RESULTS / "SUCCESS.json").write_text(
        json.dumps(
            {
                "step": 4,
                "scope": "fixed_stop_downside_protection",
                "configurations": 81,
                "entry_policies": POLICIES,
                "stop_levels_pct": STOP_LEVELS,
                "candidate_rows": len(candidates),
                "summary_rows": len(summary),
                "stable_combinations": int(screen.stability_screen.sum()),
                "positive_block_ci_both": int(screen.positive_block_ci_both.sum()),
                "protected_files_unchanged": len(before),
                "validation": "PASS",
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Completed: {RESULTS / 'downside_protection_report.md'}", flush=True)


if __name__ == "__main__":
    run()
