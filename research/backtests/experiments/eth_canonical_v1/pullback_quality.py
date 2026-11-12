"""ETH experiment: filter Pullback entries for evidence that the trend is still advancing."""

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


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_pullback_quality_v1.json"
CONTROL = "current_pullback"
LABELS = {
    CONTROL: "Current pullback",
    "ema_rising_6h": "24h EMA above 6h ago",
    "ema_rising_12h": "24h EMA above 12h ago",
    "reclaim_above_previous_5m_high": "Reclaim above EMA + previous 5m high",
}


def filter_passes(rule_name: str, ema_now: float, ema_6h: float, ema_12h: float,
                  reclaim_close: float, previous_5m_high: float) -> bool:
    """Frozen, independently tested Pullback quality predicates."""
    if rule_name == CONTROL:
        return True
    if rule_name == "ema_rising_6h":
        return ema_now > ema_6h
    if rule_name == "ema_rising_12h":
        return ema_now > ema_12h
    if rule_name == "reclaim_above_previous_5m_high":
        return reclaim_close > ema_now and reclaim_close > previous_5m_high
    raise ValueError(f"Unknown Pullback quality rule: {rule_name}")


def pullback_signal_table() -> pd.DataFrame:
    """Rebuild deployed 24h/180m Pullback signals and attach causal filter inputs."""
    raw, bullish = baseline_module.compare.load("ETHUSDT")
    rule = baseline_module.live.load_rule("eth")
    close = baseline_module.grid.CLOSE
    high = baseline_module.grid.HIGH
    times = pd.DatetimeIndex(baseline_module.grid.TIMES)
    ema = pd.Series(close).ewm(span=24 * 60, adjust=False).mean().to_numpy()
    below = close < ema
    index = np.arange(len(close))
    last_above = np.maximum.accumulate(np.where(~below, index, 0))
    run = index - last_above
    reclaim = (~below) & np.r_[False, below[:-1]]
    reclaim[0] = False
    where = np.flatnonzero(reclaim)
    where = where[run[where - 1] >= 180]
    where = where[bullish[where]]
    entries = where + 1
    valid = entries < len(close) - 1
    where, entries = where[valid], entries[valid]
    if rule["blocked"]:
        hours = times[entries].hour
        allowed = ~((hours >= rule["blocked"][0]) & (hours < rule["blocked"][1]))
        where, entries = where[allowed], entries[allowed]

    five_minute_high = pd.Series(high, index=times).resample("5min").max()
    previous_bucket_high = five_minute_high.shift(1)
    bucket = times[where].floor("5min")
    previous_high = previous_bucket_high.reindex(bucket).to_numpy()
    return pd.DataFrame({
        "reclaim": where.astype(np.int64),
        "entry": entries.astype(np.int64),
        "entry_time": times[entries],
        "ema_now": ema[where],
        "ema_6h": ema[where - 360],
        "ema_12h": ema[where - 720],
        "reclaim_close": close[where],
        "previous_5m_high": previous_high,
    })


def allowed_entries(rule_name: str, signals: pd.DataFrame) -> set[int]:
    mask = [filter_passes(
        rule_name, row.ema_now, row.ema_6h, row.ema_12h,
        row.reclaim_close, row.previous_5m_high,
    ) for row in signals.itertuples()]
    return set(signals.loc[mask, "entry"].astype(int))


def _ordinary(result: ReplayResult, excluded_months: list[str]) -> tuple[int, float]:
    trades = result.trades
    if not len(trades):
        return 0, 0.0
    ordinary = trades[~_excluded_month_mask(trades, excluded_months)]
    return len(ordinary), float(ordinary.pnl.sum())


def _metrics(result: ReplayResult, excluded_months: list[str], threshold: float) -> dict:
    ordinary_trades, ordinary_profit = _ordinary(result, excluded_months)
    pull = result.trades[result.trades.source == "pullback"]
    pull_ordinary = pull[~_excluded_month_mask(pull, excluded_months)] if len(pull) else pull
    q = quality(result, threshold)
    return {
        "profit": float(result.summary["net_profit"]),
        "trades": int(result.summary["trades"]),
        "headline_win_rate_pct": float(result.summary["win_rate_pct"]),
        "average_win": float(result.summary["average_win"]),
        "average_loss": float(result.summary["average_loss"]),
        "profit_factor": float(result.summary["profit_factor"]),
        "max_drawdown_pct": float(result.summary["maximum_drawdown_pct"]),
        "ordinary_trades": ordinary_trades,
        "ordinary_profit": ordinary_profit,
        "pullback_trades": len(pull),
        "pullback_profit": float(pull.pnl.sum()),
        "pullback_profit_per_trade": float(pull.pnl.mean()) if len(pull) else 0.0,
        "ordinary_pullback_trades": len(pull_ordinary),
        "ordinary_pullback_profit": float(pull_ordinary.pnl.sum()),
        **q,
    }


