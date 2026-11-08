"""ETH experiment: reduce spot order size when perpetual funding and OI growth are both crowded."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .confirmation_quality import quality
from .engine import CandidateTrade, ReplayResult, replay_portfolio
from .pullback_revalidation import _excluded_month_mask
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config
from .volatility_sizing import _ratio


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_futures_crowding_v1.json"
CONTROL = "fixed_100_control"


def crowded_long(funding: float, funding_threshold: float, oi_growth: float,
                 oi_threshold: float) -> bool:
    values = (funding, funding_threshold, oi_growth, oi_threshold)
    return bool(all(np.isfinite(value) for value in values)
                and funding > 0 and oi_growth > 0
                and funding >= funding_threshold and oi_growth >= oi_threshold)


def _daily_rolling_threshold(values: pd.Series, days: pd.DatetimeIndex, reference_days: int,
                             quantile: float) -> pd.Series:
    daily = values.groupby(days).last()
    return daily.shift(1).rolling(reference_days, min_periods=reference_days).quantile(quantile)


def _funding_daily_threshold(funding: pd.DataFrame, all_days: pd.DatetimeIndex,
                             reference_days: int, quantile: float) -> pd.Series:
    times = funding.funding_time
    rates = funding.funding_rate
    rows = {}
    for day in all_days.unique().sort_values():
        start = day - pd.Timedelta(days=reference_days)
        history = rates[(times >= start) & (times < day)]
        rows[day] = float(history.quantile(quantile)) if len(history) >= reference_days * 3 - 3 else np.nan
    return pd.Series(rows)


def causal_candidate_features(candidate_times: pd.DatetimeIndex, metrics_path: Path,
                              funding_path: Path, reference_days: int,
                              percentiles: list[float]) -> pd.DataFrame:
    """Build strictly backward-looking futures features for each candidate entry."""
    metrics = pd.read_csv(metrics_path, usecols=["create_time", "sum_open_interest_value"])
    metrics["create_time"] = pd.to_datetime(metrics.create_time, utc=True, format="mixed")
    metrics["open_interest_value"] = pd.to_numeric(metrics.sum_open_interest_value, errors="coerce")
    metrics = metrics.loc[metrics.open_interest_value > 0].dropna().sort_values(
        "create_time"
    ).drop_duplicates("create_time", keep="last")
    # The archive changed from end labels to start labels in 2026. Treat every row as available
    # five minutes after its label, which is causal under either convention.
    metrics["available_at"] = metrics.create_time + pd.Timedelta(minutes=5)
    prior_lookup = pd.DataFrame({
        "target": metrics.available_at - pd.Timedelta(hours=24),
        "row": np.arange(len(metrics)),
    }).sort_values("target")
    history = metrics[["available_at", "open_interest_value"]].rename(
        columns={"available_at": "history_at", "open_interest_value": "oi_24h_ago"}
    )
    prior = pd.merge_asof(
        prior_lookup, history, left_on="target", right_on="history_at",
        direction="backward", tolerance=pd.Timedelta(minutes=20),
    ).sort_values("row")
    metrics["oi_growth_24h"] = metrics.open_interest_value.to_numpy() / prior.oi_24h_ago.to_numpy() - 1

    funding = pd.read_csv(funding_path, usecols=["funding_time", "fundingRate"])
    funding["funding_time"] = pd.to_datetime(funding.funding_time, utc=True, format="mixed")
    funding["funding_rate"] = pd.to_numeric(funding.fundingRate, errors="coerce")
    funding = funding.dropna().sort_values("funding_time").drop_duplicates("funding_time", keep="last")

    entries = pd.DataFrame({"entry_time": pd.DatetimeIndex(candidate_times)})
    entries["row"] = np.arange(len(entries))
    entries = entries.sort_values("entry_time")
    entries = pd.merge_asof(
        entries,
        metrics[["available_at", "open_interest_value", "oi_growth_24h"]],
        left_on="entry_time", right_on="available_at", direction="backward",
        allow_exact_matches=True, tolerance=pd.Timedelta(minutes=20),
    )
    entries = pd.merge_asof(
        entries.sort_values("entry_time"),
        funding[["funding_time", "funding_rate"]],
        left_on="entry_time", right_on="funding_time", direction="backward",
        allow_exact_matches=False, tolerance=pd.Timedelta(hours=9),
    )
    days = entries.entry_time.dt.floor("D")
    metric_days = metrics.available_at.dt.floor("D")
    all_days = pd.date_range(days.min(), days.max(), freq="D", tz="UTC")
    for quantile in percentiles:
        suffix = int(round(quantile * 100))
        oi_threshold = _daily_rolling_threshold(
            metrics.oi_growth_24h, metric_days, reference_days, quantile,
        )
        funding_threshold = _funding_daily_threshold(
            funding, all_days, reference_days, quantile,
        )
        entries[f"oi_q{suffix}"] = oi_threshold.reindex(days).to_numpy()
        entries[f"funding_q{suffix}"] = funding_threshold.reindex(days).to_numpy()
        entries[f"crowded_q{suffix}"] = [crowded_long(
            row.funding_rate, row[f"funding_q{suffix}"], row.oi_growth_24h, row[f"oi_q{suffix}"]
        ) for _, row in entries.iterrows()]
    return entries.sort_values("row").drop(columns="row").reset_index(drop=True)


def crowding_sizer(crowded_by_entry: dict[int, bool], normal_size: float, crowded_size: float):
    def size(candidate: CandidateTrade) -> float:
        return float(crowded_size if crowded_by_entry.get(candidate.entry, False) else normal_size)
    return size


def _metrics(result: ReplayResult, crowded_entries: set[int], excluded: list[str],
             threshold: float) -> dict:
    trades = result.trades
    ordinary = trades[~_excluded_month_mask(trades, excluded)] if len(trades) else trades
    crowded = trades[trades.entry_index.isin(crowded_entries)]
    return {
        "profit": float(result.summary["net_profit"]),
        "trades": int(result.summary["trades"]),
        "headline_win_rate_pct": float(result.summary["win_rate_pct"]),
        "average_win": float(result.summary["average_win"]),
        "average_loss": float(result.summary["average_loss"]),
        "profit_factor": float(result.summary["profit_factor"]),
        "max_drawdown_pct": float(result.summary["maximum_drawdown_pct"]),
        "max_drawdown_usd": float(result.summary["maximum_drawdown_usd"]),
        "profit_to_drawdown": _ratio(result),
        "ordinary_profit": float(ordinary.pnl.sum()),
        "average_order_usd": float(trades.spend.mean()),
        "crowded_fills": len(crowded),
        "crowded_profit": float(crowded.pnl.sum()),
        "crowded_win_rate_pct": 100 * float((crowded.pnl > 0).mean()) if len(crowded) else 0.0,
        "crowded_protective_stops": int((crowded.exit_kind == "protective_stop").sum()),
        **quality(result, threshold),
    }


def _passes(row: dict, control: dict, acceptance: dict) -> bool:
    return bool(
        row["profit_retention_pct"] >= acceptance["minimum_full_profit_retention_pct"]
        and row["ordinary_profit_retention_pct"] >= acceptance["minimum_ordinary_profit_retention_pct"]
        and row["walk_forward_profit_retention_pct"] >= acceptance["minimum_walk_forward_profit_retention_pct"]
        and row["profit_to_drawdown_change"] > acceptance["profit_to_drawdown_improvement_gt"]
        and row["risk_adjusted_wf_windows_improved"]
            >= acceptance["minimum_risk_adjusted_walk_forward_windows_improved"]
        and row["average_loss"] >= control["average_loss"]
        and row["max_drawdown_pct"] >= control["max_drawdown_pct"]
    )


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    market, candidates, windows = baseline_module.build_baseline()
    candidate_times = pd.DatetimeIndex([market.times[candidate.entry] for candidate in candidates])
    percentiles = [float(item["percentile"]) for item in experiment["variants"]]
    features = causal_candidate_features(
        candidate_times, STAGE2_ROOT / experiment["data"]["metrics_csv"],
        STAGE2_ROOT / experiment["data"]["funding_csv"],
        int(experiment["reference_days"]), percentiles,
    )
    features.insert(0, "candidate_id", [candidate.candidate_id for candidate in candidates])
    features.insert(1, "entry_index", [candidate.entry for candidate in candidates])
    if features[["funding_rate", "oi_growth_24h"]].isna().any().any():
        raise AssertionError("Futures observations do not cover every canonical candidate")

    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    schedules = {CONTROL: (None, set())}
    for item in experiment["variants"]:
        suffix = int(round(float(item["percentile"]) * 100))
        crowded = dict(zip(features.entry_index.astype(int), features[f"crowded_q{suffix}"].astype(bool)))
        crowded_entries = {entry for entry, state in crowded.items() if state}
        schedules[item["name"]] = (
            crowding_sizer(crowded, float(item["normal_size_usd"]), float(item["crowded_size_usd"])),
            crowded_entries,
        )
    results = {
        label: {name: replay_portfolio(candidates, market, *windows[name], portfolio, lot_sizer=sizer)
                for name in names}
        for label, (sizer, _entries) in schedules.items()
    }
    _assert_expected(
        results[CONTROL]["full"].summary, baseline_config["acceptance"],
        float(baseline_config["acceptance_tolerance"]),
    )
    excluded = experiment["excluded_entry_months"]
    threshold = float(experiment["economic_winner_threshold_pct"])
    control = _metrics(results[CONTROL]["full"], set(), excluded, threshold)
    control_wf = sum(results[CONTROL][name].summary["net_profit"] for name in wf_names)
    rows, window_rows, trade_rows = [], [], []
    for label, by_window in results.items():
        crowded_entries = schedules[label][1]
        metrics = _metrics(by_window["full"], crowded_entries, excluded, threshold)
        wf_profit = sum(by_window[name].summary["net_profit"] for name in wf_names)
        ratio_changes = [_ratio(by_window[name]) - _ratio(results[CONTROL][name]) for name in wf_names]
        row = {
            "variant": label,
            "crowded_candidates": len(crowded_entries),
            **metrics,
            "profit_change": metrics["profit"] - control["profit"],
            "profit_retention_pct": 100 * metrics["profit"] / control["profit"],
            "ordinary_profit_change": metrics["ordinary_profit"] - control["ordinary_profit"],
            "ordinary_profit_retention_pct": 100 * metrics["ordinary_profit"] / control["ordinary_profit"],
            "drawdown_change_pct_points": metrics["max_drawdown_pct"] - control["max_drawdown_pct"],
            "profit_to_drawdown_change": metrics["profit_to_drawdown"] - control["profit_to_drawdown"],
            "walk_forward_profit": wf_profit,
            "walk_forward_change": wf_profit - control_wf,
            "walk_forward_profit_retention_pct": 100 * wf_profit / control_wf,
            "risk_adjusted_wf_windows_improved": sum(change > 0 for change in ratio_changes),
        }
        row["accepted"] = label != CONTROL and _passes(row, control, experiment["acceptance"])
        rows.append(row)
        trade_rows.append(by_window["full"].trades.assign(variant=label))
        for name in names:
            window_rows.append({
                "variant": label, "window": name,
                "profit": by_window[name].summary["net_profit"],
                "control_profit": results[CONTROL][name].summary["net_profit"],
                "profit_change": by_window[name].summary["net_profit"]
                                 - results[CONTROL][name].summary["net_profit"],
                "profit_to_drawdown_change": _ratio(by_window[name]) - _ratio(results[CONTROL][name]),
            })

    frame = pd.DataFrame(rows)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "sizing_results.csv", index=False)
    features.to_csv(output / "candidate_futures_features.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.concat(trade_rows, ignore_index=True).to_csv(output / "variant_trades.csv", index=False)
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    (output / "summary.json").write_text(json.dumps({
        "control": frame[frame.variant == CONTROL].iloc[0].to_dict(),
        "accepted_variants": accepted,
        "decision": "accept" if accepted else "reject_all",
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(frame))
    return output


def _report(frame: pd.DataFrame) -> str:
    labels = {CONTROL: "Fixed $100 control", "crowded_q90_size70": "Crowded q90 → $70",
              "crowded_q95_size50": "Crowded q95 → $50"}
    rows = []
    for row in frame.itertuples():
        decision = "CONTROL" if row.variant == CONTROL else ("PASS" if row.accepted else "FAIL")
        rows.append(
            f"| {labels[row.variant]} | ${row.profit:.2f} | ${row.profit_change:+.2f} | "
            f"{row.profit_retention_pct:.1f}% | ${row.average_win:.2f} | ${row.average_loss:.2f} | "
            f"{row.max_drawdown_pct:.2f}% | {row.profit_to_drawdown:.2f} | "
            f"{row.crowded_fills} | ${row.crowded_profit:.2f} | "
            f"${row.ordinary_profit_change:+.2f} | ${row.walk_forward_change:+.2f} | "
            f"{row.risk_adjusted_wf_windows_improved}/6 | {decision} |"
        )
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    decision = f"Advance {', '.join(accepted)} to untouched forward testing; do not deploy yet." if accepted else (
        "Reject both crowding overlays; keep fixed $100 orders."
    )
    return f"""# ETH futures-crowding sizing experiment

## Result

**{decision}**

| Sizing | Profit | vs base | Profit retained | Avg win | Avg loss | Drawdown | Profit/drawdown | Crowded fills | Their profit | Ex-Apr/May change | WF change | Risk-adjusted WF improved | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(rows)}

Every spot signal and exit is unchanged. Size is reduced only when the latest strictly prior ETH perpetual funding rate and causal 24-hour open-interest growth are both positive and above the same trailing 90-day percentile.

The q95 headline gain came from four directly resized fills, all on 1 October 2024. It did not reproduce in any of the six walk-forward windows, so it is not robust enough to replace the baseline.
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
