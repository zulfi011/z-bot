"""Experiment 8: test entry throttles based on current ETH portfolio risk."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .engine import CandidateTrade, MarketData, PortfolioConfig, ReplayResult, replay_portfolio
from .repeated_exposure import assign_episodes
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_risk_throttle_v1.json"


def _marked_pnl(lot: dict, index: int, market: MarketData, config: PortfolioConfig) -> float:
    raw = float(market.close[max(index, 0)])
    value = (lot["quantity"] * raw * (1 - config.slippage_per_side)
             * (1 - config.fee_per_side))
    return value - lot["spend"]


def _equity_at(filled: list[dict], index: int, market: MarketData,
               config: PortfolioConfig) -> float:
    equity = config.initial_capital
    for lot in filled:
        if lot["entry_index"] > index:
            continue
        if lot["exit_index"] <= index:
            equity += lot["pnl"]
        else:
            equity += _marked_pnl(lot, index, market, config)
    return equity


def risk_policy(market: MarketData, config: PortfolioConfig, strongly_bearish: np.ndarray,
                *, realized_daily_loss: float | None = None,
                mtm_daily_loss: float | None = None, total_open_loss: float | None = None,
                episode_loss: float | None = None, maximum_unarmed: int | None = None,
                bearish_maximum_lots: int | None = None):
    """Create a causal gate that reads only information available before the new fill."""
    def policy(candidate: CandidateTrade, filled: list[dict], open_lots: list[dict]) -> str | None:
        mark_index = max(candidate.entry - 1, 0)
        day_start_time = market.times[candidate.entry].normalize()
        day_start = int(market.times.searchsorted(day_start_time))
        if realized_daily_loss is not None:
            realized_today = sum(
                lot["pnl"] for lot in filled
                if day_start <= lot["exit_index"] < candidate.entry
            )
            if realized_today <= -realized_daily_loss:
                return "risk_realized_daily_loss"
        if mtm_daily_loss is not None:
            current_equity = _equity_at(filled, mark_index, market, config)
            starting_equity = _equity_at(filled, max(day_start - 1, 0), market, config)
            if current_equity - starting_equity <= -mtm_daily_loss:
                return "risk_mtm_daily_loss"
        open_pnls = [(lot, _marked_pnl(lot, mark_index, market, config)) for lot in open_lots]
        if total_open_loss is not None:
            gross_open_loss = sum(min(pnl, 0.0) for _, pnl in open_pnls)
            if gross_open_loss <= -total_open_loss:
                return "risk_total_open_loss"
        if episode_loss is not None and candidate.market_episode is not None:
            episode_pnl = 0.0
            for lot in filled:
                if lot["market_episode"] != candidate.market_episode:
                    continue
                episode_pnl += (lot["pnl"] if lot["exit_index"] < candidate.entry
                                else _marked_pnl(lot, mark_index, market, config))
            if episode_pnl <= -episode_loss:
                return "risk_market_episode_loss"
        if maximum_unarmed is not None:
            unarmed = sum(lot["arm_index"] is None or lot["arm_index"] >= candidate.entry
                          for lot in open_lots)
            if unarmed >= maximum_unarmed:
                return f"risk_maximum_unarmed_{maximum_unarmed}"
        if (bearish_maximum_lots is not None and strongly_bearish[candidate.entry]
                and len(open_lots) >= bearish_maximum_lots):
            return f"risk_bearish_maximum_lots_{bearish_maximum_lots}"
        return None
    return policy


def _strongly_bearish_candidates(candidates: list[CandidateTrade]) -> np.ndarray:
    raw = baseline_module.compare.load("ETHUSDT")[0]
    daily = baseline_module.live.replay.daily_averages(raw)
    output = np.zeros(len(raw), dtype=bool)
    for candidate in candidates:
        day = raw.open_time.iloc[candidate.entry].floor("D")
        values = daily.get(day, (None, None, None))
        if all(value is not None for value in values):
            a7, a15, a30 = map(float, values)
            output[candidate.entry] = a7 < a15 < a30
    return output


def _variants(experiment: dict, market: MarketData, portfolio: PortfolioConfig,
              bearish: np.ndarray):
    make = lambda **kwargs: risk_policy(market, portfolio, bearish, **kwargs)
    return {
        "realized_daily_25": make(realized_daily_loss=experiment["realized_daily_loss_usd"]),
        "mtm_daily_15": make(mtm_daily_loss=experiment["mtm_daily_loss_usd"]),
        "total_open_loss_10": make(total_open_loss=experiment["total_open_loss_usd"]),
        "market_episode_loss_7_5": make(episode_loss=experiment["market_episode_loss_usd"]),
        "maximum_unarmed_3": make(maximum_unarmed=3),
        "maximum_unarmed_2": make(maximum_unarmed=2),
        "bearish_maximum_lots_3": make(bearish_maximum_lots=3),
        "bearish_maximum_lots_2": make(bearish_maximum_lots=2),
        "conservative_bundle": make(
            realized_daily_loss=experiment["realized_daily_loss_usd"],
            mtm_daily_loss=experiment["mtm_daily_loss_usd"],
            total_open_loss=experiment["total_open_loss_usd"],
            episode_loss=experiment["market_episode_loss_usd"],
            maximum_unarmed=3, bearish_maximum_lots=3,
        ),
    }


def _worst_mtm_day(equity: pd.DataFrame) -> float:
    if equity.empty:
        return 0.0
    frame = equity.copy()
    frame["day"] = frame.timestamp.dt.floor("D")
    frame["day_start"] = frame.groupby("day").equity.transform("first")
    return float((frame.equity - frame.day_start).min())


def _quality(result: ReplayResult) -> dict:
    trades = result.trades
    returns = 100 * trades.pnl / trades.spend
    return {
        "economic_winners": int((returns > 0.25).sum()),
        "economic_flats": int(((returns >= -0.25) & (returns <= 0.25)).sum()),
        "economic_losers": int((returns < -0.25).sum()),
        "economic_win_rate_pct": 100 * float((returns > 0.25).mean()),
        "expectancy_per_trade": float(trades.pnl.mean()),
        "worst_mtm_day_usd": _worst_mtm_day(result.equity),
    }


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    market, plain_candidates, windows = baseline_module.build_baseline()
    candidates = assign_episodes(plain_candidates, market, experiment)
    bearish = _strongly_bearish_candidates(candidates)
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    baseline = {name: replay_portfolio(candidates, market, *windows[name], portfolio) for name in names}
    base_full = baseline["full"]
    rows, window_rows, blocked_rows = [], [], []

    for label, policy in _variants(experiment, market, portfolio, bearish).items():
        results = {name: replay_portfolio(candidates, market, *windows[name], portfolio, policy)
                   for name in names}
        full = results["full"]
        wf_changes = [results[name].summary["net_profit"] - baseline[name].summary["net_profit"]
                      for name in wf_names]
        policy_blocks = full.blocked_signals[
            full.blocked_signals.reason.str.startswith("risk_", na=False)
        ]
        rows.append({
            "variant": label, "profit": full.summary["net_profit"],
            "profit_change": full.summary["net_profit"] - base_full.summary["net_profit"],
            "trades": full.summary["trades"], "trade_change": full.summary["trades"] - base_full.summary["trades"],
            "average_loss": full.summary["average_loss"],
            "profit_factor": full.summary["profit_factor"],
            "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
            "walk_forward_change": sum(wf_changes),
            "wf_windows_improved": sum(change > 0 for change in wf_changes),
            "policy_blocks": len(policy_blocks),
            **_quality(full),
        })
        if len(policy_blocks):
            blocked_rows.append(policy_blocks.assign(variant=label))
        for name in names:
            window_rows.append({
                "variant": label, "window": name, "profit": results[name].summary["net_profit"],
                "baseline_profit": baseline[name].summary["net_profit"],
                "profit_change": results[name].summary["net_profit"] - baseline[name].summary["net_profit"],
            })

    frame = pd.DataFrame(rows).sort_values(["profit_change", "max_drawdown_pct"], ascending=False)
    baseline_summary = {**base_full.summary, **_quality(base_full)}
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    (pd.concat(blocked_rows, ignore_index=True) if blocked_rows else pd.DataFrame()).to_csv(
        output / "risk_blocked_signals.csv", index=False
    )
    (output / "summary.json").write_text(json.dumps({
        "baseline": baseline_summary, "best_profit": frame.iloc[0].to_dict(),
        "best_drawdown": frame.sort_values("max_drawdown_pct", ascending=False).iloc[0].to_dict(),
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(baseline_summary, frame))
    return output


def _report(base: dict, frame: pd.DataFrame) -> str:
    unarmed_three = frame[frame.variant == "maximum_unarmed_3"].iloc[0]
    unarmed_two = frame[frame.variant == "maximum_unarmed_2"].iloc[0]
    bearish = frame[frame.variant == "bearish_maximum_lots_3"].iloc[0]
    open_loss = frame[frame.variant == "total_open_loss_10"].iloc[0]
    return f"""# ETH portfolio-risk throttle experiment

