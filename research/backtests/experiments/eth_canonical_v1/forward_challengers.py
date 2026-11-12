"""Run the frozen ETH challengers on post-research data only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .confirmation_quality import dip_signals, quality
from .engine import CandidateTrade, MarketData, ReplayResult, replay_portfolio
from .equal_stop_risk import equal_risk_sizer
from .failure_exit import _dip_references, _mode_c_references, apply_failure_exit
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config
from .volatility_sizing import causal_volatility_states, volatility_sizer


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_forward_challengers_v1.json"
EQUAL_RISK_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_equal_stop_risk_v1.json"


def complete_utc_months(start: pd.Timestamp, end_exclusive: pd.Timestamp) -> int:
    """Count whole calendar months contained in [start, end_exclusive)."""
    boundary = pd.Timestamp(start).normalize()
    count = 0
    while True:
        following = boundary + pd.offsets.MonthBegin(1)
        if following > end_exclusive:
            return count
        count += 1
        boundary = following


def _load_market() -> tuple[pd.DataFrame, np.ndarray, MarketData]:
    raw = baseline_module.compare.replay.load_raw("ETHUSDT", include_holdout=True)
    raw = raw.sort_values("open_time").drop_duplicates("open_time").reset_index(drop=True)
    steps = raw.open_time.diff().iloc[1:]
    if not (steps == pd.Timedelta(minutes=1)).all():
        bad = raw.loc[steps.ne(pd.Timedelta(minutes=1)).to_numpy().nonzero()[0] + 1, "open_time"]
        raise ValueError(f"Forward ETH minute history is not continuous near {bad.iloc[0]}")
    grid = baseline_module.grid
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (
        raw[column].to_numpy(float) for column in ("open", "high", "low", "close")
    )
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    grid.SLIP = 2 / 10_000
    bullish = baseline_module.live.regime_flags(raw)
    market = MarketData(grid.TIMES, grid.OPEN.copy(), grid.CLOSE.copy())
    return raw, bullish, market


def _candidates(raw: pd.DataFrame, bullish: np.ndarray, confirmation: str) -> list[CandidateTrade]:
    rule = baseline_module.live.load_rule("eth")
    if confirmation == "current_green":
        dip_entries = baseline_module.live.live_entries(raw, rule)
    else:
        signals, _ = dip_signals(raw, rule, confirmation)
        dip_entries = np.asarray([signal.entry for signal in signals], dtype=np.int64)
    breakout_entries = [trade["entry"] for trade in baseline_module.compare.mode_c(
        raw, rule, 120, 12, 2.5, 30, 1.283, 22.0, 3.5
    )]
    pullback_entries = baseline_module.pullback.pullback_entries(
        baseline_module.grid.CLOSE, bullish, 24, 180, baseline_module.grid.TIMES,
        blocked=rule["blocked"],
    )
    trend_line = pd.Series(baseline_module.grid.CLOSE).ewm(span=16 * 60, adjust=False).mean().to_numpy()
    baseline_module.floor_arm.LINE_FLOOR = trend_line * (1 + baseline_module.floor_arm.COSTS / 100)
    sources = (
        (dip_entries, "dip", baseline_module.modes.DIP_STOP,
         rule["activation_pct"], rule["giveback_pct"]),
        (breakout_entries, "breakout", 3.5, 1.283, 22.0),
        (pullback_entries, "pullback", baseline_module.modes.DIP_STOP,
         rule["activation_pct"], rule["giveback_pct"]),
    )
    book = baseline_module.floor_arm.book(
        sources, bullish, trend_line, baseline_module.floor_arm.DEPLOYED_ARM,
        "buy price", "on arming",
    )
    counters: dict[tuple[str, int], int] = {}
    candidates = []
    for trade in book:
        entry, source = int(trade["entry"]), str(trade["source"])
        key = source, entry
        ordinal = counters.get(key, 0)
        counters[key] = ordinal + 1
        candidates.append(CandidateTrade(
            entry=entry, exit=int(trade["exit"]), exit_price=float(trade["price"]),
            source=source, exit_code=int(trade["why"]),
            candidate_id=f"{source}:{baseline_module.grid.TIMES[entry].isoformat()}:{ordinal}",
            exit_kind=baseline_module._exit_kind(trade),
            arm_index=baseline_module._arm_index(trade), bullish_entry=bool(bullish[entry]),
        ))
    return candidates


def _summary(result: ReplayResult, threshold: float) -> dict:
    return {**result.summary, **quality(result, threshold)}


def _factor(value) -> float:
    return float(value) if value is not None and np.isfinite(value) else float("inf")


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    raw, bullish, market = _load_market()
    start = pd.Timestamp(experiment["evaluation_start"])
    end = market.times[-1] + pd.Timedelta(minutes=1)
    if end <= start:
        output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
        output.mkdir(parents=True, exist_ok=True)
        status = {
            "freeze_timestamp": experiment["freeze_timestamp"],
            "evaluation_start": start.isoformat(), "data_end_exclusive": end.isoformat(),
            "complete_utc_months": 0,
            "required_complete_utc_months": experiment["minimum_complete_utc_months"],
            "baseline_trades": 0, "required_baseline_trades": experiment["minimum_baseline_trades"],
            "earliest_decision": experiment["earliest_decision"],
            "eligible_for_decision": False, "accepted_variants": [],
            "state": "waiting_for_forward_candles",
        }
        pd.DataFrame(columns=[
            "variant", "profit", "profit_change", "trades", "economic_win_rate_pct",
            "average_win", "average_loss", "profit_factor", "max_drawdown_pct",
            "endpoint_closed_trades", "metrics_pass", "eligible_for_decision", "accepted",
        ]).to_csv(output / "leaderboard.csv", index=False)
        (output / "status.json").write_text(json.dumps(status, indent=2) + "\n")
        (output / "REPORT.md").write_text(
            "# ETH forward challenger competition\n\n"
            "## Status\n\n"
            "**NO DECISION — waiting for the first completed ETH candle after "
            f"{start.isoformat()}.**\n\n"
            f"The official local archive currently ends at {market.times[-1].isoformat()}. "
            "Historical results are deliberately not reused as forward evidence.\n"
        )
        return output

    baseline_candidates = _candidates(raw, bullish, "current_green")
    confirmation_rule = next(item["rule"] for item in experiment["challengers"]
                             if item["name"] == "strong_confirmation")
    confirmation_candidates = _candidates(raw, bullish, confirmation_rule)

    rule = baseline_module.live.load_rule("eth")
    references = {
        "dip": _dip_references(raw, rule),
        "breakout": _mode_c_references(raw, rule),
    }
    ema_24h = pd.Series(baseline_module.grid.CLOSE).ewm(span=1440, adjust=False).mean().to_numpy()
    failure = next(item for item in experiment["challengers"] if item["name"] == "dip_failure_exit_12h")
    failure_candidates, _, _ = apply_failure_exit(
        baseline_candidates, market, str(failure["source"]), int(failure["checkpoint_hours"]),
        references, ema_24h, maximum_progress_pct=float(failure["maximum_favorable_excursion_pct"]),
    )

    equal = next(item for item in experiment["challengers"] if item["name"] == "equal_risk_4_50_cap_130")
    stops = json.loads(EQUAL_RISK_CONFIG.read_text())["stop_pct"]
    equal_sizer = equal_risk_sizer(stops, float(equal["risk_usd"]), float(equal["maximum_order_usd"]))

    volatility = next(item for item in experiment["challengers"]
                      if item["name"] == "volatility_high20_size70")
    states = causal_volatility_states(market.close, market.times).volatility_state.to_numpy()
    volatility_lot_sizer = volatility_sizer(states, volatility)

    definitions = {
        "baseline": (baseline_candidates, None),
        "strong_confirmation": (confirmation_candidates, None),
        "dip_failure_exit_12h": (failure_candidates, None),
        "equal_risk_4_50_cap_130": (baseline_candidates, equal_sizer),
        "volatility_high20_size70": (baseline_candidates, volatility_lot_sizer),
    }
    results = {
        name: replay_portfolio(candidates, market, start, end, portfolio, lot_sizer=sizer)
        for name, (candidates, sizer) in definitions.items()
    }
    threshold = 0.25
    summaries = {name: _summary(result, threshold) for name, result in results.items()}
    control = summaries["baseline"]
    months = complete_utc_months(start, end)
    ready = bool(
        months >= int(experiment["minimum_complete_utc_months"])
        and control["trades"] >= int(experiment["minimum_baseline_trades"])
        and end >= pd.Timestamp(experiment["earliest_decision"])
    )
    rows = []
    for name, summary in summaries.items():
        passed_metrics = bool(
            name != "baseline"
            and summary["net_profit"] > control["net_profit"]
            and _factor(summary["profit_factor"]) > _factor(control["profit_factor"])
            and summary["average_loss"] >= control["average_loss"]
            and summary["maximum_drawdown_pct"] >= control["maximum_drawdown_pct"]
        )
        rows.append({
            "variant": name, "profit": summary["net_profit"],
            "profit_change": summary["net_profit"] - control["net_profit"],
            "trades": summary["trades"], "economic_win_rate_pct": summary["economic_win_rate_pct"],
            "average_win": summary["average_win"], "average_loss": summary["average_loss"],
            "profit_factor": summary["profit_factor"],
            "max_drawdown_pct": summary["maximum_drawdown_pct"],
            "endpoint_closed_trades": summary["endpoint_closed_trades"],
            "metrics_pass": passed_metrics, "eligible_for_decision": ready,
            "accepted": ready and passed_metrics,
        })
    frame = pd.DataFrame(rows)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "leaderboard.csv", index=False)
    for name, result in results.items():
        result.trades.to_csv(output / f"{name}_trades.csv", index=False)
    status = {
        "freeze_timestamp": experiment["freeze_timestamp"], "evaluation_start": start.isoformat(),
        "data_end_exclusive": end.isoformat(), "complete_utc_months": months,
        "required_complete_utc_months": experiment["minimum_complete_utc_months"],
        "baseline_trades": control["trades"], "required_baseline_trades": experiment["minimum_baseline_trades"],
        "earliest_decision": experiment["earliest_decision"], "eligible_for_decision": ready,
        "accepted_variants": frame.loc[frame.accepted, "variant"].tolist(),
    }
    (output / "status.json").write_text(json.dumps(status, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(frame, status))
    return output


def _report(frame: pd.DataFrame, status: dict) -> str:
    rows = []
    for row in frame.itertuples():
        rows.append(
            f"| {row.variant} | ${row.profit:.2f} | ${row.profit_change:+.2f} | {row.trades} | "
            f"{row.economic_win_rate_pct:.1f}% | ${row.average_win:.2f} | ${row.average_loss:.2f} | "
            f"{row.max_drawdown_pct:.2f}% | {row.endpoint_closed_trades} |"
        )
    decision = "Eligible for final decision." if status["eligible_for_decision"] else (
        f"NO DECISION — {status['complete_utc_months']}/{status['required_complete_utc_months']} complete "
        f"UTC months and {status['baseline_trades']}/{status['required_baseline_trades']} baseline trades."
    )
    return f"""# ETH forward challenger competition

## Status

**{decision}**

Data: {status['evaluation_start']} through {status['data_end_exclusive']}.

| Variant | Profit | vs baseline | Trades | Economic win | Avg win | Avg loss | Drawdown | Open at cutoff |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

Partial-month scores are monitoring only. The candidates remain frozen, no historical parameters are retuned, and no live orders are sent.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXPERIMENT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output)
    print((output / "REPORT.md").read_text())
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
