"""Run isolated deduplication and comparisons. Existing run directories are refused.

Usage: python -B -m src.research.stage15.run_step1
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from .episodes import AVERAGES, KEYS, RULE, ZONES, build_episodes, require
from .metrics import required_columns, summarize
from .validation import sha256, validate_baseline, validate_partition

ROOT = Path(__file__).resolve().parents[3]
RUN = "step1_consecutive_touch_first_v1"
DATA = ROOT / "data/research/stage15" / RUN
RESULTS = ROOT / "results/stage15" / RUN


def protected_files() -> list[Path]:
    paths = []
    for directory in ["data/raw", "data/processed", "data/research", "results", "src", "config", "experiments"]:
        for path in (ROOT / directory).rglob("*"):
            if path.is_file() and "stage15" not in path.parts and "__pycache__" not in path.parts:
                if path.name != "v1_stage15_step1.yaml":
                    paths.append(path)
    paths += [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "V1_Stage1_Historical_Engine_Results.md"]
    return sorted(set(paths))


def snapshot(paths: list[Path]) -> dict:
    return {str(path.relative_to(ROOT)): {"size": path.stat().st_size, "sha256": sha256(path)}
            for path in paths}


def group_summaries(frame: pd.DataFrame, regime: bool = False) -> list[dict]:
    keys = [*KEYS, "market_regime"] if regime else KEYS
    return [{**dict(zip(keys, key)), **summarize(group)}
            for key, group in frame.groupby(keys, sort=True, dropna=False, observed=True)]


def comparison(original: pd.DataFrame, deduplicated: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    metrics = [c for c in original if c not in keys]
    left = original.melt(id_vars=keys, value_vars=metrics, var_name="metric", value_name="stage1")
    right = deduplicated.melt(id_vars=keys, value_vars=metrics, var_name="metric", value_name="stage15")
    output = left.merge(right, on=[*keys, "metric"], how="outer", validate="one_to_one")
    output["difference"] = output.stage15 - output.stage1
    return output


def retained_enriched(source: Path, selected_ids: set[str]) -> pd.DataFrame:
    parquet = pq.ParquetFile(source)
    chunks = []
    seen = 0
    for batch in parquet.iter_batches(batch_size=32768):
        table = pa.Table.from_batches([batch])
        ids = table.column("event_id").to_pylist()
        mask = [event_id in selected_ids for event_id in ids]
        seen += sum(mask)
        if any(mask):
            chunks.append(table.filter(pa.array(mask)))
    require(seen == len(selected_ids), "Missing/duplicate enriched representative")
    return pa.concat_tables(chunks).to_pandas()


def execute() -> None:
    config_path = ROOT / "config/experiments/v1_stage15_step1.yaml"
    config = yaml.safe_load(config_path.read_text())
    require(config["rule"] == {
        "name": RULE, "group_by": KEYS, "representative": "first_touch_candle",
        "reset": "one_complete_non_touch_candle", "missing_intervals": "reject",
        "average_update": "no_automatic_reset", "boundary_runs": "retain_and_mark_censored",
        "outcomes": "reuse_unchanged_stage1_event_id", "timing": "preserve_stage1_conventions",
        "independence": "distinct_contiguous_runs_not_statistically_independent_trades",
    }, "Unsupported rule: implement and version changes explicitly")
    stage1_config = yaml.safe_load((ROOT / config["source_config"]).read_text())
    assets = stage1_config["data"]["assets"]
    timeframes = stage1_config["research"]["timeframes"]
    require(stage1_config["research"]["averages"] == AVERAGES
            and stage1_config["research"]["touch_zones_pct"] == list(ZONES), "Unsupported source grid")
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; will not overwrite")
    print("Hashing protected Stage 1 files before execution...", flush=True)
    before = snapshot(protected_files())
    DATA.mkdir(parents=True, exist_ok=False)
    RESULTS.mkdir(parents=True, exist_ok=False)
    (RESULTS / "source_manifest_before.json").write_text(json.dumps(before, indent=2) + "\n")
    (RESULTS / "experiment.json").write_text(json.dumps(config, indent=2) + "\n")
    original_rows, selected_rows, regime_before, regime_after, count_rows, checks = [], [], [], [], [], []
    for asset in assets:
        for timeframe in timeframes:
            tag = f"{asset}_{timeframe}"
            print(f"Building and validating {tag}...", flush=True)
            event_path = ROOT / f"data/research/{asset}/{tag}_touch_events.parquet"
            candle_path = ROOT / f"data/processed/{asset}/{tag}_with_touches.parquet"
            candle_columns = ["open_time", "high", "low", "close"]
            candle_columns += [f"average_{a}" for a in AVERAGES]
            candle_columns += [f"touch_{a}_{z}" for a in AVERAGES for z in ZONES.values()]
            events = pd.read_parquet(event_path)
            candles = pd.read_parquet(candle_path, columns=candle_columns)
            membership, episodes = build_episodes(candles, events, asset, timeframe)
            del candles
            out = DATA / asset
            out.mkdir(exist_ok=True)
            membership.to_parquet(out / f"{tag}_event_membership.parquet", index=False)
            episodes.to_parquet(out / f"{tag}_episodes.parquet", index=False)
            saved_membership = pd.read_parquet(out / f"{tag}_event_membership.parquet")
            saved_episodes = pd.read_parquet(out / f"{tag}_episodes.parquet")
            pd.testing.assert_frame_equal(membership, saved_membership, check_exact=True)
            pd.testing.assert_frame_equal(episodes, saved_episodes, check_exact=True)
            n = validate_partition(events, saved_membership, saved_episodes, timeframe)
            selected_ids = set(episodes.representative_event_id)
            enriched_path = ROOT / f"data/research/{asset}/{tag}_touch_events_with_trailing_research.parquet"
            selected = retained_enriched(enriched_path, selected_ids)
            pd.testing.assert_frame_equal(
                events.set_index("event_id").loc[sorted(selected_ids)].sort_index(),
                selected.set_index("event_id").loc[sorted(selected_ids), events.columns.drop("event_id")].sort_index(),
                check_exact=True)
            selected.to_parquet(out / f"{tag}_episode_outcomes.parquet", index=False)
            persisted = pd.read_parquet(out / f"{tag}_episode_outcomes.parquet")
            pd.testing.assert_frame_equal(selected, persisted, check_exact=True)
            # All original outcome columns are preserved exactly, including nulls.
            checks.append({"dataset": tag, "check": "source_formula_coverage_partition_roundtrip_and_all_retained_columns",
                           "pass": True, "checked_items": n + selected.size})
            for key, part in episodes.groupby(KEYS):
                old = membership.loc[membership.average_type.eq(key[2]) & membership.touch_zone.eq(key[3])]
                separated = part.start_timestamp.sort_values().diff().dropna()
                count_rows.append({**dict(zip(KEYS, key)), "stage1_events": len(old),
                    "episodes": len(part), "suppressed_events": len(old) - len(part),
                    "reduction_pct": (1 - len(part) / len(old)) * 100,
                    "median_touch_candles": part.touch_candle_count.median(),
                    "max_touch_candles": part.touch_candle_count.max(),
                    "left_censored_episodes": int(part.left_censored.sum()),
                    "right_censored_episodes": int(part.right_censored.sum()),
                    "next_start_within_24h_count": int(separated.lt(pd.Timedelta('24h')).sum())})
            del events, membership, saved_membership, saved_episodes, selected, persisted
            original = pd.read_parquet(enriched_path, columns=required_columns())
            require(original.event_id.is_unique, "Duplicate enriched event IDs")
            regime = pd.read_parquet(ROOT / f"data/research/{asset}/{tag}_touch_events_with_regime.parquet",
                                     columns=["event_id", "market_regime"])
            original = original.merge(regime, on="event_id", how="left", validate="one_to_one", indicator=True)
            require(original._merge.eq("both").all(), "Missing regime mapping")
            original["market_regime"] = original.market_regime.fillna("missing")
            selected = original.loc[original.event_id.isin(selected_ids)]
            require(len(selected) == len(selected_ids), "Selection cardinality changed")
            original_rows.extend(group_summaries(original))
            selected_rows.extend(group_summaries(selected))
            regime_before.extend(group_summaries(original, regime=True))
            regime_after.extend(group_summaries(selected, regime=True))
            del original, selected, regime
    baseline, refined = pd.DataFrame(original_rows), pd.DataFrame(selected_rows)
    baseline_regime, refined_regime = pd.DataFrame(regime_before), pd.DataFrame(regime_after)
    n = validate_baseline(baseline, pd.read_csv(ROOT / "results/tables/stage1_configuration_summary.csv"))
    checks.append({"dataset": "all", "check": "recomputed_stage1_metrics_match_validated_summary",
                   "pass": True, "checked_items": n})
    counts = pd.DataFrame(count_rows)
    require(len(counts) == 81 and len(refined) == 81, "Expected 81 configurations")
    require((counts.stage1_events == counts.episodes + counts.suppressed_events).all(), "Count reconciliation")
    tables = {"stage1_recomputed_summary": baseline, "deduplicated_summary": refined,
              "episode_counts": counts, "comparison": comparison(baseline, refined, KEYS),
              "stage1_regime_summary": baseline_regime, "deduplicated_regime_summary": refined_regime,
              "regime_comparison": comparison(baseline_regime, refined_regime, [*KEYS, "market_regime"])}
    for name, table in tables.items():
        path = RESULTS / f"{name}.csv"
        table.to_csv(path, index=False)
        loaded = pd.read_csv(path)
        pd.testing.assert_frame_equal(table.reset_index(drop=True), loaded, check_dtype=False,
                                      check_exact=False, rtol=1e-10, atol=1e-10)
    print("Verifying SHA-256 of all protected Stage 1 files...", flush=True)
    after = snapshot(protected_files())
    require(before == after, "Protected Stage 1 file changed")
    (RESULTS / "source_manifest_after.json").write_text(json.dumps(after, indent=2) + "\n")
    checks.append({"dataset": "all", "check": "protected_stage1_sha256_unchanged", "pass": True,
                   "checked_items": len(before)})
    pd.DataFrame(checks).to_csv(RESULTS / "validation.csv", index=False)
    write_report(counts, baseline, refined, refined_regime, checks)
    (RESULTS / "SUCCESS.json").write_text(json.dumps({"rule": RULE, "configurations": 81,
        "stage1_events": int(counts.stage1_events.sum()), "episodes": int(counts.episodes.sum()),
        "protected_files": len(before), "validation": "PASS", "scope": "Step 1 only"}, indent=2) + "\n")
    print((RESULTS / "step1_report.md").read_text(), flush=True)


def write_report(counts, baseline, refined, regimes, checks):
    def primary(frame):
        return frame.loc[frame.asset.eq("SOLUSDT") & frame.timeframe.eq("5m")
                         & frame.average_type.eq("15d") & frame.touch_zone.eq(.5)].iloc[0]
    count, old, new = primary(counts), primary(baseline), primary(refined)
    metrics = ["forward_return_total_event_count", "complete_24h_event_count", "reach_probability_pct",
               "median_time_to_target_minutes", "return_24h_median_pct", "mae_24h_median_pct",
               "mfe_24h_median_pct", "median_mfe_mae_ratio", "target_2_5_first_vs_stop_2_5_pct",
               "first_2_5_target_first_decisive_pct", "activated_event_count", "trail30_resolved_pct",
               "trail30_ambiguous_pct", "trail30_median_realized_return_pct"]
    lines = ["# Stage 1.5 Step 1 — Touch Deduplication", "", "## Rule and scope", "",
        "One episode is a maximal consecutive run of touching candles per asset/timeframe/average/zone. "
        "Keep the first candle at its close; reset after one complete non-touch candle. "
        "Daily average updates alone do not reset a run. Missing candle intervals are rejected. "
        "Boundary/warm-up runs are retained and marked censored. Episode ends and lengths are retrospective audit metadata, never selection inputs.", "",
        "Stage 1 IDs, prices, forward-return timing, future windows, nullable outcomes, and ambiguity treatment are preserved. "
        "All retained enriched columns are copied exactly by event ID. No trading state, costs, or parameter optimization is introduced.", "",
        "## Population", "",
        f"Across 81 configurations: {int(counts.stage1_events.sum()):,} classified observations → "
        f"{int(counts.episodes.sum()):,} episodes ({100*(1-counts.episodes.sum()/counts.stage1_events.sum()):.2f}% reduction). "
        "These totals include overlapping average, zone, and timeframe classifications.", "",
        f"Primary SOLUSDT / 5m / 15D / ±0.5%: {int(count.stage1_events):,} → {int(count.episodes):,} "
        f"({count.reduction_pct:.2f}% reduction); left-censored {int(count.left_censored_episodes)}, "
        f"right-censored {int(count.right_censored_episodes)}.", "",
        "## Primary comparison", "", "| Metric | Stage 1 | Deduplicated | Difference |",
        "|---|---:|---:|---:|"]
    for metric in metrics:
        lines.append(f"| {metric} | {old[metric]:.6g} | {new[metric]:.6g} | {new[metric]-old[metric]:+.6g} |")
    before = baseline.set_index(KEYS)
    after = refined.set_index(KEYS)
    differences = after - before
    lines += ["", "## Findings across the full grid", "",
        "| Metric | Configurations higher | Configurations lower | Median change |",
        "|---|---:|---:|---:|"]
    for metric in ["return_24h_median_pct", "reach_probability_pct", "mae_24h_median_pct",
                   "mfe_24h_median_pct", "median_mfe_mae_ratio", "first_2_5_target_first_decisive_pct"]:
        changes = differences[metric]
        lines.append(f"| {metric} | {int(changes.gt(0).sum())} | {int(changes.lt(0).sum())} | {changes.median():+.6g} |")
    lines += ["", "A lower MAE means a more negative adverse excursion. The primary candidate retains "
        "positive median 24h forward behavior and improves target reach, but experiences deeper downside. "
        "Across the full grid, first-touch selection generally weakens the median return and excursion balance. "
        "These are descriptive changes on the same historical period, not independent significance tests.", "",
        "## Primary regime sensitivity", "",
        "| Regime | Episodes | Median 24h return (%) | Median MAE (%) | Median MFE (%) | MFE/MAE | Target-first decisive (%) |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    subset = regimes.loc[regimes.asset.eq("SOLUSDT") & regimes.timeframe.eq("5m")
                         & regimes.average_type.eq("15d") & regimes.touch_zone.eq(.5)]
    for _, row in subset.iterrows():
        lines.append(f"| {row.market_regime} | {int(row.forward_return_total_event_count)} | "
                     f"{row.return_24h_median_pct:.4f} | {row.mae_24h_median_pct:.4f} | "
                     f"{row.mfe_24h_median_pct:.4f} | {row.median_mfe_mae_ratio:.4f} | "
                     f"{row.first_2_5_target_first_decisive_pct:.4f} |")
    lines += ["", "The Stage 1 Neutral-regime preference is sensitive to observation weighting. "
        "For this first-touch population, Bullish has a larger median forward return and MFE/MAE ratio "
        "than Neutral; Bearish has a negative median 24h return. This warrants reassessment, not a new "
        "regime filter within Step 1. The missing group lacks all three completed-day averages."]
    lines += ["", "Percentage metric differences are percentage points; ratios and counts retain their own units.", "",
        "## Validation", "", f"All {len(checks)} recorded validation groups passed. "
        "Full candle formula and event coverage checks; independent timestamp-gap partition reconstruction; "
        "one first representative per episode; exact retained outcome and Parquet round-trip equality; "
        "recomputed baseline compared numerically against the validated 81-row Stage 1 summary; "
        "CSV round trips; before/after SHA-256 equality of protected Stage 1 files.", "",
        "## Interpretation and limits", "",
        "Deduplication changes the weighting from every touching candle to the beginning of each contiguous interaction. "
        "It does not prove statistical independence: nested zones, shared averages/timeframes, nearby re-entries, "
        "and overlapping 24h windows remain. The one-non-touch reset is an explicit minimal rule, not an optimized cooldown.", "",
        f"Primary configuration has {int(count.next_start_within_24h_count)} subsequent episode starts less than 24h "
        "after the preceding start. This is not a non-overlapping trade backtest.", "",
        "Target reach uses confirmed hit/non-hit outcomes (unknown excluded); MAE/MFE use complete windows; "
        "first-hit reports all-confirmed and decisive denominators separately; trailing statistics condition on activation "
        "and resolved/confirmed outcomes. The MFE/MAE ratio is a ratio of population medians, not a median event ratio. "
        "Forward returns remain anchored to candle open plus horizon; excursion windows start after candle completion.", "",
        "A first-touch sample is a changed hypothesis population, not evidence of profitability. "
        "No significance or live-performance claim is made. Missing-regime observations are preserved as a separate group.", "",
        "## Artifacts and reproduction", "",
        "Run `python -B -m src.research.stage15.run_step1` from the project environment. "
        "Existing run directories are refused. A run is complete only when SUCCESS.json exists. "
        "Run `python -B -m pytest tests/test_stage15_deduplication.py` for synthetic boundary and causal tests.", "",
        "Per asset/timeframe, event_membership maps every Stage 1 row to an episode; episodes contains audit metadata; "
        "episode_outcomes preserves the selected original enriched rows. Comparison CSVs cover every horizon, "
        "target, excursion window, first-hit stop, trailing giveback, and regime. Differences use identical formulas on both populations.", "",
        "Stopped after Step 1. No further refinement or Stage 2 work performed.", ""]
    (RESULTS / "step1_report.md").write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    execute()
