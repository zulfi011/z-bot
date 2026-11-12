"""Build one-minute account curves for the frozen Stage 2 portfolio."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtesting.account import build_account_curve, select_spot_lots  # noqa: E402


RUN_ID = "step7_account_tracking_v1"
DATA = ROOT / "data" / RUN_ID
RESULTS = ROOT / "results" / RUN_ID
CONFIG = ROOT / "config/strategies/sol_15d_touch_v1.yaml"
OUTCOMES = ROOT / "data/step6b_concurrent_positions_v1/all_signal_outcomes.parquet"
RAW = ROOT.parent / "foundations/data/raw/SOLUSDT/SOLUSDT_1m.parquet"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run() -> None:
    if DATA.exists() or RESULTS.exists():
        raise ValueError("Run already exists; refusing overwrite")
    config = yaml.safe_load(CONFIG.read_text())
    execution = config["execution"]
    sizing = execution["position_sizing"]
    initial = float(sizing["initial_equity_usd"])
    fraction = float(sizing["fraction_per_entry"])
    maximum = int(execution["maximum_open_positions"])
    if execution["leverage"] or execution["short_selling"]:
        raise ValueError("This account tracker supports long-only spot trading")
    if maximum != 2 or fraction != 0.25:
        raise ValueError("Frozen portfolio rule is not two positions at 25% each")

    candles = pd.read_parquet(RAW, columns=["open_time", "open", "close"])
    outcomes = pd.read_parquet(OUTCOMES)
    DATA.mkdir(parents=True)
    RESULTS.mkdir(parents=True)
    summaries = []

    for strategy in ["primary", "control"]:
        candidates = outcomes.loc[outcomes.strategy.eq(strategy)].copy()
        selected = select_spot_lots(candidates, candles, initial, fraction, maximum)
        curve = build_account_curve(candles, selected, initial)
        if curve.open_positions.max() > maximum or curve.cash_usd.min() < -1e-8:
            raise AssertionError("Frozen spot constraints failed")
        if curve.open_positions.iloc[-1] != 0 or curve.open_position_quantity.iloc[-1] != 0:
            raise AssertionError("Open lot remained after the research window")
        if not np.isclose(curve.total_equity_usd.iloc[-1], initial + selected.realized_pnl_usd.sum()):
            raise AssertionError("Final balance does not reconcile to trades")

        selected.to_parquet(DATA / f"{strategy}_selected_lots.parquet", index=False)
        curve.to_parquet(DATA / f"{strategy}_account_curve_1m.parquet", index=False)
        summaries.append({
            "strategy": strategy,
            "candles_tracked": len(curve),
            "started_at": curve.timestamp.iloc[0],
            "ended_at": curve.timestamp.iloc[-1],
            "candidate_signals": len(candidates),
            "opened_trades": len(selected),
            "ignored_signals": len(candidates) - len(selected),
            "winning_trades": int((selected.realized_pnl_usd > 0).sum()),
            "losing_trades": int((selected.realized_pnl_usd <= 0).sum()),
            "maximum_positions_observed": int(curve.open_positions.max()),
            "minimum_cash_usd": float(curve.cash_usd.min()),
            "maximum_open_value_usd": float(curve.open_position_value_usd.max()),
            "final_equity_usd": float(curve.total_equity_usd.iloc[-1]),
            "total_pnl_usd": float(curve.total_pnl_usd.iloc[-1]),
            "total_return_pct": float((curve.total_equity_usd.iloc[-1] / initial - 1) * 100),
            "max_mark_to_market_drawdown_pct": float(curve.drawdown_pct.min()),
            "lowest_equity_usd": float(curve.total_equity_usd.min()),
        })

    summary = pd.DataFrame(summaries)
    summary.to_csv(RESULTS / "summary.csv", index=False)
    validation = {
        "step": "stage2_step7_account_tracking",
        "status": "PASS",
        "account_rows_per_strategy": len(candles),
        "total_account_rows": len(candles) * 2,
        "maximum_open_positions": maximum,
        "equity_fraction_per_entry": fraction,
        "initial_equity_usd": initial,
        "leverage_used": False,
        "account_identity": "cash + open_position_value = initial_equity + realized_pnl + unrealized_pnl",
        "valuation_time": "each raw one-minute candle close",
        "outcome_source_sha256": sha256(OUTCOMES),
        "raw_source_sha256": sha256(RAW),
    }
    (RESULTS / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    print(summary.to_string(index=False))
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    run()

