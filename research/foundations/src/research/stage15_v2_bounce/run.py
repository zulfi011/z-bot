"""Run Stage 1.5 v2 Step 1 confirmed-bounce entry research."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.research.stage15.validation import sha256
from src.research.stage15_robustness.analysis import quarter_labels, select_nonoverlap
from .analysis import CONFIG_KEYS, attach_screen, build_summary, summarize_period
from .reporting import write_report
from .signals import POLICIES, generate_candidates, require
from .simulator import FixedExitEngine


ROOT = Path(__file__).resolve().parents[3]
RUN = "step1_bounce_entries_v1"
DATA = ROOT / "data/research/stage15_v2" / RUN
RESULTS = ROOT / "results/stage15_v2" / RUN
STEP1 = ROOT / "data/research/stage15/step1_consecutive_touch_first_v1"
STEP5 = ROOT / "data/research/stage15/step5_exits_v1"
SPLIT = pd.Timestamp("2025-09-01", tz="UTC")
COMMON_TAIL = pd.Timedelta(minutes=1510)


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


def validate_candidates(candles, candidates, timeframe):
    delta = pd.Timedelta(timeframe)
    confirmed = candidates.loc[candidates.status.eq("confirmed")]
    require((confirmed.reclaim_candle_timestamp < confirmed.breakout_candle_timestamp).all(),
            "Breakout was not later than reclaim")
    require((confirmed.entry_timestamp == confirmed.breakout_candle_timestamp + delta).all(),
            "Entry did not wait for breakout candle close")
    limits = {"bounce_break_immediate": delta.total_seconds() / 60,
              "bounce_break_15m": 15, "bounce_break_30m": 30}
    for policy, limit in limits.items():
        subset = confirmed.loc[confirmed.policy.eq(policy)]
        require(subset.breakout_delay_minutes.le(limit).all(), "Breakout window exceeded")
    wide = candidates.pivot(index="episode_id", columns="policy", values="entry_timestamp")
    immediate = wide.bounce_break_immediate.notna()
    fifteen = wide.bounce_break_15m.notna()
    require((~immediate | (wide.bounce_break_immediate == wide.bounce_break_15m)).all(),
            "Immediate confirmation differs under longer window")
    require((~fifteen | wide.bounce_break_30m.notna()).all(), "15-minute confirmation absent at 30 minutes")
    return len(confirmed)


def baseline_summary(source_config, raw_ends):
    rows = []
    for asset in source_config["data"]["assets"]:
        data_end = raw_ends[asset]
        for timeframe in source_config["research"]["timeframes"]:
            tag = f"{asset}_{timeframe}"
            source = pd.read_parquet(STEP5 / asset / f"{tag}_exit_candidates.parquet")
            base = source.loc[source.policy.eq("bullish_candle_30m") & source.approach.eq("from_below")].copy()
            origin = base.origin_signal_timestamp
            crossing = origin.lt(SPLIT) & (origin + COMMON_TAIL > SPLIT)
            base["eligible"] = ~base.left_censored & (origin + COMMON_TAIL <= data_end) & ~crossing
            base["period"] = np.where(origin < SPLIT, "earlier", "later")
            base["gross_return_pct"] = base.target_4_stop_4_return_pct
            base["duration_minutes"] = base.target_4_stop_4_duration_minutes
            base["exit_type"] = base.target_4_stop_4_exit_type
            base["complete_24h"] = base.exit_window_complete_24h
            for key, setup in base.loc[base.eligible].groupby(
                ["asset", "timeframe", "average_type", "touch_zone"], observed=True, sort=True
            ):
                row = dict(zip(CONFIG_KEYS[:-1], key))
                selected_periods = []
                for period in ["earlier", "later"]:
                    metrics, selected = summarize_period(setup.loc[setup.period.eq(period)])
                    row.update({f"{name}_{period}": value for name, value in metrics.items()})
                    selected_periods.append(selected)
                combined = pd.concat(selected_periods).sort_values("entry_timestamp")
                qmeans = (combined.assign(net=combined.gross_return_pct - .2)
                          .groupby(quarter_labels(combined.origin_signal_timestamp)).net.mean())
                row["quarters"] = len(qmeans)
                row["positive_quarters_pct"] = qmeans.gt(0).mean() * 100 if len(qmeans) else np.nan
                row["entry_method"] = "current_bullish_candle_30m"
                rows.append(row)
    return pd.DataFrame(rows)


def comparison_table(summary, baseline):
    metrics = ["nonoverlap_trades_earlier", "nonoverlap_trades_later",
               "net_0_2_mean_pct_earlier", "net_0_2_mean_pct_later",
               "target_pct_earlier", "target_pct_later", "stop_pct_earlier", "stop_pct_later",
               "positive_quarters_pct"]
    keys = ["asset", "timeframe", "average_type", "touch_zone"]
    base = baseline[[*keys, "entry_method", *metrics]].copy()
    bounce = summary[[*keys, "policy", *metrics]].rename(columns={"policy": "entry_method"})
    return pd.concat([base, bounce], ignore_index=True).sort_values([*keys, "entry_method"]).reset_index(drop=True)


def selected_audit(candidates):
    main = candidates.loc[
        candidates.asset.eq("SOLUSDT") & candidates.timeframe.eq("5m")
        & candidates.average_type.eq("15d") & candidates.touch_zone.eq(.5)
        & candidates.eligible & candidates.entered & candidates.complete_24h
    ]
    rows = []
    for policy, setup in main.groupby("policy", sort=True):
        for period, current in setup.groupby("period", sort=True):
            chosen = select_nonoverlap(current, "duration_minutes").copy()
            chosen["net_0_2_return_pct"] = chosen.gross_return_pct - .2
            rows.append(chosen[["episode_id", "policy", "period", "origin_signal_timestamp",
                                "reclaim_candle_timestamp", "breakout_candle_timestamp",
                                "entry_timestamp", "entry_price", "exit_type", "duration_minutes",
                                "gross_return_pct", "net_0_2_return_pct"]])
    return pd.concat(rows, ignore_index=True)


def run():
    config = yaml.safe_load((ROOT / "config/experiments/v1_stage15_v2_step1_bounce_entries.yaml").read_text())
    require(config["entry"]["confirmation_windows"] == ["immediate", "15m", "30m"],
            "Unsupported confirmation grid")
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")
    print("Hashing all pre-existing research artifacts...", flush=True)
    before = protected_snapshot()
    DATA.mkdir(parents=True, exist_ok=False); RESULTS.mkdir(parents=True, exist_ok=False)
    (RESULTS / "source_manifest_before.json").write_text(json.dumps(before, indent=2) + "\n")
    (RESULTS / "experiment.json").write_text(json.dumps(config, indent=2) + "\n")

    source = yaml.safe_load((ROOT / "config/experiments/v1_stage1.yaml").read_text())
    all_candidates, validations, raw_ends = [], [], {}
    for asset in source["data"]["assets"]:
        print(f"{asset}: loading raw 1-minute execution data", flush=True)
        raw = pd.read_parquet(ROOT / f"data/raw/{asset}/{asset}_1m.parquet",
                              columns=["open_time", "open", "high", "low", "close"])
        engine = FixedExitEngine(raw)
        data_end = engine.times[-1] + pd.Timedelta("1min")
        raw_ends[asset] = data_end
        asset_candidates = []
        for timeframe in source["research"]["timeframes"]:
            tag = f"{asset}_{timeframe}"
            print(f"{tag}: generating ordered reclaim-and-breakout signals", flush=True)
            candles = pd.read_parquet(ROOT / f"data/processed/{asset}/{tag}_with_averages.parquet",
                                      columns=["open_time", "open", "high", "low", "close",
                                               "average_7d", "average_15d", "average_30d"])
            episodes = pd.read_parquet(STEP1 / asset / f"{tag}_episodes.parquet",
                                       columns=["episode_id", "asset", "timeframe", "average_type",
                                                "touch_zone", "start_timestamp", "left_censored"])
            candidates = generate_candidates(candles, episodes, timeframe)
            confirmed_checks = validate_candidates(candles, candidates, timeframe)
            asset_candidates.append(candidates)
            validations.append({"dataset": tag, "candidate_rows": len(candidates),
                                "from_below_episodes": candidates.episode_id.nunique(),
                                "confirmed_signal_checks": confirmed_checks, "pass": True})
        combined = pd.concat(asset_candidates, ignore_index=True)
        print(f"{asset}: simulating {combined.entry_timestamp.nunique():,} unique confirmed entries", flush=True)
        outcomes = engine.calculate(combined.entry_timestamp.dropna())
        replay_checks = engine.validate_samples(outcomes)
        combined = combined.merge(outcomes, on="entry_timestamp", how="left", validate="many_to_one")
        combined["entered"] = combined.status.eq("confirmed") & combined.complete_24h.eq(True)
        origin = combined.origin_signal_timestamp
        crossing = origin.lt(SPLIT) & (origin + COMMON_TAIL > SPLIT)
        combined["period"] = np.where(origin < SPLIT, "earlier", "later")
        combined["eligible"] = ~combined.left_censored & (origin + COMMON_TAIL <= data_end) & ~crossing
        combined["exclusion_reason"] = np.select(
            [combined.left_censored, origin + COMMON_TAIL > data_end, crossing],
            ["left_censored", "incomplete_common_tail", "split_crossing"], default="eligible"
        )
        require(combined.loc[combined.eligible & combined.status.eq("confirmed"), "complete_24h"].eq(True).all(),
                "Eligible confirmation lacks complete outcome")
        for timeframe, frame in combined.groupby("timeframe", sort=True):
            output = DATA / asset
            output.mkdir(parents=True, exist_ok=True)
            path = output / f"{asset}_{timeframe}_bounce_candidates.parquet"
            frame.to_parquet(path, index=False)
            pd.testing.assert_frame_equal(frame.reset_index(drop=True), pd.read_parquet(path), check_exact=True)
        validations[-1]["direct_exit_replays"] = replay_checks
        all_candidates.append(combined)

    candidates = pd.concat(all_candidates, ignore_index=True)
    print("Building dependence-aware earlier/later and quarterly comparisons...", flush=True)
    summary, quarterly = build_summary(candidates)
    summary = attach_screen(summary)
    baseline = baseline_summary(source, raw_ends)
    comparison = comparison_table(summary, baseline)
    audit = selected_audit(candidates)
    audit_path = DATA / "reference_nonoverlap_events.parquet"
    audit.to_parquet(audit_path, index=False)
    pd.testing.assert_frame_equal(audit, pd.read_parquet(audit_path), check_exact=True)

    save_csv("summary", summary)
    save_csv("quarterly", quarterly)
    save_csv("baseline_comparison", comparison)
    save_csv("validation", pd.DataFrame(validations))
    print("Verifying that all earlier research files remain byte-identical...", flush=True)
    after = protected_snapshot()
    require(before == after, "A protected pre-existing file changed")
    (RESULTS / "source_manifest_after.json").write_text(json.dumps(after, indent=2) + "\n")
    write_report(RESULTS, summary, comparison, len(before), len(candidates))
    (RESULTS / "SUCCESS.json").write_text(json.dumps({
        "step": "stage15_v2_step1", "scope": "confirmed_bounce_entries",
        "configurations": 81, "policies": len(POLICIES), "candidate_rows": len(candidates),
        "provisional_passes": int(summary.provisional_pass.sum()),
        "robust_passes": int(summary.robust_pass.sum()),
        "protected_files_unchanged": len(before), "validation": "PASS",
    }, indent=2) + "\n")
    print(f"Completed: {RESULTS / 'bounce_entry_report.md'}", flush=True)


if __name__ == "__main__":
    run()

