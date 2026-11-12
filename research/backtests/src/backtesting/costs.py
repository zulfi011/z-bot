"""Apply explicit spot fees to already-slipped entry and exit fills."""

from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = [
    "raw_entry_open",
    "entry_fill",
    "raw_exit_price",
    "exit_fill",
    "return_after_slippage_pct",
]


def apply_costs(trades: pd.DataFrame, fee_bps_per_side: float) -> pd.DataFrame:
    """Return per-unit cash flows and returns after entry and exit fees.

    Slippage is already embedded in ``entry_fill`` and ``exit_fill``. Fees are
    charged on each slipped fill, matching spot quote-currency cash flows.
    """
    missing = [column for column in REQUIRED_COLUMNS if column not in trades]
    if missing:
        raise ValueError(f"Missing cost columns: {missing}")
    if fee_bps_per_side < 0:
        raise ValueError("Fee rate cannot be negative")
    output = trades.copy()
    prices = output[REQUIRED_COLUMNS[:4]].to_numpy(float)
    if not np.isfinite(prices).all() or not (prices > 0).all():
        raise ValueError("Trade prices must be finite and positive")

    fee_rate = fee_bps_per_side / 10_000
    output["fee_bps_per_side"] = fee_bps_per_side
    output["entry_fee_per_unit"] = output.entry_fill * fee_rate
    output["exit_fee_per_unit"] = output.exit_fill * fee_rate
    output["total_fees_per_unit"] = output.entry_fee_per_unit + output.exit_fee_per_unit
    output["entry_slippage_per_unit"] = output.entry_fill - output.raw_entry_open
    output["exit_slippage_per_unit"] = output.raw_exit_price - output.exit_fill
    output["total_slippage_per_unit"] = (
        output.entry_slippage_per_unit + output.exit_slippage_per_unit
    )
    output["entry_cash_out_per_unit"] = output.entry_fill + output.entry_fee_per_unit
    output["exit_cash_in_per_unit"] = output.exit_fill - output.exit_fee_per_unit
    output["net_pnl_per_unit"] = output.exit_cash_in_per_unit - output.entry_cash_out_per_unit
    output["gross_raw_return_pct"] = (
        output.raw_exit_price / output.raw_entry_open - 1
    ) * 100
    recomputed_slippage_return = (output.exit_fill / output.entry_fill - 1) * 100
    if not np.allclose(
        recomputed_slippage_return,
        output.return_after_slippage_pct,
        rtol=1e-12,
        atol=1e-12,
    ):
        raise ValueError("Stored slippage return does not match fill prices")
    output["net_return_pct"] = (
        output.exit_cash_in_per_unit / output.entry_cash_out_per_unit - 1
    ) * 100
    output["slippage_drag_pct_points"] = (
        output.return_after_slippage_pct - output.gross_raw_return_pct
    )
    output["fee_drag_pct_points"] = output.net_return_pct - output.return_after_slippage_pct
    output["total_execution_drag_pct_points"] = (
        output.net_return_pct - output.gross_raw_return_pct
    )
    return output

