"""Experiment 13: clean canonical replay of the ETH pullback entry and a frozen 3x3 neighbourhood."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .engine import CandidateTrade, PortfolioConfig, ReplayResult, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_pullback_revalidation_v1.json"


def build_pullback_candidates(hours: int, dwell: int) -> tuple[object, list[CandidateTrade]]:
    """Build one pullback setting with the exact deployed costs, stop, floor and 16-hour exit."""
    raw, bullish = baseline_module.compare.load("ETHUSDT")
    rule = baseline_module.live.load_rule("eth")
    line = pd.Series(baseline_module.grid.CLOSE).ewm(span=16 * 60, adjust=False).mean().to_numpy()
    baseline_module.floor_arm.LINE_FLOOR = line * (1 + baseline_module.floor_arm.COSTS / 100)
    entries = baseline_module.pullback.pullback_entries(
        baseline_module.grid.CLOSE, bullish, hours, dwell, baseline_module.grid.TIMES,
        blocked=rule["blocked"],
    )
    book = baseline_module.floor_arm.book(
        ((entries, "pullback", baseline_module.modes.DIP_STOP,
          rule["activation_pct"], rule["giveback_pct"]),),
        bullish, line, baseline_module.floor_arm.DEPLOYED_ARM, "buy price", "on arming",
    )
    candidates = [CandidateTrade(
        entry=int(trade["entry"]), exit=int(trade["exit"]), exit_price=float(trade["price"]),
        source="pullback", exit_code=int(trade["why"]),
        candidate_id=f"pullback-{hours}h-{dwell}m:{baseline_module.grid.TIMES[int(trade['entry'])].isoformat()}:{index}",
        exit_kind=baseline_module._exit_kind(trade), arm_index=baseline_module._arm_index(trade),
        bullish_entry=bool(bullish[int(trade["entry"])]),
    ) for index, trade in enumerate(book)]
    return raw, candidates


def _excluded_month_mask(trades: pd.DataFrame, months: list[str]) -> pd.Series:
    periods = trades.entry_time.dt.tz_localize(None).dt.to_period("M").astype(str)
    return periods.isin(months)


def _quality(result: ReplayResult, excluded_months: list[str]) -> dict:
    trades = result.trades
    excluded = _excluded_month_mask(trades, excluded_months) if len(trades) else pd.Series(dtype=bool)
    ordinary = trades[~excluded] if len(trades) else trades
    pull = trades[trades.source == "pullback"] if len(trades) else trades
    pull_ordinary = pull[~_excluded_month_mask(pull, excluded_months)] if len(pull) else pull
    slot_days = float(pull.minutes_held.sum() / 1440) if len(pull) else 0.0
    ordinary_slot_days = float(pull_ordinary.minutes_held.sum() / 1440) if len(pull_ordinary) else 0.0
    return {
        "profit_excluding_april_may_2025": float(ordinary.pnl.sum()),
        "trades_excluding_april_may_2025": len(ordinary),
        "pullback_trades": len(pull), "pullback_profit": float(pull.pnl.sum()),
        "pullback_profit_per_trade": float(pull.pnl.mean()) if len(pull) else 0.0,
        "pullback_profit_per_occupied_slot_day": float(pull.pnl.sum() / slot_days) if slot_days else 0.0,
        "pullback_profit_excluding_april_may_2025": float(pull_ordinary.pnl.sum()),
        "pullback_trades_excluding_april_may_2025": len(pull_ordinary),
        "pullback_profit_per_occupied_slot_day_excluding_april_may_2025": (
            float(pull_ordinary.pnl.sum() / ordinary_slot_days) if ordinary_slot_days else 0.0
        ),
    }


def _family_economics(result: ReplayResult, excluded_months: list[str]) -> pd.DataFrame:
    rows = []
    for source, trades in result.trades.groupby("source"):
        ordinary = trades[~_excluded_month_mask(trades, excluded_months)]
        occupied_days = float(trades.minutes_held.sum() / 1440)
        ordinary_occupied_days = float(ordinary.minutes_held.sum() / 1440)
        rows.append({
            "source": source, "trades": len(trades), "profit": trades.pnl.sum(),
            "profit_per_trade": trades.pnl.mean(),
            "profit_per_occupied_slot_day": trades.pnl.sum() / occupied_days if occupied_days else 0.0,
            "profit_excluding_april_may_2025": ordinary.pnl.sum(),
            "profit_per_trade_excluding_april_may_2025": ordinary.pnl.mean() if len(ordinary) else 0.0,
            "profit_per_occupied_slot_day_excluding_april_may_2025": (
                ordinary.pnl.sum() / ordinary_occupied_days if ordinary_occupied_days else 0.0
            ),
        })
    return pd.DataFrame(rows).sort_values("profit_per_trade", ascending=False)


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio: PortfolioConfig = _portfolio_config(baseline_config)
    market, baseline_candidates, windows = baseline_module.build_baseline()
    core = [candidate for candidate in baseline_candidates if candidate.source != "pullback"]
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    excluded_months = experiment["excluded_entry_months"]

    books: dict[str, list[CandidateTrade]] = {"no_pullback": core}
    for hours in experiment["ema_hours"]:
        for dwell in experiment["dwell_minutes"]:
            _, pull = build_pullback_candidates(int(hours), int(dwell))
            books[f"pullback_{hours}h_{dwell}m"] = sorted(
                [*core, *pull], key=lambda candidate: (candidate.entry, candidate.candidate_id)
            )

    control_label = "pullback_24h_180m"
    results = {label: {name: replay_portfolio(book, market, *windows[name], portfolio)
                       for name in names} for label, book in books.items()}
    control = results[control_label]
    base_full = control["full"]
    rows, window_rows, trade_rows = [], [], []
    for label, by_window in results.items():
        full = by_window["full"]
        changes = [by_window[name].summary["net_profit"] - control[name].summary["net_profit"]
                   for name in wf_names]
        row = {
            "variant": label, "profit": full.summary["net_profit"],
            "profit_change": full.summary["net_profit"] - base_full.summary["net_profit"],
            "trades": full.summary["trades"], "trade_change": full.summary["trades"] - base_full.summary["trades"],
            "win_rate_pct": full.summary["win_rate_pct"], "average_win": full.summary["average_win"],
            "average_loss": full.summary["average_loss"], "profit_factor": full.summary["profit_factor"],
            "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
            "walk_forward_profit": sum(by_window[name].summary["net_profit"] for name in wf_names),
            "walk_forward_change": sum(changes), "wf_windows_improved": sum(change > 0 for change in changes),
            **_quality(full, excluded_months),
        }
        row["ordinary_profit_change"] = (row["profit_excluding_april_may_2025"]
                                         - _quality(base_full, excluded_months)["profit_excluding_april_may_2025"])
        rows.append(row)
        trade_rows.append(full.trades.assign(variant=label))
        for name in names:
            window_rows.append({
                "variant": label, "window": name, "profit": by_window[name].summary["net_profit"],
                "control_profit": control[name].summary["net_profit"],
                "profit_change": by_window[name].summary["net_profit"] - control[name].summary["net_profit"],
            })

    frame = pd.DataFrame(rows).sort_values("profit", ascending=False)
    family = _family_economics(base_full, excluded_months)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "neighbourhood_results.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.concat(trade_rows, ignore_index=True).to_csv(output / "variant_trades.csv", index=False)
    family.to_csv(output / "control_family_economics.csv", index=False)
    control_summary = {**base_full.summary, **_quality(base_full, excluded_months),
                       "walk_forward_profit": sum(control[name].summary["net_profit"] for name in wf_names)}
    (output / "summary.json").write_text(json.dumps({
        "control": control_summary, "no_pullback": frame[frame.variant == "no_pullback"].iloc[0].to_dict(),
        "best_full_history": frame.iloc[0].to_dict(),
        "best_excluding_april_may": frame.sort_values("profit_excluding_april_may_2025", ascending=False).iloc[0].to_dict(),
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(control_summary, frame, family))
    return output


def _report(control: dict, frame: pd.DataFrame, family: pd.DataFrame) -> str:
    no_pull = frame[frame.variant == "no_pullback"].iloc[0]
    deployed = frame[frame.variant == "pullback_24h_180m"].iloc[0]
    neighbours = frame[frame.variant.str.startswith("pullback_")]
    profitable_neighbours = int((neighbours.profit > no_pull.profit).sum())
    ordinary_profitable = int((neighbours.profit_excluding_april_may_2025
                               > no_pull.profit_excluding_april_may_2025).sum())
    rows = []
    for row in frame.itertuples():
        marker = " (control)" if row.variant == "pullback_24h_180m" else ""
        rows.append(
            f"| {row.variant}{marker} | ${row.profit:.2f} | ${row.profit_change:+.2f} | "
            f"${row.profit_excluding_april_may_2025:.2f} | ${row.ordinary_profit_change:+.2f} | "
            f"{row.trades} | {row.pullback_trades} | ${row.pullback_profit_per_trade:.2f} | "
            f"{row.win_rate_pct:.1f}% | ${row.average_loss:.2f} | {row.max_drawdown_pct:.2f}% | "
            f"${row.walk_forward_change:+.2f} | {row.wf_windows_improved}/6 |"
        )
    family_rows = "\n".join(
        f"| {row.source} | {row.trades} | ${row.profit:.2f} | ${row.profit_per_trade:.2f} | "
        f"${row.profit_per_occupied_slot_day:.2f} | ${row.profit_per_trade_excluding_april_may_2025:.2f} | "
        f"${row.profit_per_occupied_slot_day_excluding_april_may_2025:.2f} |"
        for row in family.itertuples()
    )
    april_may_share = 100 * (control['pullback_profit'] - control['pullback_profit_excluding_april_may_2025']) / control['pullback_profit']
    return f"""# ETH pullback clean revalidation

