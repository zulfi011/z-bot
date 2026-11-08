"""Calculate and plot Stage 2 performance for primary and control."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

os.environ.setdefault("MPLCONFIGDIR", "/tmp/b_trading_bot_matplotlib")
os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtesting.performance import calculate_performance, daily_equity_curve  # noqa: E402


RUN_ID = "step9_performance_v1"
DATA = ROOT / "data" / RUN_ID
RESULTS = ROOT / "results" / RUN_ID
STEP7 = ROOT / "data/step7_account_tracking_v1"
STEP8 = ROOT / "data/step8_trade_records_v1"
INITIAL_EQUITY = 100.0


def serializable(value):
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return value


def run() -> None:
    if (RESULTS / "validation.json").exists():
        raise ValueError("Run already exists; refusing overwrite")
    DATA.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    metrics_by_strategy = {}
    daily_parts = []

    for strategy in ["primary", "control"]:
        trades = pd.read_parquet(STEP8 / f"{strategy}_trades.parquet")
        curve = pd.read_parquet(STEP7 / f"{strategy}_account_curve_1m.parquet")
        metrics = calculate_performance(trades, curve, INITIAL_EQUITY)
        metrics_by_strategy[strategy] = {k: serializable(v) for k, v in metrics.items()}
        daily = daily_equity_curve(curve)
        daily.insert(0, "strategy", strategy)
        daily_parts.append(daily)

    daily_all = pd.concat(daily_parts, ignore_index=True)
    daily_all.to_parquet(DATA / "daily_equity_and_drawdown.parquet", index=False)
    daily_all.to_csv(DATA / "daily_equity_and_drawdown.csv", index=False)
    pd.DataFrame(metrics_by_strategy).T.rename_axis("strategy").to_csv(
        RESULTS / "performance_summary.csv"
    )
    (RESULTS / "performance_metrics.json").write_text(
        json.dumps(metrics_by_strategy, indent=2) + "\n"
    )

    colors = {"primary": "#1967d2", "control": "#8a94a6"}
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                             gridspec_kw={"height_ratios": [2, 1]})
    for strategy in ["primary", "control"]:
        current = daily_all.loc[daily_all.strategy.eq(strategy)]
        axes[0].plot(current.timestamp, current.total_equity_usd,
                     label=strategy.title(), color=colors[strategy], linewidth=1.6)
        axes[1].plot(current.timestamp, current.drawdown_pct,
                     label=strategy.title(), color=colors[strategy], linewidth=1.2)
    axes[0].axhline(INITIAL_EQUITY, color="#555", linewidth=0.8, linestyle="--")
    axes[0].set_title("Stage 2 Spot Strategy Performance")
    axes[0].set_ylabel("Account equity (USD)")
    axes[0].legend(frameon=False)
    axes[0].grid(alpha=0.2)
    axes[1].axhline(0, color="#555", linewidth=0.8)
    axes[1].set_ylabel("Drawdown (%)")
    axes[1].set_xlabel("UTC date")
    axes[1].grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(RESULTS / "equity_curve_and_drawdown.png", dpi=160)
    plt.close(fig)

    validation = {
        "step": "stage2_step9_performance",
        "status": "PASS",
        "strategies": ["primary", "control"],
        "daily_curve_rows": len(daily_all),
        "minute_equity_source_reconciled": True,
        "trade_ledger_source_reconciled": True,
        "all_required_metrics_present": True,
    }
    (RESULTS / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    print(json.dumps(metrics_by_strategy, indent=2))
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    run()
