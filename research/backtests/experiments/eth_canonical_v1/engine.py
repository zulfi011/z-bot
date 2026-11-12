"""One deterministic portfolio engine for all future ETH experiments.

The engine deliberately knows nothing about how a signal or exit was selected. It receives
fully causal candidate trades, applies the shared five-lot wallet in timestamp order, truncates
positions at the evaluation boundary, records blocked candidates, and marks equity hourly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from math import floor

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MarketData:
    times: pd.DatetimeIndex
    open: np.ndarray
    close: np.ndarray

    def __post_init__(self) -> None:
        if not (len(self.times) == len(self.open) == len(self.close)):
            raise ValueError("Market arrays must have identical lengths")
        if not self.times.is_monotonic_increasing or self.times.has_duplicates:
            raise ValueError("Market timestamps must be unique and increasing")


@dataclass(frozen=True)
class CandidateTrade:
    entry: int
    exit: int
    exit_price: float
    source: str
    exit_code: int
    candidate_id: str
    setup_episode: str | None = None
    market_episode: str | None = None
    exit_kind: str | None = None
    arm_index: int | None = None
    bullish_entry: bool | None = None


@dataclass(frozen=True)
class PortfolioConfig:
    initial_capital: float = 500.0
    lot_size: float = 100.0
    maximum_lots: int = 5
    fee_per_side: float = 7.5 / 10_000
    slippage_per_side: float = 2 / 10_000
    minimum_order_usd: float = 5.0
    mark_frequency_minutes: int = 60

    def __post_init__(self) -> None:
        if self.initial_capital <= 0 or self.lot_size <= 0 or self.maximum_lots <= 0:
            raise ValueError("Capital, lot size and lot count must be positive")
        if self.initial_capital + 1e-9 < self.lot_size * self.maximum_lots:
            raise ValueError("Initial capital must fund every configured lot")
        if min(self.fee_per_side, self.slippage_per_side) < 0:
            raise ValueError("Trading costs cannot be negative")
        if self.mark_frequency_minutes <= 0:
            raise ValueError("Mark frequency must be positive")


@dataclass(frozen=True)
class ReplayResult:
    summary: dict
    trades: pd.DataFrame
    blocked_signals: pd.DataFrame
    equity: pd.DataFrame


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "candidate_id", "source", "setup_episode", "market_episode", "exit_kind", "arm_index", "bullish_entry",
        "entry_index", "entry_time", "exit_index", "exit_time",
        "exit_code", "endpoint_closed", "spend", "entry_raw_price", "entry_fill_price",
        "quantity", "exit_raw_price", "exit_fill_price", "proceeds", "pnl", "return_pct",
        "minutes_held",
    ])


def _summary(ledger: pd.DataFrame, equity: pd.DataFrame, initial: float) -> dict:
    if ledger.empty:
        return {
            "initial_capital": initial, "ending_equity": initial, "net_profit": 0.0,
            "return_pct": 0.0, "trades": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0,
            "average_win": 0.0, "average_loss": 0.0, "profit_factor": None,
            "maximum_drawdown_pct": 0.0, "maximum_drawdown_usd": 0.0,
        }
    wins = ledger[ledger.pnl > 0]
    losses = ledger[ledger.pnl <= 0]
    gross_win = float(wins.pnl.sum())
    gross_loss = float(-losses.pnl.sum())
    net = float(ledger.pnl.sum())
    return {
        "initial_capital": initial,
        "ending_equity": initial + net,
        "net_profit": net,
        "return_pct": 100 * net / initial,
        "trades": int(len(ledger)),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
        "win_rate_pct": 100 * len(wins) / len(ledger),
        "average_win": float(wins.pnl.mean()) if len(wins) else 0.0,
        "average_loss": float(losses.pnl.mean()) if len(losses) else 0.0,
        "profit_factor": gross_win / gross_loss if gross_loss else None,
        "maximum_drawdown_pct": float(equity.drawdown_pct.min()) if len(equity) else 0.0,
        "maximum_drawdown_usd": float(equity.drawdown_usd.min()) if len(equity) else 0.0,
    }


def replay_portfolio(
    candidates: list[CandidateTrade],
    market: MarketData,
    start: pd.Timestamp,
    end: pd.Timestamp,
    config: PortfolioConfig,
    entry_policy: Callable[[CandidateTrade, list[dict], list[dict]], str | None] | None = None,
    lot_sizer: Callable[[CandidateTrade], float] | None = None,
    contextual_lot_sizer: Callable[[CandidateTrade, list[dict], list[dict]], float] | None = None,
) -> ReplayResult:
    """Replay a complete ETH portfolio inside the half-open interval ``[start, end)``.

    A position whose modeled exit lies outside the interval is liquidated at the final completed
    minute's close. Candidate ordering is stable, making same-minute allocation deterministic.
    """
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if lot_sizer is not None and contextual_lot_sizer is not None:
        raise ValueError("Use either lot_sizer or contextual_lot_sizer, not both")
    if start.tz is None or end.tz is None or start >= end:
        raise ValueError("Replay boundaries must be timezone-aware and increasing")
    first = int(market.times.searchsorted(start))
    stop = int(market.times.searchsorted(end))
    if first >= stop:
        raise ValueError("The requested window has no market data")
    last = stop - 1

    wallet = float(config.initial_capital)
    open_lots: list[dict] = []
    taken: list[dict] = []
    blocked: list[dict] = []

    ordered = sorted(enumerate(candidates), key=lambda pair: (pair[1].entry, pair[0]))
    for _, candidate in ordered:
        if candidate.entry < first or candidate.entry >= stop:
            continue
        matured = [lot for lot in open_lots if lot["exit_index"] <= candidate.entry]
        wallet += sum(lot["proceeds"] for lot in matured)
        open_lots = [lot for lot in open_lots if lot["exit_index"] > candidate.entry]

        if contextual_lot_sizer is not None:
            target_spend = float(contextual_lot_sizer(candidate, taken, open_lots))
        else:
            target_spend = float(lot_sizer(candidate) if lot_sizer is not None else config.lot_size)
        if not np.isfinite(target_spend) or target_spend <= 0:
            raise ValueError("A lot sizer must return a finite positive dollar amount")
        reason = None
        if len(open_lots) >= config.maximum_lots:
            reason = "all_slots_open"
        elif wallet < config.minimum_order_usd:
            reason = "insufficient_cash"
        elif entry_policy is not None:
            reason = entry_policy(candidate, taken, open_lots)
        if reason:
            hypothetical_exit = min(candidate.exit, last)
            hypothetical_raw = float(market.close[last]) if candidate.exit > last else candidate.exit_price
            hypothetical_spend = target_spend
            hypothetical_fill = float(market.open[candidate.entry]) * (1 + config.slippage_per_side)
            hypothetical_quantity = hypothetical_spend / (hypothetical_fill * (1 + config.fee_per_side))
            hypothetical_proceeds = (hypothetical_quantity * hypothetical_raw
                                     * (1 - config.slippage_per_side) * (1 - config.fee_per_side))
            open_details = [{
                "source": lot["source"], "age_minutes": candidate.entry - lot["entry_index"],
                "armed": bool(lot["arm_index"] is not None and lot["arm_index"] <= candidate.entry),
                "market_episode": lot["market_episode"],
            } for lot in open_lots]
            blocked.append({
                "candidate_id": candidate.candidate_id,
                "source": candidate.source,
                "entry_index": candidate.entry,
                "entry_time": market.times[candidate.entry],
                "reason": reason,
                "open_lots": len(open_lots),
                "free_cash": wallet,
                "open_positions": json.dumps(open_details, separators=(",", ":")),
                "hypothetical_exit_index": hypothetical_exit,
                "hypothetical_exit_time": market.times[hypothetical_exit],
                "hypothetical_pnl": hypothetical_proceeds - hypothetical_spend,
                "hypothetical_winner": hypothetical_proceeds > hypothetical_spend,
                "setup_episode": candidate.setup_episode,
                "market_episode": candidate.market_episode,
                "bullish_entry": candidate.bullish_entry,
                "duplicate_setup_episode": (any(lot["setup_episode"] == candidate.setup_episode for lot in taken)
                                            if candidate.setup_episode else False),
                "duplicate_market_episode": (any(lot["market_episode"] == candidate.market_episode for lot in taken)
                                             if candidate.market_episode else False),
            })
            continue

        spend = min(target_spend, floor(wallet * 100) / 100)
        if spend < config.minimum_order_usd:
            blocked.append({
                "candidate_id": candidate.candidate_id, "source": candidate.source,
                "entry_index": candidate.entry, "entry_time": market.times[candidate.entry],
                "reason": "below_minimum_order", "open_lots": len(open_lots), "free_cash": wallet,
                "open_positions": "[]", "hypothetical_exit_index": None,
                "hypothetical_exit_time": None, "hypothetical_pnl": None, "hypothetical_winner": None,
                "setup_episode": candidate.setup_episode, "market_episode": candidate.market_episode,
                "bullish_entry": candidate.bullish_entry,
                "duplicate_setup_episode": None, "duplicate_market_episode": None,
            })
            continue

        endpoint_closed = candidate.exit > last
        exit_index = last if endpoint_closed else candidate.exit
        exit_raw = float(market.close[last]) if endpoint_closed else float(candidate.exit_price)
        entry_raw = float(market.open[candidate.entry])
        entry_fill = entry_raw * (1 + config.slippage_per_side)
        quantity = spend / (entry_fill * (1 + config.fee_per_side))
        exit_fill = exit_raw * (1 - config.slippage_per_side)
        proceeds = quantity * exit_fill * (1 - config.fee_per_side)
        lot = {
            "candidate_id": candidate.candidate_id,
            "source": candidate.source,
            "setup_episode": candidate.setup_episode,
            "market_episode": candidate.market_episode,
            "exit_kind": candidate.exit_kind,
            "arm_index": candidate.arm_index,
            "bullish_entry": candidate.bullish_entry,
            "entry_index": candidate.entry,
            "entry_time": market.times[candidate.entry],
            "exit_index": exit_index,
            "exit_time": market.times[exit_index],
            "exit_code": candidate.exit_code,
            "endpoint_closed": endpoint_closed,
            "spend": spend,
            "entry_raw_price": entry_raw,
            "entry_fill_price": entry_fill,
            "quantity": quantity,
            "exit_raw_price": exit_raw,
            "exit_fill_price": exit_fill,
            "proceeds": proceeds,
            "pnl": proceeds - spend,
            "return_pct": 100 * (proceeds / spend - 1),
            "minutes_held": exit_index - candidate.entry,
        }
        wallet -= spend
        open_lots.append(lot)
        taken.append(lot)

    wallet += sum(lot["proceeds"] for lot in open_lots)
    ledger = pd.DataFrame(taken) if taken else _empty_trades()
    blocked_frame = pd.DataFrame(blocked, columns=[
        "candidate_id", "source", "entry_index", "entry_time", "reason", "open_lots", "free_cash",
        "open_positions", "hypothetical_exit_index", "hypothetical_exit_time", "hypothetical_pnl",
        "hypothetical_winner", "setup_episode", "market_episode", "bullish_entry",
        "duplicate_setup_episode", "duplicate_market_episode",
    ])

    marks = np.arange(first, stop, config.mark_frequency_minutes, dtype=np.int64)
    equity_values = np.full(len(marks), config.initial_capital, dtype=float)
    for lot in taken:
        entry_mark = int(np.searchsorted(marks, lot["entry_index"]))
        exit_mark = int(np.searchsorted(marks, lot["exit_index"]))
        equity_values[exit_mark:] += lot["pnl"]
        if exit_mark > entry_mark:
            marked_exit_value = (
                lot["quantity"] * market.close[marks[entry_mark:exit_mark]]
                * (1 - config.slippage_per_side) * (1 - config.fee_per_side)
            )
            equity_values[entry_mark:exit_mark] += marked_exit_value - lot["spend"]
    peaks = np.maximum.accumulate(equity_values) if len(equity_values) else np.array([], dtype=float)
    equity = pd.DataFrame({
        "timestamp": market.times[marks],
        "equity": equity_values,
        "peak_equity": peaks,
        "drawdown_usd": equity_values - peaks,
        "drawdown_pct": np.where(peaks > 0, 100 * (equity_values / peaks - 1), 0.0),
    })
    summary = _summary(ledger, equity, config.initial_capital)
    summary["blocked_candidates"] = int(len(blocked_frame))
    summary["endpoint_closed_trades"] = int(ledger.endpoint_closed.sum()) if len(ledger) else 0
    summary["candidate_count"] = int(sum(first <= c.entry < stop for c in candidates))
    summary["ending_wallet"] = wallet
    return ReplayResult(summary, ledger, blocked_frame, equity)