## Original 24h/180m control

**${control['net_profit']:.2f} profit · {control['trades']} trades · {control['win_rate_pct']:.1f}% headline wins · ${control['average_loss']:.2f} average loss · {control['maximum_drawdown_pct']:.2f}% drawdown**

Pullback filled **{control['pullback_trades']} trades**, contributed **${control['pullback_profit']:.2f}**, and averaged **${control['pullback_profit_per_trade']:.2f} per filled pullback**.

## Frozen neighbourhood

| Variant | Total profit | Change vs control | Ex-Apr/May profit | Ex-Apr/May change | Trades | Pullbacks | Pullback $/trade | Win rate | Avg loss | Drawdown | WF change | WF improved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

April–May exclusion uses the entry month of each actually filled shared-slot trade. It is a concentration diagnostic, not a separately tradable backtest.

## Opportunity per occupied slot in the unchanged control

| Family | Trades | Profit | Profit/trade | Profit/slot-day | Ex-Apr/May $/trade | Ex-Apr/May $/slot-day |
|---|---:|---:|---:|---:|---:|---:|
{family_rows}

## Decision

**Keep the live 24h/180m rule unchanged for now, but do not grant pullback priority or retune it.** Removing pullback changes portfolio profit by only **${no_pull.profit_change:+.2f}** and profit excluding April–May by **${no_pull.ordinary_profit_change:+.2f}**. Only **{profitable_neighbours}/9** pullback settings beat no-pullback on full history, and only **{ordinary_profitable}/9** beat it after excluding April–May.

Pullback has the best full-history profit per trade and slot-day, but **{april_may_share:.1f}%** of its labeled profit came from April–May 2025. Outside those months it falls to **${control['pullback_profit_per_occupied_slot_day_excluding_april_may_2025']:.2f} per occupied slot-day**, below both Dip and Mode C. It therefore does **not** cleanly remain the best ordinary-period opportunity, so this test does not support priority allocation, a separate sleeve, or additional slots.

The August–September 2026 period remains post-selection data and is excluded from acceptance.
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
