"""Run the final Stage 1.5 robustness and selection audit."""

import json
from pathlib import Path

import pandas as pd
import yaml

from src.research.stage15.validation import sha256
from src.research.stage15_exit.statistics import strategy_specs
from .analysis import CONDITIONS, KEYS, apply_selection, build_robustness, condition_mask, require, select_nonoverlap
from .reporting import write_report


ROOT = Path(__file__).resolve().parents[3]
RUN = "step6_robustness_selection_v1"
DATA = ROOT / "data/research/stage15" / RUN
RESULTS = ROOT / "results/stage15" / RUN
STEP5 = ROOT / "data/research/stage15/step5_exits_v1"
POLICIES = ["first_touch_0m", "bullish_candle_30m"]


def protected_snapshot():
    paths = []
    excluded = {"v1_stage15_step6_robustness.yaml", "test_stage15_robustness.py"}
    for folder in ["data", "results", "src", "config", "experiments", "tests"]:
        for path in (ROOT / folder).rglob("*"):
            if not path.is_file() or RUN in path.parts or "stage15_robustness" in path.parts:
                continue
            if "__pycache__" in path.parts or path.name in excluded:
                continue
            paths.append(path)
    paths += [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "V1_Stage1_Historical_Engine_Results.md"]
    return {str(p.relative_to(ROOT)): {"size": p.stat().st_size, "sha256": sha256(p)} for p in sorted(set(paths))}


def save_csv(name, frame):
    path = RESULTS / f"{name}.csv"
    frame.to_csv(path, index=False)
    loaded = pd.read_csv(path)
    pd.testing.assert_frame_equal(frame.reset_index(drop=True), loaded, check_dtype=False,
                                  check_exact=False, rtol=1e-9, atol=1e-9)


def reconstruct_selected_events(candidates, selection):
    chosen = selection.loc[selection.provisional_selection].head(25)
    rows = []
    for candidate in chosen.itertuples(index=False):
        setup = candidates.loc[
            candidates.asset.eq(candidate.asset) & candidates.timeframe.eq(candidate.timeframe)
            & candidates.average_type.eq(candidate.average_type) & candidates.touch_zone.eq(candidate.touch_zone)
            & candidates.policy.eq(candidate.policy)
            & candidates.eligible & candidates.entered & candidates.exit_window_complete_24h
        ]
        setup = setup.loc[condition_mask(setup, candidate.condition_variant)]
        for period in ["earlier", "later"]:
            current = setup.loc[setup.period.eq(period)]
            selected = select_nonoverlap(current, f"{candidate.strategy}_duration_minutes").copy()
            selected = selected[["episode_id", "entry_timestamp", "origin_signal_timestamp"]]
            selected["asset"] = candidate.asset; selected["timeframe"] = candidate.timeframe
            selected["average_type"] = candidate.average_type; selected["touch_zone"] = candidate.touch_zone
            selected["policy"] = candidate.policy; selected["condition_variant"] = candidate.condition_variant
            selected["strategy"] = candidate.strategy; selected["period"] = period
            selected["gross_return_pct"] = setup.loc[selected.index, f"{candidate.strategy}_return_pct"]
            selected["net_0_2_return_pct"] = selected.gross_return_pct - .2
            selected["duration_minutes"] = setup.loc[selected.index, f"{candidate.strategy}_duration_minutes"]
            rows.append(selected)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def build_stage2_shortlist(selection):
    definitions = [
        ("primary_provisional", "SOLUSDT", "5m", "15d", .5, "bullish_candle_30m", "from_below", "target_4_stop_4"),
        ("entry_sensitivity", "SOLUSDT", "5m", "15d", .5, "first_touch_0m", "from_below", "target_4_stop_4"),
        ("secondary_sol_family", "SOLUSDT", "3m", "15d", 1.5, "first_touch_0m", "bullish_regime", "target_1_5_no_stop"),
        ("secondary_eth_family", "ETHUSDT", "3m", "15d", 1.0, "bullish_candle_30m", "bullish_regime", "time_480_no_stop"),
    ]
    rows = []
    for role, asset, timeframe, average, zone, policy, condition, strategy in definitions:
        match = selection.loc[
            selection.asset.eq(asset) & selection.timeframe.eq(timeframe)
            & selection.average_type.eq(average) & selection.touch_zone.eq(zone)
            & selection.policy.eq(policy) & selection.condition_variant.eq(condition)
            & selection.strategy.eq(strategy)
        ]
        require(len(match) == 1 and bool(match.iloc[0].provisional_selection), "Shortlist member is not provisional")
        row = match.iloc[0].copy(); row["selection_role"] = role; rows.append(row)
    columns = [
        "selection_role", "asset", "timeframe", "average_type", "touch_zone", "policy",
        "condition_variant", "strategy", "nonoverlap_trades_earlier", "nonoverlap_trades_later",
        "nonoverlap_net_0_2_mean_pct_earlier", "nonoverlap_net_0_2_mean_pct_later",
        "positive_quarters_pct", "net_0_2_ci95_low_earlier", "net_0_2_ci95_high_earlier",
        "net_0_2_ci95_low_later", "net_0_2_ci95_high_later", "provisional_selection",
        "robust_selection",
    ]
    return pd.DataFrame(rows)[columns]