def _passes(row: dict, control: dict, acceptance: dict) -> bool:
    return bool(
        row["profit_change"] > acceptance["full_profit_change_gt"]
        and row["ordinary_profit_change"] > acceptance["ordinary_profit_change_gt"]
        and row["walk_forward_change"] > acceptance["walk_forward_change_gt"]
        and row["wf_windows_improved"] >= acceptance["minimum_walk_forward_windows_improved"]
        and row["economic_win_rate_pct"] >= control["economic_win_rate_pct"]
        and row["average_economic_loss"] >= control["average_economic_loss"]
        and row["max_drawdown_pct"] >= control["max_drawdown_pct"]
    )


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    market, candidates, windows = baseline_module.build_baseline()
    signals = pullback_signal_table()
    canonical_pullback_entries = {candidate.entry for candidate in candidates if candidate.source == "pullback"}
    if allowed_entries(CONTROL, signals) != canonical_pullback_entries:
        raise AssertionError("Current Pullback signal rebuild does not match the canonical candidate book")

    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    variants = [CONTROL, *[item["name"] for item in experiment["variants"]]]
    books: dict[str, list[CandidateTrade]] = {}
    for variant in variants:
        allowed = allowed_entries(variant, signals)
        books[variant] = [candidate for candidate in candidates
                          if candidate.source != "pullback" or candidate.entry in allowed]

    results = {
        variant: {name: replay_portfolio(book, market, *windows[name], portfolio) for name in names}
        for variant, book in books.items()
    }
    control_results = results[CONTROL]
    _assert_expected(
        control_results["full"].summary,
        baseline_config["acceptance"],
        float(baseline_config["acceptance_tolerance"]),
    )
    threshold = float(experiment["economic_winner_threshold_pct"])
    excluded_months = experiment["excluded_entry_months"]
    control_metrics = _metrics(control_results["full"], excluded_months, threshold)
    control_ids = set(control_results["full"].trades.candidate_id)
    control_pull = control_results["full"].trades[
        control_results["full"].trades.source == "pullback"
    ]
    rows, window_rows, trade_rows = [], [], []
    for variant in variants:
        by_window = results[variant]
        full = by_window["full"]
        metrics = _metrics(full, excluded_months, threshold)
        changes = [by_window[name].summary["net_profit"] - control_results[name].summary["net_profit"]
                   for name in wf_names]
        variant_ids = set(full.trades.candidate_id)
        removed = control_pull[~control_pull.candidate_id.isin(variant_ids)]
        removed_winners = removed[removed.pnl > 0]
        row = {
            "variant": variant,
            "candidate_pullbacks": sum(c.source == "pullback" for c in books[variant]),
            **metrics,
            "profit_change": metrics["profit"] - control_metrics["profit"],
            "trade_change": metrics["trades"] - control_metrics["trades"],
            "ordinary_profit_change": metrics["ordinary_profit"] - control_metrics["ordinary_profit"],
            "walk_forward_profit": sum(by_window[name].summary["net_profit"] for name in wf_names),
            "walk_forward_change": sum(changes),
            "wf_windows_improved": sum(change > 0 for change in changes),
            "baseline_pullback_fills_removed": len(removed),
            "profitable_baseline_pullbacks_removed": len(removed_winners),
            "profitable_baseline_pullback_pnl_removed": float(removed_winners.pnl.sum()),
            "replacement_fills_admitted": len(variant_ids - control_ids),
        }
        row["accepted"] = variant != CONTROL and _passes(row, control_metrics, experiment["acceptance"])
        rows.append(row)
        trade_rows.append(full.trades.assign(variant=variant))
        for name in names:
            window_rows.append({
                "variant": variant,
                "window": name,
                "profit": by_window[name].summary["net_profit"],
                "control_profit": control_results[name].summary["net_profit"],
                "profit_change": by_window[name].summary["net_profit"]
                                 - control_results[name].summary["net_profit"],
            })

    frame = pd.DataFrame(rows)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "variant_results.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.concat(trade_rows, ignore_index=True).to_csv(output / "variant_trades.csv", index=False)
    signals.to_csv(output / "pullback_signal_inputs.csv", index=False)
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    summary = {
        "control": frame[frame.variant == CONTROL].iloc[0].to_dict(),
        "accepted_variants": accepted,
        "decision": "accept" if accepted else "reject_all",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(frame))
    return output


def _report(frame: pd.DataFrame) -> str:
    rows = []
    for row in frame.itertuples():
        decision = "CONTROL" if row.variant == CONTROL else ("PASS" if row.accepted else "FAIL")
        rows.append(
            f"| {LABELS[row.variant]} | ${row.profit:.2f} | ${row.profit_change:+.2f} | "
            f"{row.trades} ({row.trade_change:+d}) | {row.economic_win_rate_pct:.1f}% | "
            f"${row.average_economic_loss:.2f} | ${row.ordinary_profit:.2f} | "
            f"${row.ordinary_profit_change:+.2f} | ${row.walk_forward_change:+.2f} | "
            f"{row.wf_windows_improved}/6 | {row.max_drawdown_pct:.2f}% | {decision} |"
        )
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    decision = ("Accept: " + ", ".join(LABELS[name] for name in accepted)) if accepted else (
        "Reject all three filters; keep the current Pullback rule unchanged."
    )
    return f"""# ETH Pullback quality filter

## Result

**{decision}**

| Rule | Profit | vs base | Trades | Economic win rate | Avg economic loss | Ex-Apr/May profit | Ex-Apr/May change | WF change | WF improved | Drawdown | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(rows)}

Economic winners are trades above +0.25%; economic losses are below -0.25%. April–May exclusion uses the filled trade's entry month. Filters were tested separately, with unchanged entries and exits for Dip and Mode C and unchanged Pullback exits.
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
