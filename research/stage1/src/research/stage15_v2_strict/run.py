"""Run final strict historical robustness audit."""

import json
from pathlib import Path

import pandas as pd
import yaml

from src.research.stage15.validation import sha256
from .analysis import analyze, require
from .reporting import write_report


ROOT = Path(__file__).resolve().parents[3]
RUN = "step5_strict_robustness_v1"
DATA = ROOT / "data/research/stage15_v2" / RUN
RESULTS = ROOT / "results/stage15_v2" / RUN
STEP4 = ROOT / "data/research/stage15_v2/step4_realistic_execution_v1/SOLUSDT"


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


def run():
    config = yaml.safe_load((ROOT / "config/experiments/v1_stage15_v2_step5_strict_robustness.yaml").read_text())
    definitions = config["candidates"]
    require([item["name"] for item in definitions] ==
            ["refined_primary", "current_control", "rising_average_secondary"], "Candidate set changed")
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")
    print("Hashing all pre-existing research artifacts...", flush=True)
    before = protected_snapshot(); DATA.mkdir(parents=True, exist_ok=False); RESULTS.mkdir(parents=True, exist_ok=False)
    (RESULTS / "source_manifest_before.json").write_text(json.dumps(before, indent=2) + "\n")
    (RESULTS / "experiment.json").write_text(json.dumps(config, indent=2) + "\n")

    frames = []
    for timeframe in ["1m", "3m", "5m"]:
        frame = pd.read_parquet(STEP4 / f"SOLUSDT_{timeframe}_execution_candidates.parquet")
        require(not frame.duplicated("episode_id").any(), "Duplicate source episode")
        frames.append(frame)
    candidates = pd.concat(frames, ignore_index=True)
    print("Auditing periods, quarters, tails, drawdowns, neighbors, and confidence intervals...", flush=True)
    summary, quarters, neighbors, events = analyze(candidates, definitions)
    require(len(summary) == 3 and len(neighbors) == 7, "Unexpected audit cardinality")
    require(not events.duplicated(["candidate", "period", "episode_id"]).any(), "Duplicate selected event")
    event_path = DATA / "strict_candidate_events.parquet"; events.to_parquet(event_path, index=False)
    pd.testing.assert_frame_equal(events, pd.read_parquet(event_path), check_exact=True)
    save_csv("candidate_summary", summary); save_csv("quarterly", quarters)
    save_csv("neighbor_sensitivity", neighbors)
    checks = pd.DataFrame([{"candidate": row.candidate,
                            "trade_counts_match_events": len(events.loc[events.candidate.eq(row.candidate)])
                            == row.nonoverlap_trades_earlier + row.nonoverlap_trades_later,
                            "quarter_trade_counts_match": quarters.loc[quarters.candidate.eq(row.candidate), "trades"].sum()
                            == row.nonoverlap_trades_earlier + row.nonoverlap_trades_later,
                            "pass": True} for row in summary.itertuples(index=False)])
    require(checks[["trade_counts_match_events", "quarter_trade_counts_match"]].all().all(), "Audit reconciliation failed")
    save_csv("validation", checks)
    print("Verifying that all earlier research files remain byte-identical...", flush=True)
    after = protected_snapshot(); require(before == after, "A protected pre-existing file changed")
    (RESULTS / "source_manifest_after.json").write_text(json.dumps(after, indent=2) + "\n")
    write_report(RESULTS, summary, quarters, neighbors, len(before))
    (RESULTS / "DECISION.json").write_text(json.dumps({
        "strict_robust_candidates": summary.loc[summary.strict_robust_pass, "candidate"].tolist(),
        "provisional_candidates": summary.loc[summary.provisional_pass, "candidate"].tolist(),
        "official_stage2_approved": bool(summary.strict_robust_pass.any()),
        "reason_if_not_approved": "positive confidence lower bound required in both periods",
    }, indent=2) + "\n")
    (RESULTS / "SUCCESS.json").write_text(json.dumps({
        "step": "stage15_v2_step5", "scope": "strict_robustness",
        "candidate_count": len(summary), "provisional_passes": int(summary.provisional_pass.sum()),
        "strict_robust_passes": int(summary.strict_robust_pass.sum()), "event_rows": len(events),
        "protected_files_unchanged": len(before), "validation": "PASS",
    }, indent=2) + "\n")
    print(f"Completed: {RESULTS / 'strict_robustness_report.md'}", flush=True)


if __name__ == "__main__":
    run()