def run():
    config = yaml.safe_load((ROOT / "config/experiments/v1_stage15_step6_robustness.yaml").read_text())
    require(config["entry_policies"] == POLICIES, "Unsupported policies")
    require(config["condition_variants"] == CONDITIONS, "Unsupported conditions")
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")
    print("Hashing protected Stage 1 through Step 5 artifacts...", flush=True)
    before = protected_snapshot()
    DATA.mkdir(parents=True, exist_ok=False); RESULTS.mkdir(parents=True, exist_ok=False)
    (RESULTS / "source_manifest_before.json").write_text(json.dumps(before, indent=2) + "\n")
    (RESULTS / "experiment.json").write_text(json.dumps(config, indent=2) + "\n")

    frames, validations = [], []
    stage1 = yaml.safe_load((ROOT / "config/experiments/v1_stage1.yaml").read_text())
    for asset in stage1["data"]["assets"]:
        for timeframe in stage1["research"]["timeframes"]:
            tag = f"{asset}_{timeframe}"
            frame = pd.read_parquet(STEP5 / asset / f"{tag}_exit_candidates.parquet")
            frame = frame.loc[frame.policy.isin(POLICIES)].copy()
            require(not frame.duplicated(["episode_id", "policy"]).any(), "Duplicate source candidate")
            frames.append(frame)
            validations.append({"dataset": tag, "pass": True, "candidate_rows": len(frame)})
    candidates = pd.concat(frames, ignore_index=True)
    require(len(candidates) == 150313 * 2, "Unexpected source cardinality")
    strategies = [item[0] for item in strategy_specs()]
    print(f"Evaluating {len(strategies):,} exits × {len(CONDITIONS)} condition variants...", flush=True)
    robustness, quarters = build_robustness(candidates, strategies)
    require(len(robustness) == 81 * 2 * len(strategies) * len(CONDITIONS), "Unexpected robustness cardinality")
    selection = apply_selection(robustness, candidates)
    shortlist = build_stage2_shortlist(selection)
    selected_events = reconstruct_selected_events(candidates, selection)
    require(not selected_events.duplicated([*KEYS, "period", "episode_id"]).any(), "Duplicate selected event")
    DATA.joinpath("selected_candidate_events.parquet").parent.mkdir(parents=True, exist_ok=True)
    selected_events.to_parquet(DATA / "selected_candidate_events.parquet", index=False)
    persisted = pd.read_parquet(DATA / "selected_candidate_events.parquet")
    pd.testing.assert_frame_equal(selected_events, persisted, check_exact=True)
    save_csv("selection", selection)
    save_csv("provisional_shortlist", selection.loc[selection.provisional_selection].reset_index(drop=True))
    save_csv("stage2_candidate_shortlist", shortlist.reset_index(drop=True))
    save_csv("quarterly", quarters)
    save_csv("validation", pd.DataFrame(validations))

    print("Verifying protected-file hashes...", flush=True)
    after = protected_snapshot(); require(before == after, "Protected prior-stage artifact changed")
    (RESULTS / "source_manifest_after.json").write_text(json.dumps(after, indent=2) + "\n")
    write_report(RESULTS, selection, quarters, len(before), len(candidates), len(selected_events))
    (RESULTS / "SUCCESS.json").write_text(json.dumps({
        "step": 6, "scope": "robustness_and_selection", "evaluated_combinations": len(selection),
        "provisional_candidates": int(selection.provisional_selection.sum()),
        "robust_candidates": int(selection.robust_selection.sum()),
        "stage2_shortlist_candidates": len(shortlist),
        "candidate_event_rows": len(selected_events), "protected_files_unchanged": len(before),
        "validation": "PASS",
    }, indent=2) + "\n")
    print(f"Completed: {RESULTS / 'robustness_selection_report.md'}", flush=True)


if __name__ == "__main__": run()
