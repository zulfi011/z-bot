"""Experiment 5: audit ETH research for multiple-testing and holdout reuse risk."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.stats import kurtosis, norm, skew

from .run import STAGE2_ROOT


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_overfitting_audit_v1.json"
EULER_MASCHERONI = 0.5772156649015329


def moving_block_bootstrap(values: np.ndarray, block_length: int, samples: int,
                           seed: int) -> np.ndarray:
    """Bootstrap totals while keeping adjacent observations together in fixed-length blocks."""
    values = np.asarray(values, dtype=float)
    if not 1 <= block_length <= len(values):
        raise ValueError("block_length must be between one and the sample length")
    rng = np.random.default_rng(seed)
    starts = np.arange(len(values) - block_length + 1)
    blocks_needed = int(np.ceil(len(values) / block_length))
    chosen = rng.choice(starts, size=(samples, blocks_needed), replace=True)
    offsets = np.arange(block_length)
    sampled = values[chosen[..., None] + offsets]
    return sampled.reshape(samples, -1)[:, :len(values)].sum(axis=1)


def cscv_pbo(matrix: np.ndarray) -> tuple[float, pd.DataFrame]:
    """Estimate PBO by symmetric train/test splits of contiguous performance blocks."""
    matrix = np.asarray(matrix, dtype=float)
    block_count, strategy_count = matrix.shape
    if block_count < 4 or block_count % 2:
        raise ValueError("CSCV requires an even number of at least four blocks")
    rows = []
    for train in itertools.combinations(range(block_count), block_count // 2):
        test = tuple(index for index in range(block_count) if index not in train)
        train_score = matrix[list(train)].sum(axis=0)
        selected = int(np.argmax(train_score))
        test_score = matrix[list(test)].sum(axis=0)
        below = np.sum(test_score < test_score[selected])
        tied = np.sum(test_score == test_score[selected])
        percentile = float((below + 0.5 * tied) / strategy_count)
        rows.append({
            "train_blocks": ";".join(map(str, train)), "test_blocks": ";".join(map(str, test)),
            "selected_row": selected, "train_profit": train_score[selected],
            "test_profit": test_score[selected], "test_percentile": percentile,
            "below_oos_median": percentile < 0.5,
        })
    splits = pd.DataFrame(rows)
    return float(splits.below_oos_median.mean()), splits


def deflated_sharpe_sensitivity(returns: np.ndarray, trial_sharpes: np.ndarray,
                                trial_counts: list[int]) -> pd.DataFrame:
    """DSR sensitivity over assumed independent-trial counts; values are probabilities."""
    returns = np.asarray(returns, dtype=float)
    sharpe = float(returns.mean() / returns.std(ddof=1))
    trial_sharpes = np.asarray(trial_sharpes, dtype=float)
    trial_sharpes = trial_sharpes[np.isfinite(trial_sharpes)]
    sigma_trials = float(trial_sharpes.std(ddof=1))
    return_skew = float(skew(returns, bias=False))
    return_kurtosis = float(kurtosis(returns, fisher=False, bias=False))
    denominator = np.sqrt(
        1 - return_skew * sharpe + ((return_kurtosis - 1) / 4) * sharpe ** 2
    )
    rows = []
    for count in trial_counts:
        expected_maximum = sigma_trials * (
            (1 - EULER_MASCHERONI) * norm.ppf(1 - 1 / count)
            + EULER_MASCHERONI * norm.ppf(1 - 1 / (count * np.e))
        )
        statistic = (sharpe - expected_maximum) * np.sqrt(len(returns) - 1) / denominator
        rows.append({
            "assumed_independent_trials": count, "observed_block_sharpe": sharpe,
            "expected_maximum_sharpe": expected_maximum,
            "deflated_sharpe_probability": float(norm.cdf(statistic)),
            "passes_95_pct": bool(norm.cdf(statistic) >= 0.95),
        })
    return pd.DataFrame(rows)


def _selected_candidate_mask(frame: pd.DataFrame, candidate: dict) -> pd.Series:
    mask = pd.Series(True, index=frame.index)
    for field in ["trail_mode", "activation_pct", "giveback_pct", "stop_pct", "signal_minutes",
                  "average_days", "zone_pct", "trend", "skip_06_12"]:
        mask &= frame[field].eq(candidate[field])
    mask &= frame.be_trigger.isna() if candidate["be_trigger"] is None else frame.be_trigger.eq(candidate["be_trigger"])
    return mask


def _plateau(frame: pd.DataFrame, candidate: dict) -> pd.DataFrame:
    source = pd.read_csv(STAGE2_ROOT / "results" / "eth_full_research_v2" / "one_change_at_a_time.csv")
    rows = []
    for idea, part in source.groupby("idea", sort=False):
        if idea in {"trend", "skip_06_12", "be_trigger", "trail_start"}:
            continue
        rows.append({
            "dimension": idea, "variants": len(part), "profitable_full": int((part.full > 0).sum()),
            "profitable_earlier_and_later": int(((part.earlier > 0) & (part.later > 0)).sum()),
            "minimum_full_profit": float(part.full.min()), "median_full_profit": float(part.full.median()),
            "maximum_full_profit": float(part.full.max()),
        })
    fixed = pd.Series(True, index=frame.index)
    for field in ["trail_mode", "stop_pct", "signal_minutes", "average_days", "zone_pct",
                  "trend", "skip_06_12"]:
        fixed &= frame[field].eq(candidate[field])
    fixed &= frame.be_trigger.isna()
    givebacks = frame[fixed].sort_values("giveback_pct")
    rows.append({
        "dimension": "activation_giveback_pair", "variants": len(givebacks),
        "profitable_full": int((givebacks.full_profit > 0).sum()),
        "profitable_earlier_and_later": int(((givebacks.earlier_profit > 0)
                                             & (givebacks.later_profit > 0)).sum()),
        "minimum_full_profit": float(givebacks.full_profit.min()),
        "median_full_profit": float(givebacks.full_profit.median()),
        "maximum_full_profit": float(givebacks.full_profit.max()),
    })
    return pd.DataFrame(rows)


def _artifact_row_count(path: Path) -> int | None:
    if path.suffix == ".parquet":
        return pq.ParquetFile(path).metadata.num_rows
    if path.suffix == ".csv":
        with path.open() as handle:
            return max(sum(1 for _ in handle) - 1, 0)
    return None


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    config = json.loads(config_path.read_text())
    registry_path = STAGE2_ROOT / config["registry"]
    registry = pd.read_csv(registry_path)
    registry["artifact_exists"] = registry.artifact.map(lambda value: (STAGE2_ROOT / value).exists())
    if not registry.artifact_exists.all():
        missing = registry.loc[~registry.artifact_exists, "artifact"].tolist()
        raise FileNotFoundError(f"Registry artifacts missing: {missing}")
    registry["observed_rows"] = registry.artifact.map(lambda value: _artifact_row_count(STAGE2_ROOT / value))
    comparable = registry.observed_rows.notna()
    registry["count_matches_artifact"] = np.where(
        comparable, registry.observed_rows.eq(registry.trial_count), True
    )
    if not registry.count_matches_artifact.all():
        raise ValueError("A registry trial count does not match its artifact")

    pbo_path = STAGE2_ROOT / config["pbo"]["artifact"]
    profit_columns = [f"wf{index}_test_profit" for index in range(config["pbo"]["blocks"])]
    parameter_columns = ["trail_mode", "activation_pct", "giveback_pct", "be_trigger", "stop_pct",
                         "signal_minutes", "average_days", "zone_pct", "trend", "skip_06_12"]
    grid = pd.read_parquet(pbo_path, columns=[*parameter_columns, "full_profit", "earlier_profit",
                                              "later_profit", *profit_columns])
    performance = grid[profit_columns].to_numpy(float).T
    pbo, splits = cscv_pbo(performance)

    candidate_path = pbo_path.parent / "candidate.json"
    candidate = json.loads(candidate_path.read_text())
    candidate_rows = np.flatnonzero(_selected_candidate_mask(grid, candidate).to_numpy())
    if len(candidate_rows) != 1:
        raise ValueError(f"Expected one selected historical candidate; found {len(candidate_rows)}")
    selected_returns = performance[:, candidate_rows[0]] / 300.0
    means = performance.mean(axis=0)
    deviations = performance.std(axis=0, ddof=1)
    trial_sharpes = np.divide(means, deviations, out=np.full(len(means), np.nan), where=deviations > 0)
    dsr = deflated_sharpe_sensitivity(
        selected_returns, trial_sharpes, config["deflated_sharpe"]["trial_count_scenarios"]
    )
    plateau = _plateau(grid, candidate)

    concentration_dir = STAGE2_ROOT / "results" / "eth_profit_concentration_v1"
    months = pd.read_csv(concentration_dir / "monthly_profit.csv").pnl.to_numpy(float)
    episodes = pd.read_csv(concentration_dir / "market_episode_profit.csv").sort_values("first_entry").pnl.to_numpy(float)
    uncertainty = config["uncertainty"]
    monthly_bootstrap = moving_block_bootstrap(
        months, uncertainty["contiguous_month_block_length"], uncertainty["samples"], uncertainty["seed"]
    )
    episode_bootstrap = moving_block_bootstrap(
        episodes, uncertainty["contiguous_episode_block_length"], uncertainty["samples"], uncertainty["seed"] + 1
    )
    intervals = pd.DataFrame([
        {"method": "3_contiguous_month_blocks", "lower_95": np.percentile(monthly_bootstrap, 2.5),
         "median": np.median(monthly_bootstrap), "upper_95": np.percentile(monthly_bootstrap, 97.5)},
        {"method": "12_contiguous_episode_blocks", "lower_95": np.percentile(episode_bootstrap, 2.5),
         "median": np.median(episode_bootstrap), "upper_95": np.percentile(episode_bootstrap, 97.5)},
    ])

    raw_path = STAGE2_ROOT.parent / "stage1_research" / "data" / "raw" / "ETHUSDT" / "ETHUSDT_1m.parquet"
    raw_times = pd.read_parquet(raw_path, columns=["open_time"]).open_time
    data_start, data_end = raw_times.min(), raw_times.max()
    holdout_files = list((STAGE2_ROOT / "data" / "holdout_downloads").glob("ETHUSDT-1m-*.zip"))
    if holdout_files:
        data_end = max(data_end, pd.Timestamp(config["retired_holdout"]["end"]) - pd.Timedelta(minutes=1))
    registry_hash = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    raw_trial_evaluations = int(registry.trial_count.sum())
    forward_start = pd.Timestamp(config["forward_acceptance"]["freeze_timestamp"])
    complete_forward_months = max(
        0, (data_end.year - forward_start.year) * 12 + data_end.month - forward_start.month
    )
    summary = {
        "registry_entries": int(len(registry)), "raw_trial_evaluations": raw_trial_evaluations,
        "registry_sha256": registry_hash, "cscv_pbo": pbo, "cscv_splits": len(splits),
        "data_start": data_start.isoformat(), "data_end": data_end.isoformat(),
        "has_prolonged_bear_market_history": False,
        "retired_holdout": config["retired_holdout"],
        "complete_new_forward_months": complete_forward_months,
        "required_new_forward_months": config["forward_acceptance"]["minimum_complete_utc_months"],
        "earliest_possible_forward_decision": config["forward_acceptance"]["earliest_possible_decision"],
        "monthly_block_bootstrap_lower_95": float(intervals.iloc[0].lower_95),
        "episode_block_bootstrap_lower_95": float(intervals.iloc[1].lower_95),
        "minimum_dsr_probability": float(dsr.deflated_sharpe_probability.min()),
        "maximum_dsr_probability": float(dsr.deflated_sharpe_probability.max()),
    }

    output = output_dir or STAGE2_ROOT / "results" / config["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    registry.to_csv(output / "validated_registry.csv", index=False)
    splits.to_csv(output / "cscv_splits.csv", index=False)
    dsr.to_csv(output / "deflated_sharpe_sensitivity.csv", index=False)
    plateau.to_csv(output / "parameter_plateau.csv", index=False)
    intervals.to_csv(output / "block_bootstrap_uncertainty.csv", index=False)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(summary, dsr, plateau, intervals))
    return output


def _report(summary: dict, dsr: pd.DataFrame, plateau: pd.DataFrame,
            intervals: pd.DataFrame) -> str:
    low_trials = dsr.iloc[0]
    raw_trials = dsr.iloc[-1]
    return f"""# ETH overfitting-risk audit

