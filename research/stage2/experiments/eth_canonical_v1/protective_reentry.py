"""ETH experiment: one strongly confirmed re-entry after a Dip protective-stop loss."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .confirmation_quality import dip_signals, quality
from .engine import CandidateTrade, ReplayResult, replay_portfolio
from .pullback_revalidation import _excluded_month_mask
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_protective_reentry_v1.json"
CONTROL = "no_reentry_control"


@dataclass(frozen=True)
class DipEpisode:
    parent_id: str
    parent_entry: int
    stop_index: int
    zone_top: float
    setup_id: str


def strong_reentry_confirmation(open_price: float, close_price: float, zone_top: float,
                                previous_high: float) -> bool:
    return bool(close_price > open_price and close_price > zone_top and close_price > previous_high)


def _dip_zone_tops(raw: pd.DataFrame, strategy: dict) -> dict[int, tuple[float, str]]:
    """Map each deployed Dip entry to its original frozen touch-zone top."""
    signals, _ = dip_signals(raw, strategy, "current_green")
    replay, grid = baseline_module.compare.replay, baseline_module.grid
    daily = replay.daily_averages(raw)
    average_n = replay.daily_average_n(raw, strategy["average_days"])
    frame = grid.signal_frame(raw, daily, strategy["minutes"])
    days = frame["open_time"].floor("D")
    average = np.asarray([
        float(average_n[day]) if average_n.get(day) is not None else np.nan for day in days
    ])
    factor = 1 + float(strategy["zone_pct"]) / 100
    return {
        signal.entry: (
            float(average[signal.origin] * factor),
            f"dip-touch:{pd.Timestamp(frame['open_time'][signal.origin]).isoformat()}",
        )
        for signal in signals
    }


def _strong_bearish_minutes(raw: pd.DataFrame) -> np.ndarray:
    daily = baseline_module.compare.replay.daily_averages(raw)
    days = raw.open_time.dt.floor("D")
    values = np.asarray([
        [np.nan if value is None else float(value) for value in daily.get(day, (None, None, None))]
        for day in days
    ])
    a7, a15, a30 = values[:, 0], values[:, 1], values[:, 2]
    return np.isfinite(a7) & np.isfinite(a15) & np.isfinite(a30) & (a7 < a15) & (a15 < a30)


def dip_stop_episodes(raw: pd.DataFrame, candidates: list[CandidateTrade]) -> list[DipEpisode]:
    strategy = baseline_module.live.load_rule("eth")
    zones = _dip_zone_tops(raw, strategy)
    episodes = []
    for candidate in candidates:
        if candidate.source != "dip" or candidate.exit_kind != "protective_stop":
            continue
        if candidate.entry not in zones:
            raise AssertionError("Canonical Dip candidate is missing its frozen touch-zone metadata")
        top, setup_id = zones[candidate.entry]
        episodes.append(DipEpisode(
            candidate.candidate_id, candidate.entry, candidate.exit, top, setup_id,
        ))
    return episodes


def reentry_signals(raw: pd.DataFrame, episodes: list[DipEpisode], window_hours: int) -> pd.DataFrame:
    """Return the first strong post-stop reclaim in each original Dip episode."""
    rule = baseline_module.live.load_rule("eth")
    bearish = _strong_bearish_minutes(raw)
    high, _low, open_, close, last_minute = baseline_module.compare.v4.bars_for(raw, 5)
    rows = []
    for episode in episodes:
        bars = np.flatnonzero(
            (last_minute > episode.stop_index)
            & (last_minute <= episode.stop_index + window_hours * 60)
        )
        confirmation = None
        for bar_index in bars:
            if bar_index == 0:
                continue
            if strong_reentry_confirmation(
                float(open_[bar_index]), float(close[bar_index]), episode.zone_top,
                float(high[bar_index - 1]),
            ):
                confirmation = int(bar_index)
                break
        if confirmation is None:
            continue
        confirm_minute = int(last_minute[confirmation])
        entry = confirm_minute + 1
        if entry >= len(raw) - 1:
            continue
        hour = baseline_module.grid.TIMES[entry].hour
        blocked = bool(rule["blocked"] and rule["blocked"][0] <= hour < rule["blocked"][1])
        rows.append({
            "parent_id": episode.parent_id,
            "setup_id": episode.setup_id,
            "parent_entry": episode.parent_entry,
            "stop_index": episode.stop_index,
            "stop_time": baseline_module.grid.TIMES[episode.stop_index],
            "zone_top": episode.zone_top,
            "confirmation_index": confirm_minute,
            "confirmation_time": baseline_module.grid.TIMES[confirm_minute],
            "entry": entry,
            "entry_time": baseline_module.grid.TIMES[entry],
            "minutes_after_stop": entry - episode.stop_index,
            "strong_bearish": bool(bearish[confirm_minute]),
            "blocked_hour": blocked,
            "eligible": not bearish[confirm_minute] and not blocked,
        })
    return pd.DataFrame(rows)


def build_reentry_candidates(raw: pd.DataFrame, bullish: np.ndarray, episodes: list[DipEpisode],
                             window_hours: int) -> tuple[list[CandidateTrade], dict[str, str], pd.DataFrame]:
    signals = reentry_signals(raw, episodes, window_hours)
    eligible = signals[signals.eligible].sort_values(["entry", "parent_id"]) if len(signals) else signals
    line = pd.Series(baseline_module.grid.CLOSE).ewm(span=16 * 60, adjust=False).mean().to_numpy()
    baseline_module.floor_arm.LINE_FLOOR = line * (1 + baseline_module.floor_arm.COSTS / 100)
    candidates, parents = [], {}
    for row in eligible.itertuples():
        trade = baseline_module.floor_arm.book(
            ((np.asarray([row.entry], dtype=np.int64), "dip_reentry", baseline_module.modes.DIP_STOP,
              baseline_module.live.load_rule("eth")["activation_pct"],
              baseline_module.live.load_rule("eth")["giveback_pct"]),),
            bullish, line, baseline_module.floor_arm.DEPLOYED_ARM, "buy price", "on arming",
        )[0]
        candidate_id = f"dip-reentry-{window_hours}h:{row.parent_id}"
        candidates.append(CandidateTrade(
            entry=int(trade["entry"]), exit=int(trade["exit"]), exit_price=float(trade["price"]),
            source="dip_reentry", exit_code=int(trade["why"]), candidate_id=candidate_id,
            setup_episode=str(row.setup_id), exit_kind=baseline_module._exit_kind(trade),
            arm_index=baseline_module._arm_index(trade), bullish_entry=bool(bullish[int(trade["entry"])]),
        ))
        parents[candidate_id] = str(row.parent_id)
    return candidates, parents, signals


def parent_stop_policy(parent_by_reentry: dict[str, str]):
    """A re-entry exists only when its exact parent was filled and truly stopped in this replay."""
    def policy(candidate: CandidateTrade, filled: list[dict], _open_lots: list[dict]) -> str | None:
        parent_id = parent_by_reentry.get(candidate.candidate_id)
        if parent_id is None:
            return None
        valid_parent = any(
            lot["candidate_id"] == parent_id
            and lot["exit_kind"] == "protective_stop"
            and not lot["endpoint_closed"]
            and lot["exit_index"] <= candidate.entry
            for lot in filled
        )
        return None if valid_parent else "reentry_parent_not_filled_and_stopped"
    return policy


def _reentry_metrics(result: ReplayResult, parent_by_reentry: dict[str, str]) -> dict:
    reentries = result.trades[result.trades.source == "dip_reentry"]
    parents = result.trades.set_index("candidate_id", drop=False)
    paired, recovered = [], 0
    for row in reentries.itertuples():
        parent_id = parent_by_reentry[row.candidate_id]
        if parent_id in parents.index:
            combined = float(parents.loc[parent_id].pnl + row.pnl)
            paired.append(combined)
            recovered += combined > 0
    return {
        "reentry_fills": len(reentries),
        "reentry_profit": float(reentries.pnl.sum()),
        "reentry_win_rate_pct": 100 * float((reentries.pnl > 0).mean()) if len(reentries) else 0.0,
        "reentry_average_pnl": float(reentries.pnl.mean()) if len(reentries) else 0.0,
        "reentry_protective_stops": int((reentries.exit_kind == "protective_stop").sum()),
        "parent_plus_reentry_profit": float(sum(paired)),
        "parent_losses_recovered": recovered,
    }


def _metrics(result: ReplayResult, parent_by_reentry: dict[str, str], excluded: list[str],
             threshold: float) -> dict:
    trades = result.trades
    ordinary = trades[~_excluded_month_mask(trades, excluded)] if len(trades) else trades
    return {
        "profit": float(result.summary["net_profit"]),
        "trades": int(result.summary["trades"]),
        "headline_win_rate_pct": float(result.summary["win_rate_pct"]),
        "average_win": float(result.summary["average_win"]),
        "average_loss": float(result.summary["average_loss"]),
        "profit_factor": float(result.summary["profit_factor"]),
        "max_drawdown_pct": float(result.summary["maximum_drawdown_pct"]),
        "ordinary_profit": float(ordinary.pnl.sum()),
        **quality(result, threshold),
        **_reentry_metrics(result, parent_by_reentry),
    }


def _passes(row: dict, control: dict, acceptance: dict) -> bool:
    return bool(
        row["profit_change"] > acceptance["full_profit_change_gt"]
        and row["ordinary_profit_change"] > acceptance["ordinary_profit_change_gt"]
        and row["walk_forward_change"] > acceptance["walk_forward_change_gt"]
        and row["wf_windows_improved"] >= acceptance["minimum_walk_forward_windows_improved"]
        and row["economic_win_rate_pct"] >= control["economic_win_rate_pct"]
        and row["average_loss"] >= control["average_loss"]
        and row["max_drawdown_pct"] >= control["max_drawdown_pct"]
    )


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    market, canonical, windows = baseline_module.build_baseline()
    raw, bullish = baseline_module.compare.load("ETHUSDT")
    episodes = dip_stop_episodes(raw, canonical)
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    books = {CONTROL: (canonical, {}, None)}
    signal_frames = []
    for hours in experiment["reentry_windows_hours"]:
        label = f"reentry_{int(hours)}h"
        reentries, parents, signals = build_reentry_candidates(raw, bullish, episodes, int(hours))
        books[label] = ([*canonical, *reentries], parents, parent_stop_policy(parents))
        signal_frames.append(signals.assign(variant=label))

    results = {
        label: {name: replay_portfolio(book, market, *windows[name], portfolio, policy)
                for name in names}
        for label, (book, _parents, policy) in books.items()
    }
    _assert_expected(
        results[CONTROL]["full"].summary, baseline_config["acceptance"],
        float(baseline_config["acceptance_tolerance"]),
    )
    excluded = experiment["excluded_entry_months"]
    threshold = float(experiment["economic_winner_threshold_pct"])
    control = _metrics(results[CONTROL]["full"], {}, excluded, threshold)
    control_ids = set(results[CONTROL]["full"].trades.candidate_id)
    rows, window_rows, trade_rows, blocked_rows = [], [], [], []
    for label, by_window in results.items():
        parents = books[label][1]
        metrics = _metrics(by_window["full"], parents, excluded, threshold)
        changes = [by_window[name].summary["net_profit"] - results[CONTROL][name].summary["net_profit"]
                   for name in wf_names]
        variant_ids = set(by_window["full"].trades.candidate_id)
        row = {
            "variant": label,
            "potential_reentries": len(parents),
            **metrics,
            "profit_change": metrics["profit"] - control["profit"],
            "trade_change": metrics["trades"] - control["trades"],
            "ordinary_profit_change": metrics["ordinary_profit"] - control["ordinary_profit"],
            "walk_forward_profit": sum(by_window[name].summary["net_profit"] for name in wf_names),
            "walk_forward_change": sum(changes),
            "wf_windows_improved": sum(change > 0 for change in changes),
            "baseline_fills_displaced": len(control_ids - variant_ids),
            "additional_fills": len(variant_ids - control_ids),
        }
        row["accepted"] = label != CONTROL and _passes(row, control, experiment["acceptance"])
        rows.append(row)
        trade_rows.append(by_window["full"].trades.assign(variant=label))
        if len(by_window["full"].blocked_signals):
            blocked_rows.append(by_window["full"].blocked_signals.assign(variant=label))
        for name in names:
            window_rows.append({
                "variant": label, "window": name,
                "profit": by_window[name].summary["net_profit"],
                "control_profit": results[CONTROL][name].summary["net_profit"],
                "profit_change": by_window[name].summary["net_profit"]
                                 - results[CONTROL][name].summary["net_profit"],
            })

    frame = pd.DataFrame(rows)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "variant_results.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.concat(trade_rows, ignore_index=True).to_csv(output / "variant_trades.csv", index=False)
    pd.concat(signal_frames, ignore_index=True).to_csv(output / "reentry_signals.csv", index=False)
    (pd.concat(blocked_rows, ignore_index=True) if blocked_rows else pd.DataFrame()).to_csv(
        output / "blocked_signals.csv", index=False,
    )
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    (output / "summary.json").write_text(json.dumps({
        "control": frame[frame.variant == CONTROL].iloc[0].to_dict(),
        "accepted_variants": accepted,
        "decision": "accept" if accepted else "reject_all",
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(frame))
    return output


def _report(frame: pd.DataFrame) -> str:
    labels = {CONTROL: "No re-entry control", "reentry_24h": "One re-entry within 24h",
              "reentry_48h": "One re-entry within 48h"}
    rows = []
    for row in frame.itertuples():
        decision = "CONTROL" if row.variant == CONTROL else ("PASS" if row.accepted else "FAIL")
        rows.append(
            f"| {labels[row.variant]} | ${row.profit:.2f} | ${row.profit_change:+.2f} | "
            f"{row.trades} ({row.trade_change:+d}) | {row.economic_win_rate_pct:.1f}% | "
            f"${row.average_win:.2f} | ${row.average_loss:.2f} | {row.max_drawdown_pct:.2f}% | "
            f"{row.reentry_fills} | ${row.reentry_profit:.2f} | {row.reentry_protective_stops} | "
            f"${row.ordinary_profit_change:+.2f} | ${row.walk_forward_change:+.2f} | "
            f"{row.wf_windows_improved}/6 | {decision} |"
        )
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    decision = f"Advance {', '.join(accepted)} to untouched forward testing; do not deploy yet." if accepted else (
        "Reject both re-entry windows; keep the current no-re-entry rule."
    )
    return f"""# ETH Dip protective-stop re-entry experiment

## Result

**{decision}**

| Rule | Profit | vs base | Trades | Economic win rate | Avg win | Avg loss | Drawdown | Re-entry fills | Re-entry profit | Re-entry stops | Ex-Apr/May change | WF change | WF improved | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(rows)}

Only Dip protective-stop episodes can re-enter. Each episode gets at most one attempt after a bullish five-minute close above both its original frozen zone top and the prior five-minute high. The parent must have been actually filled and stopped in that replay.
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
