"""Performance metrics derived from reconciled trades and account equity."""

from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_performance(
    trades: pd.DataFrame,
    account_curve: pd.DataFrame,
    initial_equity_usd: float,
) -> dict:
    """Calculate portfolio and trade metrics without altering source data."""
    trade_columns = ["trade_id", "net_profit_usd", "net_return_pct"]
    curve_columns = ["timestamp", "total_equity_usd", "drawdown_pct"]
    missing = [c for c in trade_columns if c not in trades]
    if missing:
        raise ValueError(f"Missing trade columns: {missing}")
    missing = [c for c in curve_columns if c not in account_curve]
    if missing:
        raise ValueError(f"Missing account columns: {missing}")
    if trades.empty or account_curve.empty or initial_equity_usd <= 0:
        raise ValueError("Trades, account curve, and positive initial equity are required")

    pnl = trades.net_profit_usd.astype(float)
    returns = trades.net_return_pct.astype(float)
    wins = pnl > 0
    losses = pnl < 0
    gross_profit = float(pnl[wins].sum())
    gross_loss = float(abs(pnl[losses].sum()))
    profit_factor = gross_profit / gross_loss if gross_loss else np.inf

    curve = account_curve.reset_index(drop=True)
    trough_index = int(curve.drawdown_pct.idxmin())
    peak_index = int(curve.loc[:trough_index, "total_equity_usd"].idxmax())
    peak_equity = float(curve.loc[peak_index, "total_equity_usd"])
    trough_equity = float(curve.loc[trough_index, "total_equity_usd"])
    after_trough = curve.loc[trough_index + 1:]
    recovered = after_trough.loc[after_trough.total_equity_usd >= peak_equity]
    recovery_timestamp = None if recovered.empty else recovered.timestamp.iloc[0]
    worst_index = int(pnl.idxmin())

    final_equity = float(curve.total_equity_usd.iloc[-1])
    if not np.isclose(final_equity - initial_equity_usd, pnl.sum(), rtol=1e-11, atol=1e-11):
        raise AssertionError("Trade PnL does not reconcile to final equity")
    return {
        "initial_equity_usd": initial_equity_usd,
        "final_equity_usd": final_equity,
        "total_pnl_usd": final_equity - initial_equity_usd,
        "total_return_pct": (final_equity / initial_equity_usd - 1) * 100,
        "trades": len(trades),
        "wins": int(wins.sum()),
        "losses": int(losses.sum()),
        "breakeven_trades": int((pnl == 0).sum()),
        "win_rate_pct": float(wins.mean() * 100),
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
        "profit_factor": profit_factor,
        "average_trade_pnl_usd": float(pnl.mean()),
        "average_trade_return_pct": float(returns.mean()),
        "median_trade_return_pct": float(returns.median()),
        "worst_trade_id": trades.loc[worst_index, "trade_id"],
        "worst_trade_pnl_usd": float(pnl.loc[worst_index]),
        "worst_trade_return_pct": float(returns.loc[worst_index]),
        "max_drawdown_pct": float(curve.loc[trough_index, "drawdown_pct"]),
        "max_drawdown_usd": trough_equity - peak_equity,
        "drawdown_peak_timestamp": curve.loc[peak_index, "timestamp"],
        "drawdown_trough_timestamp": curve.loc[trough_index, "timestamp"],
        "drawdown_recovery_timestamp": recovery_timestamp,
        "drawdown_recovered": recovery_timestamp is not None,
        "lowest_equity_usd": float(curve.total_equity_usd.min()),
    }


def daily_equity_curve(account_curve: pd.DataFrame) -> pd.DataFrame:
    """Return the final account snapshot for every UTC calendar day."""
    columns = [
        "timestamp", "cash_usd", "open_position_value_usd", "realized_pnl_usd",
        "unrealized_pnl_usd", "total_equity_usd", "drawdown_pct", "open_positions",
    ]
    missing = [c for c in columns if c not in account_curve]
    if missing:
        raise ValueError(f"Missing daily-equity columns: {missing}")
    return (
        account_curve[columns].set_index("timestamp").resample("1D").last()
        .dropna().reset_index()
    )

