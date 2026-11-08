"""ETH experiment: require stronger price confirmation before a Dip entry.

Only the Dip confirmation changes. Mode C, Pullback, exits, costs, blocked hours,
shared slots and evaluation windows are rebuilt exactly as in the canonical control.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .engine import CandidateTrade, MarketData, ReplayResult, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_confirmation_quality_v1.json"
RULE_LABELS = {
    "current_green": "Current green candle",
    "close_above_zone_midpoint": "Green + close above zone midpoint",
    "close_above_zone_top": "Green + close above zone top",
    "close_above_previous_5m_high": "Green + close above previous 5m high",
}


@dataclass(frozen=True)
class DipSignal:
    origin: int
    confirmation: int
    entry: int


def confirmation_passes(rule_name: str, index: int, open_: np.ndarray, close: np.ndarray,
                        high: np.ndarray, midpoint: float, top: float) -> bool:
    """Frozen definitions for the four confirmation rules."""
    green = close[index] > open_[index]
    if not green:
        return False
    if rule_name == "current_green":
        return True
    if rule_name == "close_above_zone_midpoint":
        return close[index] > midpoint
    if rule_name == "close_above_zone_top":
        return close[index] > top
    if rule_name == "close_above_previous_5m_high":
        return index > 0 and close[index] > high[index - 1]
    raise ValueError(f"Unknown confirmation rule: {rule_name}")


def dip_signals(raw: pd.DataFrame, strategy: dict, rule_name: str) -> tuple[list[DipSignal], dict]:
    """Rebuild deployed Dip episodes and swap only their confirmation predicate."""
    replay, grid = baseline_module.compare.replay, baseline_module.grid
    daily = replay.daily_averages(raw)
    average_n = replay.daily_average_n(raw, strategy["average_days"])
    frame = grid.signal_frame(raw, daily, strategy["minutes"])
    for period in (7, 15, 30):
        frame[period] = np.array([np.nan if value is None else float(value) for value in frame[period]])
    days = frame["open_time"].floor("D")
    average = np.array([
        float(average_n[day]) if average_n.get(day) is not None else np.nan for day in days
    ])
    zone = strategy["zone_pct"] / 100
    high = np.asarray(frame["high"], dtype=float)
    low = np.asarray(frame["low"], dtype=float)
    close = np.asarray(frame["close"], dtype=float)
    open_ = np.asarray(frame["open"], dtype=float)
    a7, a15, a30 = (np.asarray(frame[p], dtype=float) for p in (7, 15, 30))
    with np.errstate(invalid="ignore"):
        lower, upper = average * (1 - zone), average * (1 + zone)
        touched = np.isfinite(average) & (high >= lower * (1 - baseline_module.live.EDGE)) \
                  & (low <= upper * (1 + baseline_module.live.EDGE))
        prior_below = np.zeros(len(high), dtype=bool)
        prior_below[1:] = np.isfinite(average[:-1]) \
                          & (high[:-1] < lower[:-1] * (1 - baseline_module.live.EDGE))
        missing = ~(np.isfinite(a7) & np.isfinite(a15) & np.isfinite(a30))
        bearish = ~missing & (a7 < a15) & (a15 < a30)
    eligible = touched & ~np.r_[False, touched[:-1]] & prior_below & ~(bearish | missing)

    signals: list[DipSignal] = []
    confirmations_before_filters = 0
    trend_rejections = 0
    blocked_hour_rejections = 0
    steps = 30 // strategy["minutes"]
    for origin in np.flatnonzero(eligible):
        confirmed = None
        for offset in range(steps + 1):
            index = int(origin + offset)
            if index >= len(high):
                break
            if confirmation_passes(
                rule_name, index, open_, close, high, float(average[origin]), float(upper[origin])
            ):
                confirmed = index
                break
            # Match the deployed state machine: a qualifying green candle is checked before the episode
            # is cancelled for leaving the touch zone.
            if not touched[index]:
                break
        if confirmed is None:
            continue
        confirmations_before_filters += 1
        if strategy["above_30d"]:
            ceiling = a30[confirmed] * (1 + (strategy["max_above_30d"] or 1e9) / 100)
            if not (close[confirmed] > a30[confirmed] and close[confirmed] <= ceiling):
                trend_rejections += 1
                continue
        entry = int(frame["first_raw"] + (confirmed + 1) * strategy["minutes"])
        if entry >= len(raw) - 1:
            continue
        if strategy["blocked"]:
            hour = pd.Timestamp(raw.open_time.iloc[entry]).hour
            if strategy["blocked"][0] <= hour < strategy["blocked"][1]:
                blocked_hour_rejections += 1
                continue
        signals.append(DipSignal(int(origin), confirmed, entry))
    funnel = {
        "eligible_touch_episodes": int(eligible.sum()),
        "confirmed_before_filters": confirmations_before_filters,
        "trend_rejections": trend_rejections,
        "blocked_hour_rejections": blocked_hour_rejections,
        "candidate_dip_signals": len(signals),
    }
    return signals, funnel


def build_candidates(rule_name: str) -> tuple[MarketData, list[CandidateTrade], dict, dict]:
    """Build a complete three-family ETH candidate book for one Dip confirmation."""
    raw, bullish = baseline_module.compare.load("ETHUSDT")
    strategy = baseline_module.live.load_rule("eth")
    signals, funnel = dip_signals(raw, strategy, rule_name)
    dip_entries = np.asarray([signal.entry for signal in signals], dtype=np.int64)
    episode_by_entry = {
        signal.entry: f"dip-touch:{pd.Timestamp(raw.open_time.iloc[int(signal.origin)]).isoformat()}"
        for signal in signals
    }
    mode_c_entries = [trade["entry"] for trade in baseline_module.compare.mode_c(
        raw, strategy, 120, 12, 2.5, 30, 1.283, 22.0, 3.5
    )]
    pullback_entries = baseline_module.pullback.pullback_entries(
        baseline_module.grid.CLOSE, bullish, 24, 180, baseline_module.grid.TIMES,
        blocked=strategy["blocked"],
    )
    trend_line = pd.Series(baseline_module.grid.CLOSE).ewm(span=16 * 60, adjust=False).mean().to_numpy()
    baseline_module.floor_arm.LINE_FLOOR = trend_line * (1 + baseline_module.floor_arm.COSTS / 100)
    sources = (
        (dip_entries, "dip", baseline_module.modes.DIP_STOP,
         strategy["activation_pct"], strategy["giveback_pct"]),
        (mode_c_entries, "breakout", 3.5, 1.283, 22.0),
        (pullback_entries, "pullback", baseline_module.modes.DIP_STOP,
         strategy["activation_pct"], strategy["giveback_pct"]),
    )
    book = baseline_module.floor_arm.book(
        sources, bullish, trend_line, baseline_module.floor_arm.DEPLOYED_ARM, "buy price", "on arming"
    )
    counters: dict[tuple[str, int], int] = {}
    candidates = []
    for trade in book:
        entry, source = int(trade["entry"]), str(trade["source"])
        key = (source, entry)
        ordinal = counters.get(key, 0)
        counters[key] = ordinal + 1
        setup = episode_by_entry.get(entry) if source == "dip" else None
        identifier = setup or f"{source}:{baseline_module.grid.TIMES[entry].isoformat()}:{ordinal}"
        candidates.append(CandidateTrade(
            entry=entry, exit=int(trade["exit"]), exit_price=float(trade["price"]), source=source,
            exit_code=int(trade["why"]), candidate_id=identifier, setup_episode=setup,
            exit_kind=baseline_module._exit_kind(trade), arm_index=baseline_module._arm_index(trade),
            bullish_entry=bool(bullish[entry]),
        ))
    market = MarketData(
        pd.DatetimeIndex(baseline_module.grid.TIMES), baseline_module.grid.OPEN.copy(),
        baseline_module.grid.CLOSE.copy(),
    )
    windows = dict(baseline_module.research.WINDOWS)
    windows["post_selection_2026_08_09"] = windows.pop("unseen")
    return market, candidates, windows, funnel


def quality(result: ReplayResult, threshold: float) -> dict:
    trades = result.trades
    economic_winners = trades[trades.return_pct > threshold]
    economic_losers = trades[trades.return_pct < -threshold]
    flat = trades[(trades.return_pct >= -threshold) & (trades.return_pct <= threshold)]
    protective = trades[trades.exit_kind == "protective_stop"]
    unarmed = trades[trades.arm_index.isna()]
    return {
        "economic_winners": int(len(economic_winners)),
        "economic_flats": int(len(flat)),
        "economic_losers": int(len(economic_losers)),
        "economic_win_rate_pct": 100 * len(economic_winners) / len(trades) if len(trades) else 0.0,
        "average_economic_win": float(economic_winners.pnl.mean()) if len(economic_winners) else 0.0,
        "average_economic_loss": float(economic_losers.pnl.mean()) if len(economic_losers) else 0.0,
        "protective_stops": int(len(protective)),
        "protective_stop_rate_pct": 100 * len(protective) / len(trades) if len(trades) else 0.0,
        "unarmed_trades": int(len(unarmed)),
        "unarmed_protective_stops": int(len(protective[protective.arm_index.isna()])),
        "arm_rate_pct": 100 * trades.arm_index.notna().sum() / len(trades) if len(trades) else 0.0,
    }


def _removed_winners(baseline: ReplayResult, variant: ReplayResult) -> dict:
    base_dip = baseline.trades[baseline.trades.source == "dip"]
    variant_setups = set(variant.trades.loc[variant.trades.source == "dip", "setup_episode"].dropna())
    removed = base_dip[~base_dip.setup_episode.isin(variant_setups)]
    winners = removed[removed.pnl > 0]
    return {
        "baseline_dip_trades_not_filled": int(len(removed)),
        "profitable_baseline_dip_trades_removed": int(len(winners)),
        "profitable_baseline_dip_pnl_removed": float(winners.pnl.sum()),
    }


def _passed(row: dict, baseline: dict, acceptance: dict) -> bool:
    return bool(
        row["profit_change"] > acceptance["full_profit_change_gt"]
        and row["walk_forward_change"] > acceptance["walk_forward_change_gt"]
        and row["wf_windows_improved"] >= acceptance["minimum_walk_forward_windows_improved"]
        and row["economic_win_rate_pct"] >= baseline["economic_win_rate_pct"]
        and row["average_loss"] >= baseline["average_loss"]
        and row["max_drawdown_pct"] >= baseline["max_drawdown_pct"]
    )


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    threshold = float(experiment["economic_winner_threshold_pct"])
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]

    all_candidates: dict[str, list[CandidateTrade]] = {}
    funnels = {}
    market = windows = None
    for rule_name in experiment["rules"]:
        built_market, candidates, built_windows, funnel = build_candidates(rule_name)
        market, windows = built_market, built_windows
        all_candidates[rule_name] = candidates
        funnels[rule_name] = funnel
    assert market is not None and windows is not None

    results: dict[str, dict[str, ReplayResult]] = {
        rule_name: {
            name: replay_portfolio(candidates, market, *windows[name], portfolio) for name in names
        }
        for rule_name, candidates in all_candidates.items()
    }
    control = results["current_green"]
    _assert_expected(
        control["full"].summary, baseline_config["acceptance"],
        float(baseline_config["acceptance_tolerance"]),
    )
    base_quality = quality(control["full"], threshold)
    baseline = {
        "profit": control["full"].summary["net_profit"],
        "trades": control["full"].summary["trades"],
        "win_rate_pct": control["full"].summary["win_rate_pct"],
        "average_win": control["full"].summary["average_win"],
        "average_loss": control["full"].summary["average_loss"],
        "profit_factor": control["full"].summary["profit_factor"],
        "max_drawdown_pct": control["full"].summary["maximum_drawdown_pct"],
        "walk_forward_profit": sum(control[name].summary["net_profit"] for name in wf_names),
        "post_selection_profit": control["post_selection_2026_08_09"].summary["net_profit"],
        **base_quality,
    }

    rows, window_rows, family_rows, trade_frames = [], [], [], []
    for rule_name in experiment["rules"]:
        full = results[rule_name]["full"]
        q = quality(full, threshold)
        wf_diffs = [results[rule_name][name].summary["net_profit"] - control[name].summary["net_profit"]
                    for name in wf_names]
        row = {
            "variant": rule_name, "label": RULE_LABELS[rule_name],
            "profit": full.summary["net_profit"],
            "profit_change": full.summary["net_profit"] - baseline["profit"],
            "trades": full.summary["trades"], "trade_change": full.summary["trades"] - baseline["trades"],
            "win_rate_pct": full.summary["win_rate_pct"],
            "economic_win_rate_pct": q["economic_win_rate_pct"],
            "average_win": full.summary["average_win"], "average_loss": full.summary["average_loss"],
            "profit_factor": full.summary["profit_factor"],
            "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
            "walk_forward_profit": sum(results[rule_name][name].summary["net_profit"] for name in wf_names),
            "walk_forward_change": sum(wf_diffs),
            "wf_windows_improved": sum(value > 0 for value in wf_diffs),
            "post_selection_change": (
                results[rule_name]["post_selection_2026_08_09"].summary["net_profit"]
                - baseline["post_selection_profit"]
            ),
            **q, **funnels[rule_name], **_removed_winners(control["full"], full),
        }
        row["passed"] = rule_name != "current_green" and _passed(row, baseline, experiment["acceptance"])
        rows.append(row)
        trades = full.trades.copy()
        trades.insert(0, "variant", rule_name)
        trade_frames.append(trades)
        for source, part in full.trades.groupby("source", sort=True):
            winners, losses = part[part.pnl > 0], part[part.pnl <= 0]
            economic = part[part.return_pct > threshold]
            stops = part[part.exit_kind == "protective_stop"]
            family_rows.append({
                "variant": rule_name, "source": source, "trades": len(part),
                "profit": part.pnl.sum(), "win_rate_pct": 100 * len(winners) / len(part),
                "economic_win_rate_pct": 100 * len(economic) / len(part),
                "average_win": winners.pnl.mean() if len(winners) else 0.0,
                "average_loss": losses.pnl.mean() if len(losses) else 0.0,
                "protective_stops": len(stops), "protective_stop_rate_pct": 100 * len(stops) / len(part),
            })
        for name in names:
            current = results[rule_name][name]
            window_rows.append({
                "variant": rule_name, "window": name, "profit": current.summary["net_profit"],
                "profit_change": current.summary["net_profit"] - control[name].summary["net_profit"],
                "trades": current.summary["trades"], "win_rate_pct": current.summary["win_rate_pct"],
                "max_drawdown_pct": current.summary["maximum_drawdown_pct"],
            })

    frame = pd.DataFrame(rows)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.DataFrame(family_rows).to_csv(output / "results_by_entry_family.csv", index=False)
    pd.concat(trade_frames, ignore_index=True).to_csv(output / "variant_trades.csv", index=False)
    pd.DataFrame([{"variant": name, **values} for name, values in funnels.items()]).to_csv(
        output / "confirmation_funnel.csv", index=False
    )
    (output / "summary.json").write_text(json.dumps({
        "baseline": baseline,
        "variants": frame.to_dict(orient="records"),
        "accepted_variants": frame.loc[frame.passed, "variant"].tolist(),
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(baseline, frame))
    return output


def _report(baseline: dict, frame: pd.DataFrame) -> str:
    alternatives = frame[frame.variant != "current_green"].copy()
    passed = alternatives[alternatives.passed]
    verdict = "IMPROVES" if len(passed) else "DOES NOT ROBUSTLY IMPROVE"
    lines = [
        "# ETH stronger Dip-confirmation experiment", "", f"## Verdict: {verdict}", "",
        f"Baseline: **${baseline['profit']:.2f} profit · {baseline['trades']} trades · "
        f"{baseline['economic_win_rate_pct']:.1f}% economic winners · ${baseline['average_loss']:.2f} "
        f"average loss · {baseline['max_drawdown_pct']:.2f}% drawdown**", "",
        "Only Dip confirmation changes. Mode C, Pullback, exits, costs, blocked hours and five shared slots are unchanged.", "",
        "| Confirmation | Profit | Change | Trades | Economic wins | Avg win | Avg loss | Stop rate | Unarmed | Drawdown | WF change | WF improved | Removed profitable Dip trades | Pass |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in frame.itertuples():
        lines.append(
            f"| {row.label} | ${row.profit:.2f} | ${row.profit_change:+.2f} | {row.trades} ({row.trade_change:+d}) | "
            f"{row.economic_win_rate_pct:.1f}% | ${row.average_win:.2f} | ${row.average_loss:.2f} | "
            f"{row.protective_stops}/{row.trades} ({row.protective_stop_rate_pct:.1f}%) | "
            f"{row.unarmed_trades} | {row.max_drawdown_pct:.2f}% | "
            f"${row.walk_forward_change:+.2f} | {row.wf_windows_improved}/6 | "
            f"{row.profitable_baseline_dip_trades_removed} (${row.profitable_baseline_dip_pnl_removed:.2f}) | "
            f"{'YES' if row.passed else 'NO'} |"
        )
    best = alternatives.sort_values("profit_change", ascending=False).iloc[0]
    lines += [
        "", "## Decision", "",
        (f"**Deploy `{passed.iloc[0].variant}` only after forward confirmation.**"
         if len(passed) else "**Keep the live green-candle confirmation unchanged.**"), "",
        f"The best full-history alternative was **{best.label}**, changing profit by **${best.profit_change:+.2f}**, "
        f"economic win rate by **{best.economic_win_rate_pct - baseline['economic_win_rate_pct']:+.1f} points**, "
        f"average loss by **${best.average_loss - baseline['average_loss']:+.2f}**, and walk-forward profit by "
        f"**${best.walk_forward_change:+.2f}** while improving **{int(best.wf_windows_improved)}/6** windows.", "",
        "The August–September 2026 result is diagnostic only; it was not used for acceptance.",
    ]
    return "\n".join(lines) + "\n"


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