## Original baseline

**${base['net_profit']:.2f} profit · {base['trades']} trades · {base['economic_win_rate_pct']:.1f}% economic winners · ${base['average_loss']:.2f} average loss · {base['maximum_drawdown_pct']:.2f}% drawdown**

| Variant | Profit change | Trades | Economic win rate | Avg loss | Drawdown | Worst MTM day | WF change | Windows improved | Blocks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
""" + "\n".join(
        f"| {row.variant} | ${row.profit_change:+.2f} | {row.trades} ({row.trade_change:+d}) | "
        f"{row.economic_win_rate_pct:.1f}% | ${row.average_loss:.2f} | {row.max_drawdown_pct:.2f}% | "
        f"${row.worst_mtm_day_usd:.2f} | ${row.walk_forward_change:+.2f} | "
        f"{row.wf_windows_improved}/6 | {row.policy_blocks} |"
        for row in frame.itertuples()
    ) + f"""

## Decision

**Do not change the ETH allocation rules from this experiment.**

- The current $25 realized-loss rule and the new $15 marked-daily and $7.50 episode limits blocked no historical entry. They are safety guards, but they do not improve this backtest.
- The $10 total-open-loss rule blocked one signal and changed profit by **${open_loss.profit_change:+.2f}** without improving drawdown.
- A three-unarmed-lot cap improved drawdown from **{base['maximum_drawdown_pct']:.2f}%** to **{unarmed_three.max_drawdown_pct:.2f}%** and the worst marked day from **${base['worst_mtm_day_usd']:.2f}** to **${unarmed_three.worst_mtm_day_usd:.2f}**, but sacrificed **${-unarmed_three.profit_change:.2f}** of profit.
- A two-unarmed-lot cap improved drawdown to **{unarmed_two.max_drawdown_pct:.2f}%**, but sacrificed **${-unarmed_two.profit_change:.2f}**. Reject both caps.
- The bearish slot cap avoided one losing trade and added **${bearish.profit_change:.2f}**, but improved only **{int(bearish.wf_windows_improved)}/6** walk-forward windows and did not reduce maximum drawdown. It is too weak to adopt.
- The combined rule is identical to the three-unarmed-lot cap because that condition dominates its decisions.

No throttle force-closes an existing position. The marked-loss checks should remain available as operational safeguards, but this history does not justify presenting them as a strategy improvement.
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
