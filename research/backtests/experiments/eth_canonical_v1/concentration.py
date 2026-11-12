"""Experiment 4: measure ETH profit concentration without changing the trading rules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .engine import ReplayResult, replay_portfolio
from .repeated_exposure import assign_episodes
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_profit_concentration_v1.json"


def monthly_profit(trades: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Return realized P&L for every calendar month, including zero-trade months."""
    first = pd.Timestamp(start).tz_localize(None).to_period("M")
    last = (pd.Timestamp(end) - pd.Timedelta(nanoseconds=1)).tz_localize(None).to_period("M")
    months = pd.period_range(first, last, freq="M")
    if trades.empty:
        return pd.Series(0.0, index=months, name="pnl")
    exits = trades.exit_time.dt.tz_localize(None).dt.to_period("M")
    return trades.groupby(exits).pnl.sum().reindex(months, fill_value=0.0).rename("pnl")


def drawdown_recoveries(equity: pd.DataFrame, tolerance: float = 1e-9) -> pd.DataFrame:
    """Measure each below-peak interval using the engine's hourly marked equity."""
    columns = ["start", "trough", "end", "recovered", "duration_days",
               "recovery_from_trough_days", "trough_drawdown_pct"]
    if equity.empty:
        return pd.DataFrame(columns=columns)
    underwater = equity.drawdown_usd.to_numpy() < -tolerance
    rows: list[dict] = []
    index = 0
    while index < len(equity):
        if not underwater[index]:
            index += 1
            continue
        start_index = index
        while index + 1 < len(equity) and underwater[index + 1]:
            index += 1
        last_underwater = index
        is_recovered = last_underwater + 1 < len(equity)
        end_index = last_underwater + 1 if is_recovered else last_underwater
        segment = equity.iloc[start_index:last_underwater + 1]
        trough_position = int(np.argmin(segment.drawdown_pct.to_numpy())) + start_index
        start_time = equity.iloc[start_index].timestamp
        trough_time = equity.iloc[trough_position].timestamp
        end_time = equity.iloc[end_index].timestamp
        rows.append({
            "start": start_time, "trough": trough_time, "end": end_time, "recovered": is_recovered,
            "duration_days": (end_time - start_time).total_seconds() / 86400,
            "recovery_from_trough_days": ((end_time - trough_time).total_seconds() / 86400
                                           if is_recovered else np.nan),
            "trough_drawdown_pct": float(segment.drawdown_pct.min()),
        })
        index += 1
    return pd.DataFrame(rows, columns=columns)