## Verdict: NOT INDEPENDENTLY VALIDATED

The strategy remains profitable in the historical robustness checks, but the search history is too large and the genuinely new forward sample is currently empty. No new ETH rule should be promoted from these data alone.

## Search registry

- Registered research groups: **{summary['registry_entries']}**.
- Recorded raw rule evaluations: **{summary['raw_trial_evaluations']:,}**.
- Registry fingerprint: `{summary['registry_sha256']}`.
- These are raw evaluations, not independent trials; many rules are closely related.

## Statistical diagnostics

- Six-block CSCV estimate: **{summary['cscv_pbo']:.1%} PBO** across {summary['cscv_splits']} symmetric splits.
- DSR sensitivity with only {int(low_trials.assumed_independent_trials):,} assumed independent trials: **{low_trials.deflated_sharpe_probability:.1%}**.
- DSR sensitivity using all {int(raw_trials.assumed_independent_trials):,} historical grid rows as independent: **{raw_trials.deflated_sharpe_probability:.2e}**.
- The DSR result is a sensitivity diagnostic, not a definitive estimate: there are only six return blocks and the real independent-trial count is unknown.
- The 0% CSCV estimate is also not proof against overfitting; six blocks give only 20 splits and all blocks have already influenced research.

## Contiguous-block uncertainty

