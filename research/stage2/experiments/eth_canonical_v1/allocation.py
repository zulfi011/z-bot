"""Experiment 3: test deterministic ETH signal priority and a conditional final-slot reservation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import baseline as baseline_module
from .engine import CandidateTrade, PortfolioConfig, ReplayResult, replay_portfolio
from .repeated_exposure import assign_episodes
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config

EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_allocation_v1.json"


def prioritize(candidates: list[CandidateTrade], order: list[str]) -> list[CandidateTrade]:
    """Change only the order of candidates sharing an execution minute."""
    rank = {source: index for index, source in enumerate(order)}
    original = {candidate.candidate_id: index for index, candidate in enumerate(candidates)}
    return sorted(candidates, key=lambda candidate: (
        candidate.entry, rank.get(candidate.source, len(rank)), original[candidate.candidate_id]
    ))


def reserve_final_slot(maximum_lots: int):
    """In a clean uptrend, only a pullback may consume the fifth and final ETH slot."""
    def policy(candidate: CandidateTrade, _filled: list[dict], open_lots: list[dict]) -> str | None:
        if candidate.bullish_entry and candidate.source != "pullback" and len(open_lots) == maximum_lots - 1:
            return "allocation_final_slot_reserved_for_pullback"
        return None
    return policy


def _blocked_summary(result: ReplayResult) -> pd.DataFrame:
    blocked = result.blocked_signals
    if blocked.empty:
        return pd.DataFrame(columns=[
            "source", "blocked", "hypothetical_winners", "hypothetical_win_rate_pct",
            "hypothetical_pnl", "duplicate_market_episodes",
        ])
    return pd.DataFrame([{
        "source": source,
        "blocked": len(part),
        "hypothetical_winners": int(part.hypothetical_winner.fillna(False).sum()),
        "hypothetical_win_rate_pct": 100 * part.hypothetical_winner.fillna(False).mean(),
        "hypothetical_pnl": part.hypothetical_pnl.sum(),
        "duplicate_market_episodes": int(part.duplicate_market_episode.fillna(False).sum()),
    } for source, part in blocked.groupby("source", sort=True)])


def _open_position_rows(result: ReplayResult) -> pd.DataFrame:
    rows = []
    for blocked in result.blocked_signals.itertuples():
        for position in json.loads(blocked.open_positions or "[]"):
            rows.append({
                "blocked_candidate_id": blocked.candidate_id, "blocked_source": blocked.source,
                "blocked_at": blocked.entry_time, "open_source": position["source"],
                "age_minutes": position["age_minutes"], "armed": position["armed"],
                "same_market_episode": position["market_episode"] is not None
                and position["market_episode"] == getattr(blocked, "market_episode", None),
            })
    return pd.DataFrame(rows)


def _same_minute_conflicts(candidates: list[CandidateTrade], market, start, end) -> pd.DataFrame:
    rows = [{"entry_index": candidate.entry, "entry_time": market.times[candidate.entry],
             "source": candidate.source, "candidate_id": candidate.candidate_id}
            for candidate in candidates if start <= market.times[candidate.entry] < end]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    counts = frame.groupby("entry_index").source.transform("nunique")
    return frame[counts > 1].sort_values(["entry_index", "source"])


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio: PortfolioConfig = _portfolio_config(baseline_config)
    market, plain_candidates, windows = baseline_module.build_baseline()
    candidates = assign_episodes(plain_candidates, market, experiment)
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]

    variants = {
        "priority_pullback_dip_modec": (
            prioritize(candidates, experiment["simultaneous_priority"]), None
        ),
        "reserve_final_slot_for_pullback": (
            candidates, reserve_final_slot(portfolio.maximum_lots)
        ),
    }
    baseline = {name: replay_portfolio(candidates, market, *windows[name], portfolio) for name in names}
    base_full = baseline["full"]
    rows, window_rows = [], []
    for label, (ordered, policy) in variants.items():
        results = {name: replay_portfolio(ordered, market, *windows[name], portfolio, policy) for name in names}
        full = results["full"]
        changes = [results[name].summary["net_profit"] - baseline[name].summary["net_profit"]
                   for name in wf_names]
        baseline_ids, variant_ids = set(base_full.trades.candidate_id), set(full.trades.candidate_id)
        added = full.trades[full.trades.candidate_id.isin(variant_ids - baseline_ids)]
        displaced = base_full.trades[base_full.trades.candidate_id.isin(baseline_ids - variant_ids)]
        allocation_blocks = full.blocked_signals[
            full.blocked_signals.reason.str.startswith("allocation_", na=False)
        ]
        rows.append({
            "variant": label, "profit": full.summary["net_profit"],
            "profit_change": full.summary["net_profit"] - base_full.summary["net_profit"],
            "trades": full.summary["trades"], "trade_change": full.summary["trades"] - base_full.summary["trades"],
            "win_rate_pct": full.summary["win_rate_pct"], "average_win": full.summary["average_win"],
            "average_loss": full.summary["average_loss"], "profit_factor": full.summary["profit_factor"],
            "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
            "walk_forward_profit": sum(results[name].summary["net_profit"] for name in wf_names),
            "walk_forward_change": sum(changes), "wf_windows_improved": sum(change > 0 for change in changes),
            "post_selection_profit": results["post_selection_2026_08_09"].summary["net_profit"],
            "post_selection_change": (results["post_selection_2026_08_09"].summary["net_profit"]
                                      - baseline["post_selection_2026_08_09"].summary["net_profit"]),
            "allocation_blocks": len(allocation_blocks),
            "additional_trades": len(added), "additional_trade_pnl": added.pnl.sum(),
            "displaced_trades": len(displaced), "displaced_baseline_pnl": displaced.pnl.sum(),
        })
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
    base_full.blocked_signals.to_csv(output / "baseline_blocked_signals.csv", index=False)
    _blocked_summary(base_full).to_csv(output / "baseline_blocked_summary.csv", index=False)
    _open_position_rows(base_full).to_csv(output / "blocked_open_position_details.csv", index=False)
    conflicts = _same_minute_conflicts(candidates, market, *windows["full"])
    conflicts.to_csv(output / "simultaneous_signal_conflicts.csv", index=False)
    baseline_summary = {
        "profit": base_full.summary["net_profit"], "trades": base_full.summary["trades"],
        "win_rate_pct": base_full.summary["win_rate_pct"], "average_loss": base_full.summary["average_loss"],
        "max_drawdown_pct": base_full.summary["maximum_drawdown_pct"],
        "walk_forward_profit": sum(baseline[name].summary["net_profit"] for name in wf_names),
        "post_selection_profit": baseline["post_selection_2026_08_09"].summary["net_profit"],
        "blocked_signals": len(base_full.blocked_signals),
        "simultaneous_conflict_minutes": int(conflicts.entry_index.nunique()) if len(conflicts) else 0,
    }
    (output / "summary.json").write_text(json.dumps({
        "baseline": baseline_summary, "best": frame.iloc[0].to_dict(),
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(baseline_summary, _blocked_summary(base_full), frame))
    return output


def _report(baseline: dict, blocked: pd.DataFrame, frame: pd.DataFrame) -> str:
    best = frame.iloc[0]
    robust = bool(best.profit_change > 0 and best.walk_forward_change > 0
                  and best.wf_windows_improved >= 4
                  and best.max_drawdown_pct >= baseline["max_drawdown_pct"])
    verdict = "IMPROVED" if robust else "DOES NOT ROBUSTLY IMPROVE"
    lines = [
        "# ETH allocation experiment", "", f"## Verdict: {verdict}", "",
        f"Baseline: **${baseline['profit']:.2f}** profit · **{baseline['blocked_signals']}** blocked signals · "
        f"**{baseline['simultaneous_conflict_minutes']}** minutes with simultaneous cross-family signals", "",
        "## Blocked-signal evidence", "",
        "| Family | Blocked | Hypothetical winners | Hypothetical win rate | Hypothetical P&L* | Duplicate market episode |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in blocked.itertuples():
        lines.append(f"| {row.source} | {row.blocked} | {row.hypothetical_winners} | "
                     f"{row.hypothetical_win_rate_pct:.1f}% | ${row.hypothetical_pnl:.2f} | "
                     f"{row.duplicate_market_episodes} |")
    lines += [
        "", "\\* Hypothetical blocked-trade P&L is diagnostic and is not additive portfolio profit.", "",
        "## Portfolio tests", "",
        "| Variant | Profit change | Trades | Win rate | Avg loss | Drawdown | WF change | Windows improved | Retired-holdout change* |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples():
        lines.append(f"| {row.variant} | {row.profit_change:+.2f} | {row.trades} ({row.trade_change:+d}) | "
                     f"{row.win_rate_pct:.1f}% | ${row.average_loss:.2f} | {row.max_drawdown_pct:.2f}% | "
                     f"{row.walk_forward_change:+.2f} | {row.wf_windows_improved}/6 | {row.post_selection_change:+.2f} |")
    lines += ["", "*The August–September 2026 window is post-selection research data, not unseen evidence.",
              "", "## Decision", ""]
    if robust:
        lines.append(f"**{best.variant}** passed the initial robustness gates.")
    else:
        lines.append("**Keep first-come-first-served allocation unchanged.** Neither preregistered change passed.")
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
