"""Save and validate the Stage 2 per-trade ledgers."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtesting.trade_records import build_trade_records, trade_record_summary  # noqa: E402


RUN_ID = "step8_trade_records_v1"
DATA = ROOT / "data" / RUN_ID
RESULTS = ROOT / "results" / RUN_ID
STEP7_DATA = ROOT / "data/step7_account_tracking_v1"
STEP7_SUMMARY = ROOT / "results/step7_account_tracking_v1/summary.csv"


def run() -> None:
    if DATA.exists() or RESULTS.exists():
        raise ValueError("Run already exists; refusing overwrite")
    DATA.mkdir(parents=True)
    RESULTS.mkdir(parents=True)
    account_summary = pd.read_csv(STEP7_SUMMARY).set_index("strategy")
    ledgers = []
    summaries = []

    for strategy in ["primary", "control"]:
        selected = pd.read_parquet(STEP7_DATA / f"{strategy}_selected_lots.parquet")
        records = build_trade_records(selected)
        expected_pnl = float(account_summary.loc[strategy, "total_pnl_usd"])
        if len(records) != int(account_summary.loc[strategy, "opened_trades"]):
            raise AssertionError("Trade count differs from Step 7")
        if not np.isclose(records.net_profit_usd.sum(), expected_pnl, rtol=1e-11, atol=1e-11):
            raise AssertionError("Trade PnL differs from final account PnL")
        records.to_parquet(DATA / f"{strategy}_trades.parquet", index=False)
        records.to_csv(DATA / f"{strategy}_trades.csv", index=False)
        ledgers.append(records)
        summaries.append({"strategy": strategy, **trade_record_summary(records)})

    combined = pd.concat(ledgers, ignore_index=True)
    combined.to_parquet(DATA / "all_trades.parquet", index=False)
    combined.to_csv(DATA / "all_trades.csv", index=False)
    summary = pd.DataFrame(summaries)
    summary.to_csv(RESULTS / "summary.csv", index=False)
    exit_reasons = (
        combined.groupby(["strategy", "exit_reason"], as_index=False)
        .agg(trades=("trade_id", "size"), net_profit_usd=("net_profit_usd", "sum"))
    )
    exit_reasons.to_csv(RESULTS / "exit_reasons.csv", index=False)

    validation = {
        "step": "stage2_step8_trade_records",
        "status": "PASS",
        "primary_trade_records": int((combined.strategy == "primary").sum()),
        "control_trade_records": int((combined.strategy == "control").sum()),
        "total_trade_records": len(combined),
        "duplicate_signal_ids": int(combined.signal_id.duplicated().sum()),
        "cash_flow_reconciliation": "PASS",
        "step7_trade_count_reconciliation": "PASS",
        "step7_final_pnl_reconciliation": "PASS",
    }
    (RESULTS / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    print(summary.to_string(index=False))
    print(exit_reasons.to_string(index=False))
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    run()