| Method | 95% lower | Median | 95% upper |
|---|---:|---:|---:|
| Three-month blocks | ${intervals.iloc[0].lower_95:.2f} | ${intervals.iloc[0]['median']:.2f} | ${intervals.iloc[0].upper_95:.2f} |
| Twelve-episode blocks | ${intervals.iloc[1].lower_95:.2f} | ${intervals.iloc[1]['median']:.2f} | ${intervals.iloc[1].upper_95:.2f} |

Both intervals remain positive, which supports the existence of a historical edge. They do not erase selection bias.

## Parameter plateau

| Dimension | Profitable full | Profitable in both halves | Full-profit range |
|---|---:|---:|---:|
""" + "\n".join(
        f"| {row.dimension} | {row.profitable_full}/{row.variants} | "
        f"{row.profitable_earlier_and_later}/{row.variants} | "
        f"${row.minimum_full_profit:.2f} to ${row.maximum_full_profit:.2f} |"
        for row in plateau.itertuples()
    ) + f"""

The result has useful neighbouring plateaus, but the selected zone width and activation/giveback pair sit at the tested boundary. Future searches must widen the range before treating the single best point as stable.

## Holdout and data status

- August 1–September 10, 2026 is now named **post-selection research data** and removed from acceptance gates.
- New forward months completed after the freeze: **{summary['complete_new_forward_months']} of {summary['required_new_forward_months']} required**.
- Earliest possible decision under the frozen rule: **{summary['earliest_possible_forward_decision'][:10]}**.
- Local clean minute history begins **{summary['data_start'][:10]}**. No older prolonged ETH bear market is available locally.

## Decision

Keep the live strategy unchanged. Continue paper/live observation without tuning against the protected forward months. Do not accept another strategy change until at least three untouched full UTC months are available, and obtain older clean ETH minute history before claiming cross-cycle robustness.
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
