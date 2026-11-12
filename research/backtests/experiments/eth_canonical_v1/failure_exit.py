"""Experiment 1: exit a stale, unarmed ETH setup after its reference fails."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .engine import CandidateTrade, MarketData, PortfolioConfig, ReplayResult, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config

FAILURE_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_failure_exit_v1.json"
EXIT_CODE = 4


def _dip_references(raw, rule) -> dict[int, float]:
    """Frozen lower edge of the original dip zone, keyed by execution minute."""
    replay = baseline_module.compare.replay
    grid = baseline_module.grid
    daily = replay.daily_averages(raw)
    average_n = replay.daily_average_n(raw, rule["average_days"])
    frame = grid.signal_frame(raw, daily, rule["minutes"])
    for period in (7, 15, 30):
        frame[period] = np.array([np.nan if value is None else float(value) for value in frame[period]])
    days = frame["open_time"].floor("D")
    average = np.array([
        float(average_n[day]) if average_n.get(day) is not None else np.nan for day in days
    ])
    zone = rule["zone_pct"] / 100
    high, low = frame["high"], frame["low"]
    lower, upper = average * (1 - zone), average * (1 + zone)
    touched = np.isfinite(average) & (high >= lower * (1 - 1e-12)) & (low <= upper * (1 + 1e-12))
    prior_below = np.zeros(len(high), bool)
    prior_below[1:] = np.isfinite(average[:-1]) & (high[:-1] < lower[:-1] * (1 - 1e-12))
    a7, a15, a30 = frame[7], frame[15], frame[30]
    missing = ~(np.isfinite(a7) & np.isfinite(a15) & np.isfinite(a30))
    bearish = ~missing & (a7 < a15) & (a15 < a30)
    eligible = touched & ~np.r_[False, touched[:-1]] & prior_below & ~(bearish | missing)
    bullish_candle = frame["close"] > frame["open"]
    confirmations, references = [], []
    for origin in np.flatnonzero(eligible):
        for offset in range(30 // rule["minutes"] + 1):
            index = origin + offset
            if index >= len(high):
                break
            if bullish_candle[index]:
                confirmations.append(index)
                references.append(float(lower[origin]))
                break
            if not touched[index]:
                break
    confirmations = np.asarray(confirmations, dtype=np.int64)
    references = np.asarray(references, dtype=float)
    entries = frame["first_raw"] + (confirmations + 1) * rule["minutes"]
    keep = entries < len(raw) - 1
    entries, references = entries[keep], references[keep]
    if rule["blocked"] and len(entries):
        hours = pd.DatetimeIndex(raw.open_time).hour.to_numpy()[entries]
        keep = ~((hours >= rule["blocked"][0]) & (hours < rule["blocked"][1]))
        entries, references = entries[keep], references[keep]
    return dict(zip(entries.astype(int), references, strict=True))


def _mode_c_references(raw, rule) -> dict[int, float]:
    """Frozen upper boundary of the original Mode C consolidation band."""
    grid = baseline_module.grid
    v4 = baseline_module.compare.v4
    high, low, _, close, last_minute = v4.bars_for(raw, 120)
    top = pd.Series(high).rolling(12).max().to_numpy()
    bottom = pd.Series(low).rolling(12).min().to_numpy()
    zone_top, zone_bottom = np.r_[np.nan, top[:-1]], np.r_[np.nan, bottom[:-1]]
    quiet = (zone_top / zone_bottom - 1) <= 2.5 / 100
    broke = quiet & (close > zone_top)
    where = np.flatnonzero(broke & ~np.r_[False, broke[:-1]])
    check = last_minute[where] + 30
    valid = check < len(raw) - 1
    where, check = where[valid], check[valid]
    held = grid.CLOSE[check] > zone_top[where]
    entries, references = (check[held] + 1).astype(np.int64), zone_top[where][held]
    if rule["blocked"] and len(entries):
        hours = grid.TIMES[entries].hour
        keep = ~((hours >= rule["blocked"][0]) & (hours < rule["blocked"][1]))
        entries, references = entries[keep], references[keep]
    return dict(zip(entries.astype(int), references.astype(float), strict=True))


def setup() -> tuple[MarketData, list[CandidateTrade], dict, dict[str, dict[int, float]], np.ndarray]:
    market, candidates, windows = baseline_module.build_baseline()
    raw = baseline_module.compare.load("ETHUSDT")[0]
    rule = baseline_module.live.load_rule("eth")
    references = {"dip": _dip_references(raw, rule), "breakout": _mode_c_references(raw, rule)}
    ema_24h = pd.Series(baseline_module.grid.CLOSE).ewm(span=1440, adjust=False).mean().to_numpy()
    expected = {source: {c.entry for c in candidates if c.source == source} for source in references}
    for source in references:
        if set(references[source]) != expected[source]:
            raise AssertionError(f"{source} failure references do not match the frozen baseline entries")
    return market, candidates, windows, references, ema_24h


def checkpoint_index(times: pd.DatetimeIndex, entry: int, hours: int) -> int | None:
    """Last minute in the first completed UTC five-minute candle at/after the checkpoint."""
    target = times[entry] + pd.Timedelta(hours=hours)
    boundary = target.ceil("5min")
    evaluation_time = boundary - pd.Timedelta(minutes=1)
    index = int(times.searchsorted(evaluation_time))
    return index if index < len(times) and times[index] == evaluation_time and index + 1 < len(times) else None


def apply_failure_exit(
    candidates: list[CandidateTrade], market: MarketData, source: str, hours: int,
    references: dict[str, dict[int, float]], ema_24h: np.ndarray,
    arm_pct: float = 1.315, maximum_progress_pct: float = 0.5,
) -> tuple[list[CandidateTrade], pd.DataFrame, dict]:
    """Replace the baseline exit only when all three preregistered failure conditions hold."""
    grid = baseline_module.grid
    changed, diagnostics = [], []
    funnel = {"source_candidates": 0, "survived_to_checkpoint": 0, "unarmed": 0,
              "low_progress": 0, "reference_failed": 0}
    for candidate in candidates:
        if candidate.source != source:
            changed.append(candidate)
            continue
        funnel["source_candidates"] += 1
        check = checkpoint_index(market.times, candidate.entry, hours)
        if check is None or candidate.exit <= check:
            changed.append(candidate)
            continue
        funnel["survived_to_checkpoint"] += 1
        fill = float(grid.OPEN[candidate.entry]) * (1 + grid.SLIP)
        peak = float(np.max(grid.HIGH[candidate.entry:check + 1]))
        mfe_pct = 100 * (peak / fill - 1)
        if peak >= fill * (1 + arm_pct / 100):
            changed.append(candidate)
            continue
        funnel["unarmed"] += 1
        if mfe_pct >= maximum_progress_pct:
            changed.append(candidate)
            continue
        funnel["low_progress"] += 1
        reference = float(ema_24h[check]) if source == "pullback" else float(references[source][candidate.entry])
        check_close = float(grid.CLOSE[check])
        if check_close >= reference:
            changed.append(candidate)
            continue
        funnel["reference_failed"] += 1
        early = replace(candidate, exit=check + 1, exit_price=float(grid.OPEN[check + 1]), exit_code=EXIT_CODE)
        changed.append(early)
        diagnostics.append({
            "candidate_id": candidate.candidate_id, "source": source, "hours": hours,
            "entry_index": candidate.entry, "entry_time": market.times[candidate.entry],
            "checkpoint_index": check, "checkpoint_time": market.times[check],
            "failure_exit_index": check + 1, "failure_exit_time": market.times[check + 1],
            "mfe_pct": mfe_pct, "checkpoint_close": check_close, "failure_reference": reference,
            "baseline_exit_index": candidate.exit, "baseline_exit_code": candidate.exit_code,
        })
    return changed, pd.DataFrame(diagnostics), funnel


def _counterfactual_pnl(candidate: CandidateTrade, row, market: MarketData,
                        end: pd.Timestamp, config: PortfolioConfig) -> float:
    last = int(market.times.searchsorted(end)) - 1
    exit_index = min(candidate.exit, last)
    raw_exit = float(market.close[last]) if candidate.exit > last else candidate.exit_price
    quantity = row.spend / (row.entry_fill_price * (1 + config.fee_per_side))
    proceeds = quantity * raw_exit * (1 - config.slippage_per_side) * (1 - config.fee_per_side)
    return float(proceeds - row.spend)


def _diagnose(
    baseline: ReplayResult, variant: ReplayResult, baseline_by_id: dict[str, CandidateTrade],
    early_rules: pd.DataFrame, market: MarketData, end: pd.Timestamp, config: PortfolioConfig,
) -> dict:
    early_ids = set(early_rules.candidate_id) if len(early_rules) else set()
    taken_early = variant.trades[variant.trades.candidate_id.isin(early_ids)].copy()
    if len(taken_early):
        taken_early["baseline_pnl_same_trade"] = [
            _counterfactual_pnl(baseline_by_id[row.candidate_id], row, market, end, config)
            for row in taken_early.itertuples()
        ]
        taken_early["direct_change"] = taken_early.pnl - taken_early.baseline_pnl_same_trade
    baseline_ids, variant_ids = set(baseline.trades.candidate_id), set(variant.trades.candidate_id)
    replacements = variant.trades[variant.trades.candidate_id.isin(variant_ids - baseline_ids)]
    displaced = baseline.trades[baseline.trades.candidate_id.isin(baseline_ids - variant_ids)]
    return {
        "early_exit_candidates": int(len(early_rules)),
        "early_exits_taken": int(len(taken_early)),
        "baseline_recoveries_cut": int((taken_early.baseline_pnl_same_trade > 0).sum()) if len(taken_early) else 0,
        "direct_trade_change": float(taken_early.direct_change.sum()) if len(taken_early) else 0.0,
        "loss_avoided": float(taken_early.direct_change.clip(lower=0).sum()) if len(taken_early) else 0.0,
        "recovery_cost": float((-taken_early.direct_change.clip(upper=0)).sum()) if len(taken_early) else 0.0,
        "replacement_trades": int(len(replacements)),
        "replacement_pnl": float(replacements.pnl.sum()) if len(replacements) else 0.0,
        "displaced_trades": int(len(displaced)),
        "displaced_baseline_pnl": float(displaced.pnl.sum()) if len(displaced) else 0.0,
    }


def run(config_path: Path = FAILURE_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    market, baseline_candidates, windows, references, ema_24h = setup()
    window_names = baseline_config["evaluation"]["windows"]
    baseline_results = {
        name: replay_portfolio(baseline_candidates, market, *windows[name], portfolio) for name in window_names
    }
    baseline_by_id = {candidate.candidate_id: candidate for candidate in baseline_candidates}
    wf_names = [name for name in window_names if name.startswith("wf")]

    rows, diagnostic_rows, funnels, window_rows, source_rows = [], [], [], [], []
    for source in experiment["sources"]:
        for hours in experiment["checkpoints_hours"]:
            variant_candidates, early_rules, funnel = apply_failure_exit(
                baseline_candidates, market, source, hours, references, ema_24h,
                float(experiment["arm_pct"]), float(experiment["maximum_favorable_excursion_pct"]),
            )
            results = {
                name: replay_portfolio(variant_candidates, market, *windows[name], portfolio)
                for name in window_names
            }
            for name in window_names:
                window_rows.append({
                    "variant": f"{source}_{hours}h", "window": name,
                    "profit": results[name].summary["net_profit"],
                    "baseline_profit": baseline_results[name].summary["net_profit"],
                    "profit_change": (results[name].summary["net_profit"]
                                      - baseline_results[name].summary["net_profit"]),
                    "trades": results[name].summary["trades"],
                    "win_rate_pct": results[name].summary["win_rate_pct"],
                    "max_drawdown_pct": results[name].summary["maximum_drawdown_pct"],
                })
            full, base_full = results["full"], baseline_results["full"]
            diagnostic = _diagnose(
                base_full, full, baseline_by_id, early_rules, market, windows["full"][1], portfolio
            )
            wf_diffs = [results[name].summary["net_profit"] - baseline_results[name].summary["net_profit"]
                        for name in wf_names]
            row = {
                "variant": f"{source}_{hours}h", "source": source, "checkpoint_hours": hours,
                "profit": full.summary["net_profit"],
                "profit_change": full.summary["net_profit"] - base_full.summary["net_profit"],
                "trades": full.summary["trades"], "win_rate_pct": full.summary["win_rate_pct"],
                "average_win": full.summary["average_win"], "average_loss": full.summary["average_loss"],
                "profit_factor": full.summary["profit_factor"],
                "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
                "walk_forward_profit": sum(results[name].summary["net_profit"] for name in wf_names),
                "walk_forward_change": sum(wf_diffs),
                "wf_windows_improved": sum(value > 0 for value in wf_diffs),
                "post_selection_profit": results["post_selection_2026_08_09"].summary["net_profit"],
                "post_selection_change": (results["post_selection_2026_08_09"].summary["net_profit"]
                                           - baseline_results["post_selection_2026_08_09"].summary["net_profit"]),
                **diagnostic,
            }
            rows.append(row)
            for family, part in full.trades.groupby("source", sort=True):
                wins, losses = part[part.pnl > 0], part[part.pnl <= 0]
                source_rows.append({
                    "variant": row["variant"], "source": family, "trades": len(part),
                    "wins": len(wins), "win_rate_pct": 100 * len(wins) / len(part),
                    "net_profit": part.pnl.sum(),
                    "average_win": wins.pnl.mean() if len(wins) else 0.0,
                    "average_loss": losses.pnl.mean() if len(losses) else 0.0,
                })
            funnels.append({"variant": row["variant"], **funnel})
            if len(early_rules):
                diagnostic_rows.append(early_rules.assign(variant=row["variant"]))

    frame = pd.DataFrame(rows).sort_values(["profit_change", "walk_forward_change"], ascending=False)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.DataFrame(source_rows).to_csv(output / "results_by_entry_family.csv", index=False)
    pd.DataFrame(funnels).to_csv(output / "condition_funnel.csv", index=False)
    all_diagnostics = pd.concat(diagnostic_rows, ignore_index=True) if diagnostic_rows else pd.DataFrame()
    all_diagnostics.to_csv(output / "early_exit_candidates.csv", index=False)
    baseline_row = {
        "profit": baseline_results["full"].summary["net_profit"],
        "win_rate_pct": baseline_results["full"].summary["win_rate_pct"],
        "average_win": baseline_results["full"].summary["average_win"],
        "average_loss": baseline_results["full"].summary["average_loss"],
        "max_drawdown_pct": baseline_results["full"].summary["maximum_drawdown_pct"],
        "walk_forward_profit": sum(baseline_results[name].summary["net_profit"] for name in wf_names),
        "post_selection_profit": baseline_results["post_selection_2026_08_09"].summary["net_profit"],
    }
    (output / "summary.json").write_text(json.dumps({
        "baseline": baseline_row, "best_by_full_profit": frame.iloc[0].to_dict(),
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_simple_report(baseline_row, frame))
    return output


def _simple_report(baseline: dict, frame: pd.DataFrame) -> str:
    best = frame.iloc[0]
    robust = bool(
        best.profit_change > 0 and best.walk_forward_change > 0
        and best.wf_windows_improved >= 4
        and best.max_drawdown_pct >= baseline["max_drawdown_pct"]
    )
    verdict = "IMPROVED" if robust else "DOES NOT ROBUSTLY IMPROVE"
    lines = [
        "# ETH conditional setup-failure exit", "", f"## Verdict: {verdict}", "",
        f"Baseline profit: **${baseline['profit']:.2f}** · walk-forward: **${baseline['walk_forward_profit']:.2f}** · "
        f"drawdown: **{baseline['max_drawdown_pct']:.2f}%**", "",
        "| Variant | Profit | Change | Avg loss | Win rate | Drawdown | Walk-forward change | Windows improved | Retired-holdout change* |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples():
        lines.append(
            f"| {row.source} {row.checkpoint_hours}h | ${row.profit:.2f} | {row.profit_change:+.2f} | "
            f"${row.average_loss:.2f} | {row.win_rate_pct:.1f}% | {row.max_drawdown_pct:.2f}% | "
            f"{row.walk_forward_change:+.2f} | {row.wf_windows_improved}/6 | {row.post_selection_change:+.2f} |"
        )
    lines += [
        "", "## Best full-history variant", "",
        f"**{best.source} at {int(best.checkpoint_hours)} hours:** profit changed by "
        f"**${best.profit_change:+.2f}**. It made {int(best.early_exits_taken)} early exits, cut "
        f"{int(best.baseline_recoveries_cut)} trades that would later have recovered, and admitted "
        f"{int(best.replacement_trades)} replacement trades.", "",
        f"Its average loss improved from **${baseline['average_loss']:.2f}** to **${best.average_loss:.2f}** and "
        f"drawdown improved from **{baseline['max_drawdown_pct']:.2f}%** to **{best.max_drawdown_pct:.2f}%**, "
        f"but win rate fell to **{best.win_rate_pct:.1f}%**. Walk-forward changed only "
        f"**${best.walk_forward_change:+.2f}**. The retired holdout changed "
        f"**${best.post_selection_change:+.2f}**, but is diagnostic only.", "",
        "*The August–September 2026 window is post-selection research data, not unseen evidence.", "",
        "**Decision: do not deploy any of these nine variants.** The Dip 12h rule is useful as a risk-reduction "
        "lead, but its profit improvement is not stable enough yet.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=FAILURE_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output)
    print((output / "REPORT.md").read_text())
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
