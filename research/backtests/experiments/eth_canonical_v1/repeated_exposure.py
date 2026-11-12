"""Experiment 2: limit repeated ETH exposure to the same setup or market episode."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .engine import CandidateTrade, PortfolioConfig, ReplayResult, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config

EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_repeated_exposure_v1.json"


def _mode_c_setup_ids(raw, rule) -> dict[int, str]:
    """Group shifted, overlapping Mode C bands into one causal setup episode."""
    grid, v4 = baseline_module.grid, baseline_module.compare.v4
    high, low, _, close, last_minute = v4.bars_for(raw, 120)
    top = pd.Series(high).rolling(12).max().to_numpy()
    bottom = pd.Series(low).rolling(12).min().to_numpy()
    zone_top, zone_bottom = np.r_[np.nan, top[:-1]], np.r_[np.nan, bottom[:-1]]
    quiet = (zone_top / zone_bottom - 1) <= 2.5 / 100
    broke = quiet & (close > zone_top)
    breakout_bars = np.flatnonzero(broke & ~np.r_[False, broke[:-1]])
    checks = last_minute[breakout_bars] + 30
    valid = checks < len(raw) - 1
    breakout_bars, checks = breakout_bars[valid], checks[valid]
    held = grid.CLOSE[checks] > zone_top[breakout_bars]
    breakout_bars, checks = breakout_bars[held], checks[held]
    entries = (checks + 1).astype(np.int64)
    if rule["blocked"] and len(entries):
        hours = grid.TIMES[entries].hour
        keep = ~((hours >= rule["blocked"][0]) & (hours < rule["blocked"][1]))
        breakout_bars, entries = breakout_bars[keep], entries[keep]

    episodes, prior_breakout, current_id = {}, None, None
    for breakout_bar, entry in zip(breakout_bars, entries, strict=True):
        zone_start = int(breakout_bar) - 12
        if prior_breakout is None or zone_start > prior_breakout:
            current_id = f"breakout-band:{grid.TIMES[int(entry)].isoformat()}"
        episodes[int(entry)] = str(current_id)
        prior_breakout = int(breakout_bar)
    return episodes


def assign_episodes(candidates: list[CandidateTrade], market, config: dict) -> list[CandidateTrade]:
    """Attach native setup IDs and broader causal cross-family market IDs."""
    raw = baseline_module.compare.load("ETHUSDT")[0]
    rule = baseline_module.live.load_rule("eth")
    mode_c = _mode_c_setup_ids(raw, rule)
    setup_annotated = []
    for candidate in candidates:
        setup = (mode_c[candidate.entry] if candidate.source == "breakout"
                 else f"{candidate.source}-setup:{market.times[candidate.entry].isoformat()}")
        setup_annotated.append(replace(candidate, setup_episode=setup))

    max_minutes = int(config["market_episode"]["maximum_gap_minutes"])
    max_price = float(config["market_episode"]["maximum_anchor_distance_pct"]) / 100
    output, episode_number = [], 0
    last_entry, anchor_price, episode_id = None, None, None
    for candidate in sorted(setup_annotated, key=lambda item: (item.entry, item.candidate_id)):
        price = float(market.open[candidate.entry])
        new_episode = (
            last_entry is None or candidate.entry - last_entry > max_minutes
            or abs(price / anchor_price - 1) > max_price
        )
        if new_episode:
            episode_number += 1
            anchor_price = price
            episode_id = f"eth-market-{episode_number:04d}:{market.times[candidate.entry].isoformat()}"
        output.append(replace(candidate, market_episode=episode_id))
        last_entry = candidate.entry
    # Restore the exact stable order used by the frozen baseline.
    order = {candidate.candidate_id: index for index, candidate in enumerate(candidates)}
    return sorted(output, key=lambda candidate: order[candidate.candidate_id])


def cap_policy(field: str, maximum: int):
    def policy(candidate: CandidateTrade, filled: list[dict], _open_lots: list[dict]) -> str | None:
        episode = getattr(candidate, field)
        used = sum(lot[field] == episode for lot in filled)
        return f"exposure_{field}_cap_{maximum}" if used >= maximum else None
    return policy


def family_stop_cooldown(minutes: int):
    def policy(candidate: CandidateTrade, filled: list[dict], _open_lots: list[dict]) -> str | None:
        prior = [lot for lot in filled if lot["source"] == candidate.source
                 and lot["exit_kind"] == "protective_stop" and lot["exit_index"] <= candidate.entry]
        if prior and candidate.entry - max(lot["exit_index"] for lot in prior) < minutes:
            return f"exposure_family_stop_cooldown_{minutes}m"
        return None
    return policy


def correlated_stop_cooldown(minutes: int, required_stops: int = 2):
    def policy(candidate: CandidateTrade, filled: list[dict], _open_lots: list[dict]) -> str | None:
        by_episode: dict[str, list[int]] = defaultdict(list)
        for lot in filled:
            if lot["exit_kind"] == "protective_stop" and lot["exit_index"] <= candidate.entry:
                by_episode[lot["market_episode"]].append(lot["exit_index"])
        triggers = [max(exits) for exits in by_episode.values() if len(exits) >= required_stops]
        if triggers and candidate.entry - max(triggers) < minutes:
            return f"exposure_correlated_{required_stops}_stop_cooldown_{minutes}m"
        return None
    return policy


def _variants(config: dict):
    cooldown = int(config["cooldown_hours"]) * 60
    return {
        "setup_max_1": cap_policy("setup_episode", 1),
        "setup_max_2": cap_policy("setup_episode", 2),
        "market_max_1": cap_policy("market_episode", 1),
        "market_max_2": cap_policy("market_episode", 2),
        "family_stop_cooldown_6h": family_stop_cooldown(cooldown),
        "two_correlated_stops_cooldown_6h": correlated_stop_cooldown(cooldown, 2),
    }


def _episode_metrics(result: ReplayResult) -> dict:
    ledger = result.trades
    if ledger.empty:
        return {"worst_market_episode_pnl": 0.0, "worst_setup_episode_pnl": 0.0,
                "maximum_fills_one_market_episode": 0}
    market = ledger.groupby("market_episode").pnl.agg(["sum", "size"])
    setup = ledger.groupby("setup_episode").pnl.sum()
    return {
        "worst_market_episode_pnl": float(market["sum"].min()),
        "worst_setup_episode_pnl": float(setup.min()),
        "maximum_fills_one_market_episode": int(market["size"].max()),
    }


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio: PortfolioConfig = _portfolio_config(baseline_config)
    market, plain_candidates, windows = baseline_module.build_baseline()
    candidates = assign_episodes(plain_candidates, market, experiment)
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    baseline = {name: replay_portfolio(candidates, market, *windows[name], portfolio) for name in names}
    baseline_full = baseline["full"]

    rows, window_rows, block_rows = [], [], []
    for label, policy in _variants(experiment).items():
        results = {name: replay_portfolio(candidates, market, *windows[name], portfolio, policy) for name in names}
        full = results["full"]
        wf_changes = [results[name].summary["net_profit"] - baseline[name].summary["net_profit"]
                      for name in wf_names]
        policy_blocks = full.blocked_signals[full.blocked_signals.reason.str.startswith("exposure_", na=False)]
        baseline_ids = set(baseline_full.trades.candidate_id)
        lost_baseline = baseline_full.trades[
            baseline_full.trades.candidate_id.isin(set(policy_blocks.candidate_id) & baseline_ids)
        ]
        row = {
            "variant": label, "profit": full.summary["net_profit"],
            "profit_change": full.summary["net_profit"] - baseline_full.summary["net_profit"],
            "trades": full.summary["trades"], "trade_change": full.summary["trades"] - baseline_full.summary["trades"],
            "win_rate_pct": full.summary["win_rate_pct"], "average_win": full.summary["average_win"],
            "average_loss": full.summary["average_loss"], "profit_factor": full.summary["profit_factor"],
            "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
            "walk_forward_profit": sum(results[name].summary["net_profit"] for name in wf_names),
            "walk_forward_change": sum(wf_changes),
            "wf_windows_improved": sum(change > 0 for change in wf_changes),
            "post_selection_profit": results["post_selection_2026_08_09"].summary["net_profit"],
            "post_selection_change": (results["post_selection_2026_08_09"].summary["net_profit"]
                                      - baseline["post_selection_2026_08_09"].summary["net_profit"]),
            "policy_blocks": len(policy_blocks),
            "baseline_winners_blocked": int((lost_baseline.pnl > 0).sum()),
            "baseline_winner_profit_blocked": float(lost_baseline[lost_baseline.pnl > 0].pnl.sum()),
            **_episode_metrics(full),
        }
        rows.append(row)
        if len(policy_blocks):
            block_rows.append(policy_blocks.assign(variant=label))
        for name in names:
            window_rows.append({
                "variant": label, "window": name, "profit": results[name].summary["net_profit"],
                "baseline_profit": baseline[name].summary["net_profit"],
                "profit_change": results[name].summary["net_profit"] - baseline[name].summary["net_profit"],
                "trades": results[name].summary["trades"],
                "max_drawdown_pct": results[name].summary["maximum_drawdown_pct"],
            })

    frame = pd.DataFrame(rows).sort_values(["walk_forward_change", "profit_change"], ascending=False)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    blocks = pd.concat(block_rows, ignore_index=True) if block_rows else pd.DataFrame()
    blocks.to_csv(output / "policy_blocked_signals.csv", index=False)
    episode_map = pd.DataFrame([{
        "candidate_id": candidate.candidate_id, "source": candidate.source,
        "entry_time": market.times[candidate.entry], "setup_episode": candidate.setup_episode,
        "market_episode": candidate.market_episode, "exit_kind": candidate.exit_kind,
    } for candidate in candidates])
    episode_map.to_csv(output / "candidate_episode_map.csv", index=False)
    baseline_summary = {
        "profit": baseline_full.summary["net_profit"], "trades": baseline_full.summary["trades"],
        "win_rate_pct": baseline_full.summary["win_rate_pct"],
        "average_loss": baseline_full.summary["average_loss"],
        "max_drawdown_pct": baseline_full.summary["maximum_drawdown_pct"],
        "walk_forward_profit": sum(baseline[name].summary["net_profit"] for name in wf_names),
        "post_selection_profit": baseline["post_selection_2026_08_09"].summary["net_profit"],
        **_episode_metrics(baseline_full),
    }
    (output / "summary.json").write_text(json.dumps({
        "baseline": baseline_summary, "best_walk_forward": frame.iloc[0].to_dict(),
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(baseline_summary, frame))
    return output


def _report(baseline: dict, frame: pd.DataFrame) -> str:
    best = frame.iloc[0]
    robust = bool(best.profit_change > 0 and best.walk_forward_change > 0
                  and best.wf_windows_improved >= 4
                  and best.max_drawdown_pct >= baseline["max_drawdown_pct"])
    verdict = "IMPROVED" if robust else "DOES NOT ROBUSTLY IMPROVE"
    lines = [
        "# ETH repeated-exposure experiment", "", f"## Verdict: {verdict}", "",
        f"Baseline: **${baseline['profit']:.2f}** profit · **{baseline['trades']}** trades · "
        f"**{baseline['max_drawdown_pct']:.2f}%** drawdown · **${baseline['walk_forward_profit']:.2f}** walk-forward", "",
        "| Variant | Profit change | Trades | Win rate | Avg loss | Drawdown | WF change | Windows improved | Retired-holdout change* | Blocks |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples():
        lines.append(
            f"| {row.variant} | {row.profit_change:+.2f} | {row.trades} ({row.trade_change:+d}) | "
            f"{row.win_rate_pct:.1f}% | ${row.average_loss:.2f} | {row.max_drawdown_pct:.2f}% | "
            f"{row.walk_forward_change:+.2f} | {row.wf_windows_improved}/6 | {row.post_selection_change:+.2f} | "
            f"{row.policy_blocks} |"
        )
    lines += ["", "*The August–September 2026 window is post-selection research data, not unseen evidence.",
              "", "## Decision", ""]
    if robust:
        lines.append(f"**{best.variant}** passed the initial robustness gates and should advance to combination testing.")
    else:
        lines.append("**Keep the ETH strategy unchanged.** No repeated-exposure rule passed all robustness gates.")
    lines += [
        "", "Native setup caps may show no effect because Dip and Pullback already emit one candidate per native setup. "
        "The cross-family market caps are the direct test of several labels representing the same ETH move.",
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
