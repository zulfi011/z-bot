"""ETH experiment: replace Mode C's timed confirmation with a breakout-and-retest entry."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .confirmation_quality import quality
from .engine import CandidateTrade, ReplayResult, replay_portfolio
from .pullback_revalidation import _excluded_month_mask
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_mode_c_retest_v1.json"
CONTROL = "current_mode_c"


@dataclass(frozen=True)
class BreakoutSetup:
    breakout_bar: int
    breakout_minute: int
    band_top: float
    band_bottom: float
    setup_id: str


def mode_c_breakouts(raw: pd.DataFrame, chart_minutes: int = 120, zone_bars: int = 12,
                     maximum_zone_pct: float = 2.5) -> list[BreakoutSetup]:
    """Rebuild the exact causal frozen bands used by deployed Mode C."""
    high, low, _open, close, last_minute = baseline_module.compare.v4.bars_for(raw, chart_minutes)
    top = pd.Series(high).rolling(zone_bars).max().to_numpy()
    bottom = pd.Series(low).rolling(zone_bars).min().to_numpy()
    zone_top = np.r_[np.nan, top[:-1]]
    zone_bottom = np.r_[np.nan, bottom[:-1]]
    quiet = (zone_top / zone_bottom - 1) <= maximum_zone_pct / 100
    broke = quiet & (close > zone_top)
    first = broke & ~np.r_[False, broke[:-1]]
    setups = []
    for bar_index in np.flatnonzero(first):
        minute = int(last_minute[bar_index])
        setup_id = f"mode-c-band:{baseline_module.grid.TIMES[minute].isoformat()}"
        setups.append(BreakoutSetup(
            int(bar_index), minute, float(zone_top[bar_index]),
            float(zone_bottom[bar_index]), setup_id,
        ))
    return setups


def current_mode_c_entries(raw: pd.DataFrame, setups: list[BreakoutSetup],
                           confirm_minutes: int = 30) -> np.ndarray:
    """Current timed confirmation, used only as an exact parity check."""
    rule = baseline_module.live.load_rule("eth")
    entries = []
    for setup in setups:
        check = setup.breakout_minute + confirm_minutes
        if check >= len(raw) - 1 or baseline_module.grid.CLOSE[check] <= setup.band_top:
            continue
        entry = check + 1
        hour = baseline_module.grid.TIMES[entry].hour
        if rule["blocked"] and rule["blocked"][0] <= hour < rule["blocked"][1]:
            continue
        entries.append(entry)
    return np.asarray(entries, dtype=np.int64)


def retest_entries(raw: pd.DataFrame, setups: list[BreakoutSetup], tolerance_pct: float,
                   wait_minutes: int = 360, confirmation_minutes: int = 5) -> tuple[np.ndarray, pd.DataFrame]:
    """Find one bullish band-top reclaim per original frozen band, using completed bars only."""
    rule = baseline_module.live.load_rule("eth")
    high, low, open_, close, last_minute = baseline_module.compare.v4.bars_for(raw, confirmation_minutes)
    rows = []
    for setup in setups:
        candidate_bars = np.flatnonzero(
            (last_minute > setup.breakout_minute)
            & (last_minute <= setup.breakout_minute + wait_minutes)
        )
        lower = setup.band_top * (1 - tolerance_pct / 100)
        upper = setup.band_top * (1 + tolerance_pct / 100)
        confirmation = None
        for bar_index in candidate_bars:
            intersects_top_area = low[bar_index] <= upper and high[bar_index] >= lower
            bullish_reclaim = close[bar_index] > open_[bar_index] and close[bar_index] > setup.band_top
            if intersects_top_area and bullish_reclaim:
                confirmation = int(bar_index)
                break
        if confirmation is None:
            continue
        entry = int(last_minute[confirmation]) + 1
        if entry >= len(raw) - 1:
            continue
        hour = baseline_module.grid.TIMES[entry].hour
        blocked = bool(rule["blocked"] and rule["blocked"][0] <= hour < rule["blocked"][1])
        rows.append({
            "setup_id": setup.setup_id,
            "breakout_minute": setup.breakout_minute,
            "breakout_time": baseline_module.grid.TIMES[setup.breakout_minute],
            "band_top": setup.band_top,
            "band_bottom": setup.band_bottom,
            "confirmation_minute": int(last_minute[confirmation]),
            "confirmation_time": baseline_module.grid.TIMES[int(last_minute[confirmation])],
            "entry": entry,
            "entry_time": baseline_module.grid.TIMES[entry],
            "delay_minutes": entry - setup.breakout_minute - 1,
            "entry_vs_band_top_pct": 100 * (baseline_module.grid.OPEN[entry] / setup.band_top - 1),
            "blocked_hour": blocked,
        })
    diagnostics = pd.DataFrame(rows)
    allowed = diagnostics[~diagnostics.blocked_hour] if len(diagnostics) else diagnostics
    return allowed.entry.to_numpy(dtype=np.int64), diagnostics


def build_retest_candidates(raw: pd.DataFrame, bullish: np.ndarray, setups: list[BreakoutSetup],
                            tolerance_pct: float, wait_minutes: int,
                            confirmation_minutes: int) -> tuple[list[CandidateTrade], pd.DataFrame]:
    entries, diagnostics = retest_entries(
        raw, setups, tolerance_pct, wait_minutes, confirmation_minutes,
    )
    usable = diagnostics[~diagnostics.blocked_hour] if len(diagnostics) else diagnostics
    if usable.entry.duplicated().any():
        raise AssertionError("Multiple frozen Mode C bands produced the same retest entry minute")
    setup_by_entry = dict(zip(usable.entry.astype(int), usable.setup_id))
    line = pd.Series(baseline_module.grid.CLOSE).ewm(span=16 * 60, adjust=False).mean().to_numpy()
    baseline_module.floor_arm.LINE_FLOOR = line * (1 + baseline_module.floor_arm.COSTS / 100)
    book = baseline_module.floor_arm.book(
        ((entries, "breakout", 3.5, 1.283, 22.0),),
        bullish, line, baseline_module.floor_arm.DEPLOYED_ARM, "buy price", "on arming",
    )
    candidates = []
    for trade in book:
        entry = int(trade["entry"])
        setup_id = setup_by_entry[entry]
        candidates.append(CandidateTrade(
            entry=entry, exit=int(trade["exit"]), exit_price=float(trade["price"]),
            source="breakout", exit_code=int(trade["why"]),
            candidate_id=f"retest-{tolerance_pct:.2f}:{setup_id}", setup_episode=setup_id,
            exit_kind=baseline_module._exit_kind(trade), arm_index=baseline_module._arm_index(trade),
            bullish_entry=bool(bullish[entry]),
        ))
    return candidates, diagnostics


def _mode_c_metrics(result: ReplayResult) -> dict:
    trades = result.trades[result.trades.source == "breakout"]
    wins, losses = trades[trades.pnl > 0], trades[trades.pnl <= 0]
    return {
        "mode_c_trades": len(trades),
        "mode_c_profit": float(trades.pnl.sum()),
        "mode_c_win_rate_pct": 100 * len(wins) / len(trades) if len(trades) else 0.0,
        "mode_c_average_win": float(wins.pnl.mean()) if len(wins) else 0.0,
        "mode_c_average_loss": float(losses.pnl.mean()) if len(losses) else 0.0,
        "mode_c_protective_stops": int((trades.exit_kind == "protective_stop").sum()),
    }


def _metrics(result: ReplayResult, excluded_months: list[str], threshold: float) -> dict:
    trades = result.trades
    ordinary = trades[~_excluded_month_mask(trades, excluded_months)] if len(trades) else trades
    return {
        "profit": float(result.summary["net_profit"]),
        "trades": int(result.summary["trades"]),
        "headline_win_rate_pct": float(result.summary["win_rate_pct"]),
        "average_win": float(result.summary["average_win"]),
        "average_loss": float(result.summary["average_loss"]),
        "profit_factor": float(result.summary["profit_factor"]),
        "max_drawdown_pct": float(result.summary["maximum_drawdown_pct"]),
        "ordinary_profit": float(ordinary.pnl.sum()),
        "ordinary_trades": len(ordinary),
        **quality(result, threshold),
        **_mode_c_metrics(result),
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
    market, canonical, windows = baseline_module.build_baseline()
    raw, bullish = baseline_module.compare.load("ETHUSDT")
    setups = mode_c_breakouts(
        raw, int(experiment["chart_minutes"]), int(experiment["zone_bars"]),
        float(experiment["maximum_zone_pct"]),
    )
    current_entries = current_mode_c_entries(raw, setups)
    canonical_entries = np.asarray([c.entry for c in canonical if c.source == "breakout"], dtype=np.int64)
    if not np.array_equal(current_entries, canonical_entries):
        raise AssertionError("Mode C breakout reconstruction does not match the canonical candidate book")

    core = [candidate for candidate in canonical if candidate.source != "breakout"]
    priority = {"dip": 0, "breakout": 1, "pullback": 2}
    books = {CONTROL: canonical}
    diagnostics = []
    for tolerance in experiment["near_band_top_tolerances_pct"]:
        label = f"retest_{float(tolerance):.2f}pct"
        retests, detail = build_retest_candidates(
            raw, bullish, setups, float(tolerance), int(experiment["retest_wait_minutes"]),
            int(experiment["confirmation_candle_minutes"]),
        )
        books[label] = sorted(
            [*core, *retests], key=lambda c: (c.entry, priority[c.source], c.candidate_id),
        )
        diagnostics.append(detail.assign(variant=label))

    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    results = {
        label: {name: replay_portfolio(book, market, *windows[name], portfolio) for name in names}
        for label, book in books.items()
    }
    _assert_expected(
        results[CONTROL]["full"].summary, baseline_config["acceptance"],
        float(baseline_config["acceptance_tolerance"]),
    )
    threshold = float(experiment["economic_winner_threshold_pct"])
    excluded = experiment["excluded_entry_months"]
    control = _metrics(results[CONTROL]["full"], excluded, threshold)
    rows, windows_rows, trade_rows = [], [], []
    for label, by_window in results.items():
        metrics = _metrics(by_window["full"], excluded, threshold)
        changes = [by_window[name].summary["net_profit"] - results[CONTROL][name].summary["net_profit"]
                   for name in wf_names]
        row = {
            "variant": label,
            "candidate_mode_c_entries": sum(c.source == "breakout" for c in books[label]),
            **metrics,
            "profit_change": metrics["profit"] - control["profit"],
            "trade_change": metrics["trades"] - control["trades"],
            "ordinary_profit_change": metrics["ordinary_profit"] - control["ordinary_profit"],
            "walk_forward_profit": sum(by_window[name].summary["net_profit"] for name in wf_names),
            "walk_forward_change": sum(changes),
            "wf_windows_improved": sum(change > 0 for change in changes),
        }
        row["accepted"] = label != CONTROL and _passes(row, control, experiment["acceptance"])
        rows.append(row)
        trade_rows.append(by_window["full"].trades.assign(variant=label))
        for name in names:
            windows_rows.append({
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
    pd.DataFrame(windows_rows).to_csv(output / "window_results.csv", index=False)
    pd.concat(trade_rows, ignore_index=True).to_csv(output / "variant_trades.csv", index=False)
    pd.concat(diagnostics, ignore_index=True).to_csv(output / "retest_diagnostics.csv", index=False)
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    (output / "summary.json").write_text(json.dumps({
        "control": frame[frame.variant == CONTROL].iloc[0].to_dict(),
        "accepted_variants": accepted,
        "decision": "accept" if accepted else "reject_all",
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(frame))
    return output


def _report(frame: pd.DataFrame) -> str:
    lines = []
    for row in frame.itertuples():
        decision = "CONTROL" if row.variant == CONTROL else ("PASS" if row.accepted else "FAIL")
        label = "Current Mode C" if row.variant == CONTROL else row.variant.replace("retest_", "Retest ±").replace("pct", "%")
        lines.append(
            f"| {label} | ${row.profit:.2f} | ${row.profit_change:+.2f} | {row.trades} ({row.trade_change:+d}) | "
            f"{row.mode_c_trades} | ${row.mode_c_profit:.2f} | {row.economic_win_rate_pct:.1f}% | "
            f"${row.average_economic_loss:.2f} | {row.max_drawdown_pct:.2f}% | "
            f"${row.ordinary_profit_change:+.2f} | ${row.walk_forward_change:+.2f} | "
            f"{row.wf_windows_improved}/6 | {decision} |"
        )
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    decision = f"Advance {', '.join(accepted)} to forward testing; do not deploy yet." if accepted else (
        "Reject all three retest entries; keep current Mode C unchanged."
    )
    return f"""# ETH Mode C breakout-and-retest experiment

## Result

**{decision}**

| Rule | Profit | vs base | Trades | Mode C fills | Mode C profit | Economic win rate | Avg economic loss | Drawdown | Ex-Apr/May change | WF change | WF improved | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(lines)}

Each retest rule uses the original frozen Mode C band, waits at most six hours, permits one entry per band, and buys after a completed bullish five-minute reclaim. All exits and non-Mode-C rules are unchanged.
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