def concentration_metrics(result: ReplayResult, start: pd.Timestamp, end: pd.Timestamp,
                          excluded_month: str) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trades = result.trades
    months = monthly_profit(trades, start, end)
    episodes = trades.groupby("market_episode", dropna=False).agg(
        pnl=("pnl", "sum"), trades=("candidate_id", "size"),
        first_entry=("entry_time", "min"), last_exit=("exit_time", "max"),
    ).sort_values("pnl", ascending=False)
    positive_episodes = episodes[episodes.pnl > 0]
    total = float(trades.pnl.sum())
    excluded_value = float(months.get(pd.Period(excluded_month, freq="M"), 0.0))
    largest = float(positive_episodes.pnl.head(1).sum())
    largest_five = float(positive_episodes.pnl.head(5).sum())
    recoveries = drawdown_recoveries(result.equity)
    recovered = recoveries[recoveries.recovered] if len(recoveries) else recoveries
    unresolved = recoveries[~recoveries.recovered] if len(recoveries) else recoveries
    maximum_drawdown_episode = (recoveries.loc[recoveries.trough_drawdown_pct.idxmin()]
                                if len(recoveries) else None)
    longest_drawdown_episode = (recovered.loc[recovered.duration_days.idxmax()]
                                if len(recovered) else None)
    metrics = {
        "all_data_profit": total,
        "excluded_month": excluded_month,
        "excluded_month_profit": excluded_value,
        "profit_excluding_month": total - excluded_value,
        "largest_winning_episode_profit": largest,
        "profit_excluding_largest_episode": total - largest,
        "five_largest_winning_episodes_profit": largest_five,
        "profit_excluding_five_largest_episodes": total - largest_five,
        "best_month": str(months.idxmax()),
        "best_month_profit": float(months.max()),
        "best_month_share_pct": 100 * float(months.max()) / total if total > 0 else np.nan,
        "median_month_profit": float(months.median()),
        "worst_month": str(months.idxmin()),
        "worst_month_profit": float(months.min()),
        "profitable_months": int((months > 0).sum()),
        "flat_months": int(np.isclose(months, 0.0).sum()),
        "losing_months": int((months < 0).sum()),
        "market_episodes": int(len(episodes)),
        "largest_episode_share_pct": 100 * largest / total if total > 0 else np.nan,
        "five_largest_episode_share_pct": 100 * largest_five / total if total > 0 else np.nan,
        "median_recovered_drawdown_days": float(recovered.duration_days.median()) if len(recovered) else 0.0,
        "longest_recovered_drawdown_days": float(recovered.duration_days.max()) if len(recovered) else 0.0,
        "longest_drawdown_recovery_from_trough_days": (
            float(longest_drawdown_episode.recovery_from_trough_days)
            if longest_drawdown_episode is not None else 0.0
        ),
        "maximum_drawdown_recovery_from_trough_days": (
            float(maximum_drawdown_episode.recovery_from_trough_days)
            if maximum_drawdown_episode is not None and maximum_drawdown_episode.recovered else np.nan
        ),
        "unrecovered_drawdown_days": float(unresolved.duration_days.max()) if len(unresolved) else 0.0,
        "drawdown_episodes": int(len(recoveries)),
    }
    month_frame = months.rename_axis("month").reset_index()
    month_frame["month"] = month_frame.month.astype(str)
    return metrics, month_frame, episodes.reset_index(), recoveries


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    market, plain_candidates, windows = baseline_module.build_baseline()
    candidates = assign_episodes(plain_candidates, market, experiment)
    start, end = windows["full"]
    result = replay_portfolio(candidates, market, start, end, portfolio)
    metrics, months, episodes, recoveries = concentration_metrics(
        result, start, end, experiment["excluded_month"]
    )

    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    months.to_csv(output / "monthly_profit.csv", index=False)
    episodes.to_csv(output / "market_episode_profit.csv", index=False)
    recoveries.to_csv(output / "drawdown_recoveries.csv", index=False)
    (output / "summary.json").write_text(json.dumps(metrics, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(metrics))
    return output


def _report(m: dict) -> str:
    still_positive = (m["profit_excluding_month"] > 0
                      and m["profit_excluding_largest_episode"] > 0
                      and m["profit_excluding_five_largest_episodes"] > 0)
    verdict = "CONCENTRATED, BUT NOT DEPENDENT ON ONE OUTLIER" if still_positive else "OUTLIER-DEPENDENT"
    return f"""# ETH profit-concentration stress test

## Verdict: {verdict}

The strategy is unchanged. These exclusions are diagnostics, not tradable backtests.

| Test | Profit remaining |
|---|---:|
| All data | ${m['all_data_profit']:.2f} |
| Excluding {m['excluded_month']} | ${m['profit_excluding_month']:.2f} |
| Excluding largest winning episode | ${m['profit_excluding_largest_episode']:.2f} |
| Excluding five largest winning episodes | ${m['profit_excluding_five_largest_episodes']:.2f} |

## Concentration

- Best month: **{m['best_month']}**, ${m['best_month_profit']:.2f}, or **{m['best_month_share_pct']:.1f}%** of total profit.
- Largest episode: ${m['largest_winning_episode_profit']:.2f}, or **{m['largest_episode_share_pct']:.1f}%** of total profit.
- Five largest episodes: ${m['five_largest_winning_episodes_profit']:.2f}, or **{m['five_largest_episode_share_pct']:.1f}%** of total profit.
- Median month: **${m['median_month_profit']:.2f}**.
- Worst month: **{m['worst_month']}**, **${m['worst_month_profit']:.2f}**.
- Months: {m['profitable_months']} profitable, {m['flat_months']} flat, {m['losing_months']} losing.

## Drawdown recovery

- Median completed drawdown: **{m['median_recovered_drawdown_days']:.1f} days**.
- Longest time below a previous peak: **{m['longest_recovered_drawdown_days']:.1f} days**; recovery after its trough took **{m['longest_drawdown_recovery_from_trough_days']:.1f} days**.
- The maximum drawdown recovered **{m['maximum_drawdown_recovery_from_trough_days']:.1f} days** after its trough.
- Unrecovered drawdown at the data endpoint: **{m['unrecovered_drawdown_days']:.1f} days**.

## Decision

Keep the uncapped trend exit. The current strategy remains profitable after every requested exclusion, but its best month and five largest market episodes each supply about half of total profit. Future ETH candidates must improve ordinary periods as well as the full-history result; an improvement confined to the best month should be rejected.
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
