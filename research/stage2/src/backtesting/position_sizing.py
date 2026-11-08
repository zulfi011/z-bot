"""Spot-only position sizing and realized trade-level equity simulation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SizingSpec:
    name: str
    method: str
    value: float

    def __post_init__(self):
        if self.method not in {"fixed_capital", "equity_fraction", "risk_fraction"}:
            raise ValueError(f"Unsupported sizing method: {self.method}")
        if self.value <= 0:
            raise ValueError("Sizing value must be positive")
        if self.method in {"equity_fraction", "risk_fraction"} and self.value > 1:
            raise ValueError("Fractional sizing values cannot exceed one")


def planned_stop_loss_fraction(stop_pct: float, fee_bps_per_side: float,
                               exit_slippage_bps: float) -> float:
    """Cash loss fraction if the planned stop fills without an adverse gap."""
    if stop_pct <= 0 or stop_pct >= 100 or fee_bps_per_side < 0 or exit_slippage_bps < 0:
        raise ValueError("Invalid stop or cost assumption")
    fee = fee_bps_per_side / 10_000
    slip = exit_slippage_bps / 10_000
    exit_cash_multiple = (1 - stop_pct / 100) * (1 - slip) * (1 - fee)
    entry_cash_multiple = 1 + fee
    loss = 1 - exit_cash_multiple / entry_cash_multiple
    if not 0 < loss < 1:
        raise ValueError("Planned stop loss fraction is invalid")
    return loss


def allocation_for_trade(equity: float, spec: SizingSpec,
                         stop_loss_fraction: float) -> float:
    if not np.isfinite(equity) or equity <= 0:
        raise ValueError("Equity must be finite and positive")
    if spec.method == "fixed_capital":
        requested = spec.value
    elif spec.method == "equity_fraction":
        requested = equity * spec.value
    else:
        requested = equity * spec.value / stop_loss_fraction
    return min(requested, equity)


def simulate_position_sizing(trades: pd.DataFrame, spec: SizingSpec,
                             initial_equity: float, stop_loss_fraction: float) -> pd.DataFrame:
    required = [
        "signal_id", "strategy", "entry_timestamp", "exit_timestamp",
        "entry_cash_out_per_unit", "exit_cash_in_per_unit", "net_pnl_per_unit",
        "net_return_pct", "entry_fee_per_unit", "exit_fee_per_unit",
        "total_slippage_per_unit",
    ]
    missing = [column for column in required if column not in trades]
    if missing:
        raise ValueError(f"Missing position-sizing columns: {missing}")
    if initial_equity <= 0 or stop_loss_fraction <= 0:
        raise ValueError("Initial equity and stop loss must be positive")
    ordered = trades.sort_values("entry_timestamp").reset_index(drop=True)
    if len(ordered) > 1 and not bool((
        ordered.entry_timestamp.iloc[1:].reset_index(drop=True)
        >= ordered.exit_timestamp.iloc[:-1].reset_index(drop=True)
    ).all()):
        raise ValueError("Trades overlap")

    equity = float(initial_equity)
    peak = equity
    rows = []
    for trade in ordered.itertuples(index=False):
        allocation = allocation_for_trade(equity, spec, stop_loss_fraction)
        quantity = allocation / trade.entry_cash_out_per_unit
        cash_reserve = equity - allocation
        exit_proceeds = quantity * trade.exit_cash_in_per_unit
        pnl = exit_proceeds - allocation
        equity_after = cash_reserve + exit_proceeds
        if allocation > equity + 1e-12 or cash_reserve < -1e-12 or quantity < 0:
            raise AssertionError("Spot allocation exceeded available equity")
        if not np.isclose(pnl, quantity * trade.net_pnl_per_unit, rtol=1e-12, atol=1e-12):
            raise AssertionError("PnL cash-flow reconciliation failed")
        peak = max(peak, equity_after)
        drawdown = (equity_after / peak - 1) * 100
        rows.append({
            "signal_id": trade.signal_id,
            "strategy": trade.strategy,
            "entry_timestamp": trade.entry_timestamp,
            "exit_timestamp": trade.exit_timestamp,
            "sizing_name": spec.name,
            "sizing_method": spec.method,
            "sizing_value": spec.value,
            "equity_before_usd": equity,
            "allocation_usd": allocation,
            "allocation_pct_of_equity": allocation / equity * 100,
            "cash_reserve_usd": cash_reserve,
            "asset_quantity": quantity,
            "entry_fees_usd": quantity * trade.entry_fee_per_unit,
            "exit_fees_usd": quantity * trade.exit_fee_per_unit,
            "slippage_cost_usd": quantity * trade.total_slippage_per_unit,
            "net_return_pct": trade.net_return_pct,
            "net_pnl_usd": pnl,
            "equity_after_usd": equity_after,
            "realized_equity_peak_usd": peak,
            "realized_drawdown_pct": drawdown,
        })
        equity = equity_after
    return pd.DataFrame(rows)


def sizing_metrics(path: pd.DataFrame, initial_equity: float) -> dict[str, float | int]:
    pnl = path.net_pnl_usd
    positive = pnl[pnl > 0].sum()
    negative = abs(pnl[pnl < 0].sum())
    return {
        "trades": len(path),
        "final_equity_usd": path.equity_after_usd.iloc[-1],
        "total_pnl_usd": path.equity_after_usd.iloc[-1] - initial_equity,
        "total_return_pct": (path.equity_after_usd.iloc[-1] / initial_equity - 1) * 100,
        "max_realized_drawdown_pct": path.realized_drawdown_pct.min(),
        "max_realized_drawdown_usd": (
            path.equity_after_usd - path.realized_equity_peak_usd
        ).min(),
        "worst_trade_pnl_usd": pnl.min(),
        "mean_allocation_usd": path.allocation_usd.mean(),
        "mean_allocation_pct": path.allocation_pct_of_equity.mean(),
        "total_fees_usd": (path.entry_fees_usd + path.exit_fees_usd).sum(),
        "total_slippage_usd": path.slippage_cost_usd.sum(),
        "dollar_profit_factor": positive / negative,
        "cash_cap_uses": int(np.isclose(path.allocation_usd, path.equity_before_usd).sum()),
    }

