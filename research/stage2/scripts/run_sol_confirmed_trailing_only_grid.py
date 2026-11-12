"""Grid-test confirmed SOL touches whose only exit is a profit trailing stop."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from run_sol_immediate_trail_experiment import generate_fills  # noqa: E402
from run_sol_trailing_only_grid import marked_curve, run_combination  # noqa: E402


EXPERIMENT_ID = "sol_15d_confirmed_trailing_only_grid_v1"
RESULT_DIR = ROOT / "results" / EXPERIMENT_ID
DATA_DIR = ROOT / "data" / EXPERIMENT_ID
CONFIG_PATH = ROOT / "config/experiments" / f"{EXPERIMENT_ID}.json"
RAW_PATH = PROJECT / "stage1/data/raw/SOLUSDT/SOLUSDT_1m.parquet"
SIGNAL_PATH = PROJECT / "stage1/data/processed/SOLUSDT/SOLUSDT_3m_with_averages.parquet"
ACTIVATIONS = [0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
GIVEBACKS = [10.0, 15.0, 20.0]


def main() -> None:
    raw = pd.read_parquet(RAW_PATH, columns=["open_time", "open", "high", "low", "close"])
    signal = pd.read_parquet(SIGNAL_PATH, columns=[
        "open_time", "open", "high", "low", "close",
        "average_7d", "average_15d", "average_30d",
    ])
    fills, diagnostics = generate_fills(signal, slippage_bps=2.0)
    fills = fills.rename(columns={
        "start_timestamp": "touch_timestamp",
        "fill_price": "entry_fill",
    })

    rows = []
    outputs = {}
    for activation in ACTIVATIONS:
        for giveback in GIVEBACKS:
            ledger, open_position, stats = run_combination(
                fills, raw, activation, giveback
            )
            rows.append(stats)
            outputs[(activation, giveback)] = (ledger, open_position)

    leaderboard = pd.DataFrame(rows).sort_values(
        ["ending_marked_equity_usd", "realized_equity_usd"], ascending=False
    ).reset_index(drop=True)
    leaderboard.insert(0, "rank", np.arange(1, len(leaderboard) + 1))
    best = leaderboard.iloc[0].to_dict()
    key = (float(best["activation_pct"]), float(best["giveback_pct_of_open_profit"]))
    best_ledger, best_open = outputs[key]
    curve = marked_curve(best_ledger, best_open, raw)
    best["maximum_mark_to_market_drawdown_pct"] = float(curve.drawdown_pct.min())
    best["lowest_marked_equity_usd"] = float(curve.marked_equity_usd.min())
    best["entry_diagnostics"] = diagnostics
    best["data_start_utc"] = str(curve.timestamp.iloc[0])
    best["data_end_utc"] = str(curve.timestamp.iloc[-1])
    if best_open is not None:
        best["open_position"] = {
            name: (str(value) if isinstance(value, pd.Timestamp) else value)
            for name, value in best_open.items()
            if name != "quantity"
        }

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    leaderboard.to_csv(RESULT_DIR / "leaderboard.csv", index=False)
    best_ledger.to_csv(DATA_DIR / "best_completed_trade_ledger.csv", index=False)
    best_ledger.to_parquet(DATA_DIR / "best_completed_trade_ledger.parquet", index=False)
    curve.to_parquet(DATA_DIR / "best_marked_account_curve_1m.parquet", index=False)
    (RESULT_DIR / "best_result.json").write_text(json.dumps(best, indent=2) + "\n")

    config = {
        "experiment_id": EXPERIMENT_ID,
        "status": "historical_grid_not_deployed",
        "entry": {
            "signal_timeframe": "3m",
            "average": "15d SMA from completed UTC daily closes",
            "touch_zone_pct": 0.2,
            "approach": "from_below",
            "confirmation": "first bullish 3m candle within 30 minutes",
            "fill": "raw 1m open at confirmation close boundary",
            "market_filter": "reject 7d < 15d < 30d",
        },
        "exit": {
            "only_permitted_exit": "trailing_stop",
            "hard_stop": None,
            "maximum_hold": None,
            "activation_pct_from_entry_fill_grid": ACTIVATIONS,
            "giveback_pct_of_peak_open_profit_grid": GIVEBACKS,
            "zero_activation_meaning": "activate on first post-entry high at or above entry fill",
            "activation_candle_can_exit": False,
            "trail_uses_prior_completed_1m_peak": True,
        },
        "portfolio": {
            "initial_equity_usd": 100,
            "maximum_positions": 1,
            "allocation_pct": 100,
            "signals_while_open": "ignore",
        },
        "costs": {"fee_bps_per_side": 10, "slippage_bps_per_side": 2},
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")

    table_lines = [
        "| Rank | Activate | Giveback | Completed | Wins | Losses | Win rate | Open | Final marked $100 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in leaderboard.itertuples(index=False):
        activation_label = "Immediate" if row.activation_pct == 0 else f"+{row.activation_pct:g}%"
        table_lines.append(
            f"| {row.rank} | {activation_label} | {row.giveback_pct_of_open_profit:g}% | "
            f"{row.completed_trades} | {row.wins_after_costs} | {row.losses_after_costs} | "
            f"{row.win_rate_after_costs_pct:.2f}% | {row.open_position_at_data_end} | "
            f"${row.ending_marked_equity_usd:.2f} |"
        )
    best_activation = "Immediate" if best["activation_pct"] == 0 else f"+{best['activation_pct']:g}%"
    open_note = (
        f"The final position remains open from **{best_open['entry_timestamp']}**, entered with "
        f"**${best_open['entry_equity_usd']:.2f}**, and is worth **${best_open['marked_value_usd']:.2f}** "
        "at the final historical close."
        if best_open is not None else "The best combination has no position open at data end."
    )
    report = f"""# SOL Confirmed Touch with Trailing-Only Exits

## Rules tested

The strategy waits for the existing bullish confirmation after a ±0.2% 15-day-average touch from below and buys at the raw one-minute open on the confirmation boundary. One position uses 100% of current equity. There is no hard stop and no time exit. The only permitted sale is a trailing stop after immediate/0% or +1% through +4% activation. The trail gives back 10%, 15%, or 20% of peak open profit. Fees and slippage remain 10 bps and 2 bps per side.

## Best full-history marked result

- Activation: **{best_activation}**
- Giveback of peak open profit: **{best['giveback_pct_of_open_profit']:g}%**
- Completed trades: **{best['completed_trades']}**
- Wins / losses after costs: **{best['wins_after_costs']} / {best['losses_after_costs']}**
- Completed-trade win rate: **{best['win_rate_after_costs_pct']:.2f}%**
- Realized equity before the final open position: **${best['realized_equity_usd']:.2f}**
- Final marked equity: **${best['ending_marked_equity_usd']:.2f}**
- Marked return: **{best['marked_total_return_pct']:+.2f}%**
- Maximum minute-marked drawdown: **{best['maximum_mark_to_market_drawdown_pct']:.2f}%**

{open_note}

## All 24 combinations

{chr(10).join(table_lines)}

## Measurement rule

Completed-trade win rate excludes the final open position. Because no loss or time exit is allowed, a position that never reaches activation remains invested indefinitely and blocks every later signal. Final ranking uses its marked value at the last SOL close; it does not fabricate a sale.
"""
    (RESULT_DIR / "REPORT.md").write_text(report)
    print(json.dumps(best, indent=2))
    print("\n" + leaderboard.to_string(index=False))


if __name__ == "__main__":
    main()
