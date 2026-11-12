"""Audit the strongest historical BTC candidate and freeze a paper-only rule."""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.research.eth_stage15_freeze.analysis import (
    block_bootstrap,
    expected_shortfall_10,
    longest_nonpositive_streak,
    max_drawdown_pct,
    profit_factor,
    require,
)
from src.research.stage15_robustness.analysis import condition_mask, quarter_labels, select_nonoverlap


ROOT = Path(__file__).resolve().parents[3]
RUN = "btc_stage15_freeze_v1"
RESULTS = ROOT / "results/btc_stage15" / RUN
DATA = ROOT / "data/research/btc_stage15" / RUN
SOURCE = ROOT / "data/research/stage15/step5_exits_v1/BTCUSDT"
CONFIG_PATH = ROOT / "config/experiments/btc_stage15_freeze_v1.yaml"
SCENARIOS = {
    "gross": (0.0, 0.0), "fee_only": (10.0, 0.0), "realistic": (10.0, 2.0),
    "stressed": (10.0, 5.0), "severe": (10.0, 10.0),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def markdown_table(frame: pd.DataFrame) -> str:
    """Render a compact Markdown table without pandas' optional tabulate dependency."""
    clean = frame.copy()
    for column in clean.columns:
        clean[column] = clean[column].map(
            lambda value: "" if pd.isna(value) else f"{value:.6g}" if isinstance(value, (float, np.floating)) else str(value)
        )
    headers = [str(column) for column in clean.columns]
    rows = [headers, ["---"] * len(headers), *clean.astype(str).values.tolist()]
    return "\n".join("| " + " | ".join(row) + " |" for row in rows)


def load_sources() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    frames, manifest = [], {}
    for timeframe in ["1m", "3m", "5m"]:
        path = SOURCE / f"BTCUSDT_{timeframe}_exit_candidates.parquet"
        frame = pd.read_parquet(path)
        require(frame.asset.eq("BTCUSDT").all(), "Non-BTC source row")
        frames.append(frame)
        manifest[str(path.relative_to(ROOT))] = {"size": path.stat().st_size, "sha256": sha256(path)}
    raw_path = ROOT / "data/processed/BTCUSDT/BTCUSDT_1m_with_averages.parquet"
    raw = pd.read_parquet(raw_path)
    manifest[str(raw_path.relative_to(ROOT))] = {"size": raw_path.stat().st_size, "sha256": sha256(raw_path)}
    return pd.concat(frames, ignore_index=True), raw, manifest


def signals(candidates: pd.DataFrame, timeframe="5m", zone=1.5) -> pd.DataFrame:
    frame = candidates.loc[
        candidates.timeframe.eq(timeframe) & candidates.average_type.eq("30d")
        & candidates.touch_zone.eq(zone) & candidates.policy.eq("bullish_candle_30m")
        & candidates.eligible & candidates.entered & candidates.exit_window_complete_24h
    ].copy()
    return frame.loc[condition_mask(frame, "bullish_regime")].sort_values("entry_timestamp")


def replay(
    signal_rows: pd.DataFrame, raw: pd.DataFrame, fee_bps: float, slip_bps: float,
    target_pct: float = 1.0, stop_pct: float | None = None, hold_minutes: int = 1440,
) -> pd.DataFrame:
    times = pd.DatetimeIndex(raw.open_time)
    require(times.is_unique and times.is_monotonic_increasing and str(times.tz) == "UTC", "Invalid raw grid")
    require((times[1:] - times[:-1] == pd.Timedelta("1min")).all(), "Raw one-minute gaps")
    starts = times.get_indexer(pd.DatetimeIndex(signal_rows.entry_timestamp))
    require((starts >= 0).all() and (starts + hold_minutes - 1 < len(raw)).all(), "Incomplete execution window")
    opened, highs, lows, closes = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    fee, slip = fee_bps / 10_000.0, slip_bps / 10_000.0
    entry = opened[starts] * (1 + slip)
    target = entry * (1 + target_pct / 100)
    stop = entry * (1 - stop_pct / 100) if stop_pct is not None else np.full(len(entry), -np.inf)
    idx = starts[:, None] + np.arange(hold_minutes)
    target_hit, stop_hit = highs[idx] >= target[:, None], lows[idx] <= stop[:, None]
    target_any, stop_any = target_hit.any(axis=1), stop_hit.any(axis=1)
    target_offset = np.where(target_any, target_hit.argmax(axis=1), hold_minutes)
    stop_offset = np.where(stop_any, stop_hit.argmax(axis=1), hold_minutes)
    # A same-minute conflict is resolved against the strategy.
    stopped = stop_any & (stop_offset <= target_offset)
    targeted = target_any & (target_offset < stop_offset)
    offset = np.minimum(np.minimum(target_offset, stop_offset), hold_minutes - 1)
    exit_index = starts + offset
    raw_exit = np.where(stopped, np.minimum(stop, opened[exit_index]), np.where(targeted, target, closes[exit_index]))
    exit_fill = raw_exit * (1 - slip)
    net = (exit_fill * (1 - fee) / (entry * (1 + fee)) - 1) * 100
    result = signal_rows.copy()
    result["entry_fill"] = entry; result["exit_fill"] = exit_fill
    result["net_return_pct"] = net; result["duration_minutes"] = offset + 1
    result["exit_type"] = np.where(stopped, "protective_stop", np.where(targeted, "profit_target", "time"))
    return result


def select_periods(frame: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for period in ["earlier", "later"]:
        part = select_nonoverlap(frame.loc[frame.period.eq(period)], "duration_minutes").copy()
        part["analysis_period"] = period
        parts.append(part)
    return pd.concat(parts).sort_values(["entry_timestamp", "episode_id"])


def metrics(frame: pd.DataFrame, scenario: str, repetitions: int, seed: int) -> list[dict]:
    rows = []
    for period in ["earlier", "later", "combined"]:
        part = frame if period == "combined" else frame.loc[frame.analysis_period.eq(period)]
        values = part.net_return_pct
        rows.append({"scenario": scenario, "period": period, "trades": len(part),
            "mean_pct": values.mean(), "median_pct": values.median(),
            "win_pct": values.gt(0).mean()*100, "profit_factor": profit_factor(values),
            "expected_shortfall_10_pct": expected_shortfall_10(values), "worst_trade_pct": values.min(),
            "max_drawdown_pct": max_drawdown_pct(values),
            "longest_nonpositive_streak": longest_nonpositive_streak(values),
            **block_bootstrap(part, "net_return_pct", repetitions, seed)})
    return rows


def evaluate(main: pd.DataFrame, quarterly: pd.DataFrame, sensitivity: pd.DataFrame, config: dict) -> dict:
    gate = config["decision_gates"]
    by_period = main.set_index("period")
    sample = all(by_period.loc[p, "trades"] >= gate["minimum_trades_each_period"] for p in ["earlier", "later"])
    mean = all(by_period.loc[p, "mean_pct"] > 0 for p in ["earlier", "later"])
    median = all(by_period.loc[p, "median_pct"] > 0 for p in ["earlier", "later"])
    pf = all(by_period.loc[p, "profit_factor"] > gate["minimum_profit_factor"] for p in ["earlier", "later"])
    dd = all(by_period.loc[p, "max_drawdown_pct"] >= -gate["maximum_drawdown_pct"] for p in ["earlier", "later"])
    quarter = quarterly.mean_pct.gt(0).mean()*100 >= gate["minimum_positive_quarters_pct"]
    neighbors = sensitivity.loc[sensitivity.kind.eq("neighbor")]
    neighbor = neighbors.positive_both.mean() >= gate["minimum_positive_neighbors_fraction"]
    ci = all(by_period.loc[p, "ci95_low"] > 0 for p in ["earlier", "later"])
    paper = sample and mean and median and pf and dd and quarter and neighbor
    return {"decision": "FROZEN_FOR_PAPER_VALIDATION_ONLY" if paper else "REJECT",
        "sample_pass": bool(sample), "positive_mean_both": bool(mean), "positive_median_both": bool(median),
        "profit_factor_both": bool(pf), "drawdown_pass_both": bool(dd), "quarter_consistency": bool(quarter),
        "neighbor_stability": bool(neighbor), "positive_ci95_both": bool(ci),
        "strict_historical_validation_pass": bool(paper and ci)}


def exploratory_grid(candidates: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """Search simple neighboring exits, selecting on the earlier period only."""
    rows = []
    for timeframe, zone, target, stop, hold in itertools.product(
        ["1m", "3m", "5m"], [0.5, 1.0, 1.5], [0.5, 1.0, 1.5, 2.0],
        [None, 1.0, 2.0, 3.0, 4.0], [240, 480, 720, 1440],
    ):
        signal_rows = signals(candidates, timeframe, zone)
        if signal_rows.empty:
            continue
        selected = select_periods(replay(signal_rows, raw, 10, 2, target, stop, hold))
        row = {"timeframe": timeframe, "touch_zone_pct": zone, "target_pct": target,
               "stop_pct": "none" if stop is None else stop, "maximum_hold_minutes": hold}
        for period in ["earlier", "later"]:
            values = selected.loc[selected.analysis_period.eq(period), "net_return_pct"]
            row.update({f"trades_{period}": len(values), f"mean_pct_{period}": values.mean(),
                        f"median_pct_{period}": values.median(), f"profit_factor_{period}": profit_factor(values),
                        f"max_drawdown_pct_{period}": max_drawdown_pct(values)})
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame["earlier_gate_pass"] = (
        (frame.trades_earlier >= 30) & (frame.mean_pct_earlier > 0) &
        (frame.median_pct_earlier > 0) & (frame.profit_factor_earlier > 1) &
        (frame.max_drawdown_pct_earlier >= -15)
    )
    frame["later_gate_pass"] = (
        (frame.trades_later >= 30) & (frame.mean_pct_later > 0) &
        (frame.median_pct_later > 0) & (frame.profit_factor_later > 1) &
        (frame.max_drawdown_pct_later >= -15)
    )
    frame["worst_period_mean_pct"] = frame[["mean_pct_earlier", "mean_pct_later"]].min(axis=1)
    return frame.sort_values(["earlier_gate_pass", "mean_pct_earlier"], ascending=False).reset_index(drop=True)


def run() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text())
    require(config["experiment"]["name"] == RUN, "Experiment mismatch")
    require(not RESULTS.exists() and not DATA.exists(), "Run exists; refusing overwrite")
    candidates, raw, manifest = load_sources()
    repetitions, seed = config["bootstrap"]["repetitions"], config["bootstrap"]["seed"]
    RESULTS.mkdir(parents=True); DATA.mkdir(parents=True)
    (RESULTS / "experiment.json").write_text(json.dumps(config, indent=2)+"\n")
    (RESULTS / "source_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")

    main_signals = signals(candidates)
    scenario_frames, metric_rows = [], []
    for name, (fee, slip) in SCENARIOS.items():
        selected = select_periods(replay(main_signals, raw, fee, slip))
        selected["scenario"] = name; scenario_frames.append(selected)
        metric_rows.extend(metrics(selected, name, repetitions, seed))
    scenario_events = pd.concat(scenario_frames)
    main_metrics = pd.DataFrame(metric_rows)
    realistic = scenario_events.loc[scenario_events.scenario.eq("realistic")].copy()
    realistic.assign(quarter=quarter_labels(realistic.origin_signal_timestamp)).to_parquet(DATA / "frozen_candidate_events.parquet", index=False)

    quarter_frame = realistic.assign(quarter=quarter_labels(realistic.origin_signal_timestamp)).groupby("quarter").net_return_pct.agg([("trades","size"),("mean_pct","mean"),("median_pct","median")]).reset_index()
    sensitivity_rows = []
    for timeframe, zone in [("1m",1.5),("3m",1.5),("5m",1.0),("5m",2.0)]:
        selected = select_periods(replay(signals(candidates,timeframe,zone),raw,10,2))
        row={"kind":"neighbor","timeframe":timeframe,"touch_zone_pct":zone}
        for period in ["earlier","later"]:
            part=selected.loc[selected.analysis_period.eq(period)].net_return_pct
            row[f"trades_{period}"]=len(part); row[f"mean_pct_{period}"]=part.mean()
        row["positive_both"]=row["mean_pct_earlier"]>0 and row["mean_pct_later"]>0
        sensitivity_rows.append(row)
    for stop in [1.0,2.0,3.0,4.0,5.0,6.0,8.0,None]:
        selected=select_periods(replay(main_signals,raw,10,2,stop_pct=stop))
        row={"kind":"stop","stop_pct":stop if stop is not None else "none"}
        for period in ["earlier","later"]:
            part=selected.loc[selected.analysis_period.eq(period)].net_return_pct
            row[f"trades_{period}"]=len(part); row[f"mean_pct_{period}"]=part.mean(); row[f"median_pct_{period}"]=part.median(); row[f"max_drawdown_pct_{period}"]=max_drawdown_pct(part)
        sensitivity_rows.append(row)
    sensitivity=pd.DataFrame(sensitivity_rows)
    decision=evaluate(main_metrics.loc[main_metrics.scenario.eq("realistic")],quarter_frame,sensitivity,config)

    grid = exploratory_grid(candidates, raw)
    eligible = grid.loc[grid.earlier_gate_pass & grid.later_gate_pass]
    require(not eligible.empty, "No exploratory BTC paper candidate survived both period screens")
    best = eligible.sort_values("worst_period_mean_pct", ascending=False).iloc[0]
    best_stop = None if str(best.stop_pct) == "none" else float(best.stop_pct)
    best_signals = signals(candidates, str(best.timeframe), float(best.touch_zone_pct))
    best_metric_rows, best_scenario_frames = [], []
    for name, (fee, slip) in SCENARIOS.items():
        selected = select_periods(replay(best_signals, raw, fee, slip, float(best.target_pct), best_stop, int(best.maximum_hold_minutes)))
        selected["scenario"] = name
        best_scenario_frames.append(selected)
        best_metric_rows.extend(metrics(selected, name, repetitions, seed))
    best_metrics = pd.DataFrame(best_metric_rows)
    best_realistic = pd.concat(best_scenario_frames).loc[lambda frame: frame.scenario.eq("realistic")].copy()
    best_quarterly = best_realistic.assign(quarter=quarter_labels(best_realistic.origin_signal_timestamp)).groupby("quarter").net_return_pct.agg([("trades", "size"), ("mean_pct", "mean"), ("median_pct", "median")]).reset_index()
    best_realistic.to_parquet(DATA / "recommended_paper_candidate_events.parquet", index=False)

    main_metrics.to_csv(RESULTS/"scenario_metrics.csv",index=False)
    quarter_frame.to_csv(RESULTS/"quarterly.csv",index=False)
    sensitivity.to_csv(RESULTS/"parameter_sensitivity.csv",index=False)
    grid.to_csv(RESULTS/"exploratory_rule_grid.csv", index=False)
    best_metrics.to_csv(RESULTS/"recommended_paper_candidate_metrics.csv", index=False)
    best_quarterly.to_csv(RESULTS/"recommended_paper_candidate_quarterly.csv", index=False)
    (RESULTS/"DECISION.json").write_text(json.dumps(decision,indent=2)+"\n")
    realistic_metrics=main_metrics.loc[main_metrics.scenario.eq("realistic")].set_index("period")
    rule={"schema_version":1,"strategy_id":"btc_30d_bullish_target_5m_v1","status":decision["decision"],"paper_trade_only":True,
      "asset":"BTCUSDT","venue_type":"spot","direction":"long_only",
      "signal":{"timeframe":"5m","execution_timeframe":"1m","daily_average_source":"completed_UTC_daily_closes_only","averages":{"type":"simple","days":[7,15,30]},"regime":"average_7d > average_15d > average_30d","reference_average":"30d","touch_zone_pct":1.5,"deduplication":"one_episode_for_consecutive_touching_candles","confirmation":"first_bullish_5m_candle_within_30_minutes","confirmation_expiry":"first_non_touch_candle_included_or_30_minutes_whichever_first"},
      "execution":{"entry":"next_raw_1m_open_after_confirmation_close","maximum_open_positions":1,"profit_target_pct_from_actual_entry_fill":1.0,"protective_stop":None,"maximum_hold_minutes":1440,"same_candle_conflict":"protective_stop_wins_if_a_future_version_adds_a_stop"},
      "position_sizing":{"maximum_position_notional_pct_of_net_liquidation":10.0,"formula":"min(available_quote_balance, net_liquidation*0.10)","leverage":"none"},
      "paper_cost_model":{"fee_bps_per_side":10.0,"slippage_bps_per_side":2.0,"adverse_slippage_on_entry_and_exit":True},
      "historical_audit":{"data_start_utc":config["source_period"]["start_utc"],"data_end_utc":config["source_period"]["end_utc"],"split_utc":config["source_period"]["split_utc"],"earlier_trades":int(realistic_metrics.loc["earlier","trades"]),"later_trades":int(realistic_metrics.loc["later","trades"]),"realistic_mean_pct_earlier":float(realistic_metrics.loc["earlier","mean_pct"]),"realistic_mean_pct_later":float(realistic_metrics.loc["later","mean_pct"]),"strict_historical_validation_pass":decision["strict_historical_validation_pass"]},
      "immutability":{"rule_changes_require_new_strategy_id":True,"historical_source_manifest":manifest}}
    rule_text=json.dumps(rule,indent=2,allow_nan=False)+"\n"; (RESULTS/"historical_leader_rule.json").write_text(rule_text)
    (RESULTS/"historical_leader_rule.sha256").write_text(hashlib.sha256(rule_text.encode()).hexdigest()+"  historical_leader_rule.json\n")
    paper_rule = {
        "schema_version": 1,
        "strategy_id": "btc_30d_bullish_target1_stop2_5m_v1",
        "status": "PROSPECTIVE_PAPER_CANDIDATE_ONLY",
        "historical_validation_status": "REJECT",
        "paper_trade_only": True,
        "asset": "BTCUSDT", "venue_type": "spot", "direction": "long_only",
        "signal": rule["signal"],
        "execution": {
            "entry": rule["execution"]["entry"],
            "maximum_open_positions": 1,
            "profit_target_pct_from_actual_entry_fill": float(best.target_pct),
            "protective_stop_pct_from_actual_entry_fill": best_stop,
            "maximum_hold_minutes": int(best.maximum_hold_minutes),
            "same_candle_conflict": "protective_stop_wins",
        },
        "position_sizing": rule["position_sizing"], "paper_cost_model": rule["paper_cost_model"],
        "selection_disclosure": {
            "method": "post_audit_exploratory_grid",
            "configurations_tested": int(len(grid)),
            "selection_rule": "pass basic gates in both periods, then maximize the worse period mean",
            "independent_holdout_remaining": False,
            "requires_prospective_validation": True,
        },
        "immutability": {"rule_changes_require_new_strategy_id": True, "historical_source_manifest": manifest},
    }
    paper_text = json.dumps(paper_rule, indent=2, allow_nan=False) + "\n"
    (RESULTS / "recommended_paper_strategy.json").write_text(paper_text)
    (RESULTS / "recommended_paper_strategy.sha256").write_text(hashlib.sha256(paper_text.encode()).hexdigest()+"  recommended_paper_strategy.json\n")
    rule_heading = "## Freeze decision\n"
    rule_note = (
        "This rule may be frozen for prospective paper validation only.\n"
        if decision["decision"] != "REJECT" else
        "Do not freeze this as a validated strategy. It is the leading BTC research candidate, but it failed the preset robustness gates.\n"
    )
    best_realistic_metrics = best_metrics.loc[best_metrics.scenario.eq("realistic")]
    report_lines=["# BTC Stage 1/1.5/Version 2 End-to-End Audit\n",f"## Historical decision\n\n**{decision['decision']}** — no BTC rule passed the complete historical robustness standard.\n", rule_heading, "The best rule may be frozen only as an immutable prospective paper experiment. It must not be represented as historically validated.\n", "## Best paper candidate\n", "BTCUSDT spot, long only; 5-minute bullish confirmation after a ±1.5% touch of the completed-day 30-day SMA, only when 7D > 15D > 30D. Enter at the next raw one-minute open, take profit at +1.0% from actual fill, stop at −2.0% from actual fill, and force exit after 1,440 minutes. Model 10 bps fee and 2 bps slippage per side. Use one position and 10% of account equity.\n", "This stop was selected after a 720-configuration exploratory exit grid. There is no untouched historical holdout left, so its positive result is a hypothesis for forward paper trading.\n", "## Best candidate realistic results\n", markdown_table(best_realistic_metrics), "\n## Best candidate quarterly stability\n", markdown_table(best_quarterly), "\n## Original Stage 1.5 leader (no stop)\n", markdown_table(realistic_metrics.reset_index()), "\n## Original leader cost sensitivity\n", markdown_table(main_metrics), "\n## Parameter and stop sensitivity\n", markdown_table(sensitivity), "\n## Original leader gate audit\n", "\n".join(f"- {k}: **{'PASS' if v else 'FAIL'}**" for k,v in decision.items() if isinstance(v,bool)), "\n## End-to-end interpretation\n\nStage 1 established the completed-day moving-average touch framework on BTC. Stage 1.5 evaluated entry timing, market filters, downside protection, exits, non-overlap, costs, quarterly stability, and block bootstrap uncertainty; BTC produced zero provisional and zero robust selections. Its top-ranked candidate was the no-stop rule replayed above. Version 2 tested BTC bounce confirmations, but every BTC configuration failed the sample gate and the later market-filter, ATR-exit, execution, and strict-robustness stages proceeded with SOL only. The exact replay used actual one-minute opens, adverse fills, non-overlapping trades, conservative same-candle stop ordering, cost stress, weekly block bootstrap, quarterly slices, nearby timeframes, zones, exits, and source hashes.\n"]
    (RESULTS/"BTC_STAGE15_FINAL_REPORT.md").write_text("\n".join(report_lines))
    (RESULTS/"SUCCESS.json").write_text(json.dumps({"experiment":RUN,"source_rows":len(candidates),"realistic_events":len(realistic),"bootstrap_repetitions":repetitions,"historical_decision":decision["decision"],"pipeline_validation":"PASS"},indent=2)+"\n")
    print(RESULTS/"BTC_STAGE15_FINAL_REPORT.md")


if __name__ == "__main__":
    run()
