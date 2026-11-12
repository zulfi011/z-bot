"""Experiment 12: measure Mode C's marginal value and five conservative restrictions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import baseline as baseline_module
from .engine import CandidateTrade, PortfolioConfig, ReplayResult, replay_portfolio
from .repeated_exposure import assign_episodes
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_mode_c_economics_v1.json"


def no_active_core_episode(candidate: CandidateTrade, _filled: list[dict],
                           open_lots: list[dict]) -> str | None:
    if candidate.source != "breakout":
        return None
    active = any(lot["source"] in {"dip", "pullback"}
                 and lot["market_episode"] == candidate.market_episode for lot in open_lots)
    return "mode_c_active_dip_pullback_episode" if active else None


def one_lot_per_frozen_band(candidate: CandidateTrade, filled: list[dict],
                            _open_lots: list[dict]) -> str | None:
    if candidate.source != "breakout":
        return None
    used = any(lot["source"] == "breakout" and lot["setup_episode"] == candidate.setup_episode
               for lot in filled)
    return "mode_c_frozen_band_already_filled" if used else None


def fresh_band_after_failed_breakout(candidate: CandidateTrade, filled: list[dict],
                                     _open_lots: list[dict]) -> str | None:
    if candidate.source != "breakout":
        return None
    failed = any(lot["source"] == "breakout"
                 and lot["setup_episode"] == candidate.setup_episode
                 and lot["exit_kind"] == "protective_stop"
                 and lot["exit_index"] <= candidate.entry for lot in filled)
    return "mode_c_failed_breakout_requires_fresh_band" if failed else None


def failed_breakout_cooldown(minutes: int):
    def policy(candidate: CandidateTrade, filled: list[dict], _open_lots: list[dict]) -> str | None:
        if candidate.source != "breakout":
            return None
        failures = [lot["exit_index"] for lot in filled
                    if lot["source"] == "breakout"
                    and lot["exit_kind"] == "protective_stop"
                    and lot["exit_index"] <= candidate.entry]
        if failures and candidate.entry - max(failures) < minutes:
            return "mode_c_failed_breakout_cooldown"
        return None
    return policy


def _mode_c_quality(result: ReplayResult) -> dict:
    trades = result.trades[result.trades.source == "breakout"]
    losses = trades[trades.pnl <= 0]
    return {
        "mode_c_trades": len(trades),
        "mode_c_profit": float(trades.pnl.sum()),
        "mode_c_average_pnl": float(trades.pnl.mean()) if len(trades) else 0.0,
        "mode_c_win_rate_pct": 100 * float((trades.pnl > 0).mean()) if len(trades) else 0.0,
        "mode_c_average_loss": float(losses.pnl.mean()) if len(losses) else 0.0,
        "mode_c_protective_stops": int((trades.exit_kind == "protective_stop").sum()),
    }


def _variant_inputs(candidates: list[CandidateTrade], cooldown: int):
    return {
        "without_mode_c": ([candidate for candidate in candidates if candidate.source != "breakout"], None),
        "mode_c_no_active_dip_pullback_episode": (candidates, no_active_core_episode),
        "mode_c_one_lot_per_frozen_band": (candidates, one_lot_per_frozen_band),
        "mode_c_fresh_band_after_failed_breakout": (candidates, fresh_band_after_failed_breakout),
        "mode_c_failed_breakout_cooldown_6h": (candidates, failed_breakout_cooldown(cooldown)),
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
    base_full = baseline["full"]
    rows, window_rows, block_rows, trade_rows = [], [], [], []

    variants = _variant_inputs(candidates, int(experiment["failed_breakout_cooldown_minutes"]))
    for label, (book, policy) in variants.items():
        results = {name: replay_portfolio(book, market, *windows[name], portfolio, policy)
                   for name in names}
        full = results["full"]
        changes = [results[name].summary["net_profit"] - baseline[name].summary["net_profit"]
                   for name in wf_names]
        mode_blocks = full.blocked_signals[
            full.blocked_signals.reason.str.startswith("mode_c_", na=False)
        ]
        rows.append({
            "variant": label, "profit": full.summary["net_profit"],
            "profit_change": full.summary["net_profit"] - base_full.summary["net_profit"],
            "trades": full.summary["trades"], "trade_change": full.summary["trades"] - base_full.summary["trades"],
            "win_rate_pct": full.summary["win_rate_pct"],
            "average_win": full.summary["average_win"], "average_loss": full.summary["average_loss"],
            "profit_factor": full.summary["profit_factor"],
            "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
            "drawdown_change_pct_points": full.summary["maximum_drawdown_pct"] - base_full.summary["maximum_drawdown_pct"],
            "walk_forward_change": sum(changes),
            "wf_windows_improved": sum(change > 0 for change in changes),
            "mode_c_policy_blocks": len(mode_blocks),
            "post_selection_change": (results["post_selection_2026_08_09"].summary["net_profit"]
                                      - baseline["post_selection_2026_08_09"].summary["net_profit"]),
            **_mode_c_quality(full),
        })
        if len(mode_blocks):
            block_rows.append(mode_blocks.assign(variant=label))
        trade_rows.append(full.trades.assign(variant=label))
        for name in names:
            window_rows.append({
                "variant": label, "window": name,
                "profit": results[name].summary["net_profit"],
                "baseline_profit": baseline[name].summary["net_profit"],
                "profit_change": results[name].summary["net_profit"] - baseline[name].summary["net_profit"],
                "trades": results[name].summary["trades"],
            })

    frame = pd.DataFrame(rows).sort_values(["profit_change", "walk_forward_change"], ascending=False)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.concat(trade_rows, ignore_index=True).to_csv(output / "variant_trades.csv", index=False)
    (pd.concat(block_rows, ignore_index=True) if block_rows else pd.DataFrame()).to_csv(
        output / "mode_c_blocked_signals.csv", index=False
    )
    baseline_quality = _mode_c_quality(base_full)
    baseline_summary = {**base_full.summary, **baseline_quality,
                        "walk_forward_profit": sum(baseline[name].summary["net_profit"] for name in wf_names)}
    (output / "summary.json").write_text(json.dumps({
        "baseline": baseline_summary, "best_full_profit": frame.iloc[0].to_dict(),
        "best_drawdown": frame.sort_values("max_drawdown_pct", ascending=False).iloc[0].to_dict(),
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(baseline_summary, frame))
    return output


def _report(base: dict, frame: pd.DataFrame) -> str:
    without = frame[frame.variant == "without_mode_c"].iloc[0]
    best = frame.iloc[0]
    lines = [
        "# ETH Mode C marginal-economics experiment", "", "## Original baseline", "",
        f"**${base['net_profit']:.2f} profit · {base['trades']} trades · {base['win_rate_pct']:.1f}% headline wins · "
        f"${base['average_loss']:.2f} average loss · {base['maximum_drawdown_pct']:.2f}% drawdown**", "",
        f"Mode C itself filled **{base['mode_c_trades']} trades**, earned **${base['mode_c_profit']:.2f}**, "
        f"averaged **${base['mode_c_average_pnl']:.2f} per trade**, and had "
        f"**{base['mode_c_protective_stops']} protective stops**.", "",
        "| Variant | Total profit | Change vs original | Trades | Mode C trades | Mode C profit | Win rate | Avg loss | Drawdown | WF change | WF improved | Blocks |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples():
        lines.append(
            f"| {row.variant} | ${row.profit:.2f} | ${row.profit_change:+.2f} | {row.trades} ({row.trade_change:+d}) | "
            f"{row.mode_c_trades} | ${row.mode_c_profit:.2f} | {row.win_rate_pct:.1f}% | ${row.average_loss:.2f} | "
            f"{row.max_drawdown_pct:.2f}% | ${row.walk_forward_change:+.2f} | {row.wf_windows_improved}/6 | {row.mode_c_policy_blocks} |"
        )
    passed = bool(best.profit_change > 0 and best.walk_forward_change > 0
                  and best.wf_windows_improved >= 4
                  and best.max_drawdown_pct >= base["maximum_drawdown_pct"])
    lines += ["", "## Decision", ""]
    if passed:
        lines.append(f"**Advance `{best.variant}` to forward testing, but do not deploy it yet.** It passed the frozen historical gates.")
    else:
        lines.append("**Keep Mode C unchanged.** None of the restrictions passed the robustness gates.")
    lines += [
        "",
        f"Removing Mode C changed total portfolio profit by **${without.profit_change:+.2f}**, not simply "
        f"-${base['mode_c_profit']:.2f}, because freed ETH slots admitted replacement Dip/Pullback signals.",
        "",
        "The August–September 2026 period remains post-selection data and is not used for acceptance.",
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
