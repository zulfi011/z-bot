"""Pure frozen-strategy paper fill, exit, and sizing rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


HUNDRED = Decimal("100")
TEN_THOUSAND = Decimal("10000")


@dataclass(frozen=True)
class ExecutionConfig:
    initial_equity: Decimal
    equity_fraction: Decimal
    maximum_positions: int
    fee_bps: Decimal
    slippage_bps: Decimal
    stop_pct: Decimal
    trail_activation_pct: Decimal
    trail_giveback_pct: Decimal
    maximum_hold_minutes: int

    @classmethod
    def from_strategy(cls, strategy: dict) -> "ExecutionConfig":
        portfolio = strategy["portfolio"]
        execution = strategy["execution_model"]
        exit_rules = strategy["exit"]
        trailing = exit_rules["trailing_stop"]
        return cls(
            initial_equity=Decimal(str(portfolio["initial_paper_equity_usd"])),
            equity_fraction=Decimal(str(portfolio["equity_fraction_per_entry"])),
            maximum_positions=int(portfolio["maximum_open_positions"]),
            fee_bps=Decimal(str(execution["fee_bps_per_side"])),
            slippage_bps=Decimal(str(execution["slippage_bps_per_side"])),
            stop_pct=Decimal(str(exit_rules["protective_stop_pct_from_entry_fill"])),
            trail_activation_pct=Decimal(str(trailing["activation_pct_from_entry_fill"])),
            trail_giveback_pct=Decimal(str(trailing["giveback_of_open_profit_pct"])),
            maximum_hold_minutes=int(exit_rules["maximum_hold_minutes"]),
        )


@dataclass(frozen=True)
class Candle:
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    @property
    def exit_time(self) -> datetime:
        return self.open_time + timedelta(minutes=1)


@dataclass
class Position:
    position_id: str
    signal_id: str
    entry_time: datetime
    raw_entry_price: Decimal
    entry_fill_price: Decimal
    quantity: Decimal
    allocation_usd: Decimal
    entry_fee_usd: Decimal
    strategy_id: str = ""
    symbol: str = ""
    bars_held: int = 0
    trailing_active: bool = False
    peak_price: Decimal | None = None


@dataclass(frozen=True)
class EntryFill:
    fill_price: Decimal
    quantity: Decimal
    notional_usd: Decimal
    fee_usd: Decimal
    slippage_usd: Decimal
    allocation_usd: Decimal


@dataclass(frozen=True)
class ExitFill:
    reason: str
    raw_price: Decimal
    fill_price: Decimal
    fee_usd: Decimal
    slippage_usd: Decimal
    cash_in_usd: Decimal
    net_pnl_usd: Decimal
    net_return_pct: Decimal
    exit_time: datetime
    duration_minutes: int


@dataclass(frozen=True)
class AccountMark:
    open_position_value_usd: Decimal
    open_position_cost_usd: Decimal
    unrealized_pnl_usd: Decimal
    total_equity_usd: Decimal
    total_pnl_usd: Decimal
    return_pct: Decimal
    equity_peak_usd: Decimal
    drawdown_pct: Decimal


def create_entry(raw_open: Decimal, allocation: Decimal, config: ExecutionConfig) -> EntryFill:
    fill = raw_open * (Decimal("1") + config.slippage_bps / TEN_THOUSAND)
    cash_per_unit = fill * (Decimal("1") + config.fee_bps / TEN_THOUSAND)
    quantity = allocation / cash_per_unit
    notional = quantity * fill
    fee = notional * config.fee_bps / TEN_THOUSAND
    return EntryFill(
        fill_price=fill,
        quantity=quantity,
        notional_usd=notional,
        fee_usd=fee,
        slippage_usd=quantity * (fill - raw_open),
        allocation_usd=notional + fee,
    )


def _exit(position: Position, candle: Candle, raw_price: Decimal, reason: str,
          config: ExecutionConfig) -> ExitFill:
    fill = raw_price * (Decimal("1") - config.slippage_bps / TEN_THOUSAND)
    notional = position.quantity * fill
    fee = notional * config.fee_bps / TEN_THOUSAND
    cash_in = notional - fee
    pnl = cash_in - position.allocation_usd
    return ExitFill(
        reason=reason,
        raw_price=raw_price,
        fill_price=fill,
        fee_usd=fee,
        slippage_usd=position.quantity * (raw_price - fill),
        cash_in_usd=cash_in,
        net_pnl_usd=pnl,
        net_return_pct=pnl / position.allocation_usd * HUNDRED,
        exit_time=candle.exit_time,
        duration_minutes=position.bars_held,
    )


def evaluate_exit(position: Position, candle: Candle, config: ExecutionConfig) -> ExitFill | None:
    """Advance one lot through one completed minute, matching Stage 2 exactly."""
    position.bars_held += 1
    hard_stop = position.entry_fill_price * (Decimal("1") - config.stop_pct / HUNDRED)

    if not position.trailing_active:
        activation = position.entry_fill_price * (
            Decimal("1") + config.trail_activation_pct / HUNDRED
        )
        activation_hit = candle.high >= activation
        stop_hit = candle.low <= hard_stop
        if stop_hit:
            reason = "ambiguous_stop" if activation_hit else "protective_stop"
            return _exit(position, candle, min(hard_stop, candle.open), reason, config)
        if activation_hit:
            position.trailing_active = True
            position.peak_price = max(position.entry_fill_price, candle.high)
    else:
        if position.peak_price is None:
            raise ValueError("Active trailing position has no peak price")
        trail = position.entry_fill_price + (
            position.peak_price - position.entry_fill_price
        ) * (Decimal("1") - config.trail_giveback_pct / HUNDRED)
        if candle.low <= trail:
            return _exit(position, candle, min(trail, candle.open), "trailing_stop", config)
        position.peak_price = max(position.peak_price, candle.high)

    if position.bars_held >= config.maximum_hold_minutes:
        return _exit(position, candle, candle.close, "time", config)
    return None


def mark_account(
    initial_equity: Decimal,
    cash: Decimal,
    positions: list[Position],
    close_price: Decimal | dict[str, Decimal],
    realized_pnl: Decimal,
    previous_peak: Decimal,
) -> AccountMark:
    def price_for(position: Position) -> Decimal:
        if isinstance(close_price, dict):
            return close_price[position.symbol]
        return close_price

    open_value = sum(
        (position.quantity * price_for(position) for position in positions), Decimal("0")
    )
    open_cost = sum((position.allocation_usd for position in positions), Decimal("0"))
    unrealized = open_value - open_cost
    equity = cash + open_value
    total_pnl = equity - initial_equity
    if total_pnl != realized_pnl + unrealized:
        raise ValueError("Account identity failed: total PnL differs from realized plus unrealized PnL")
    peak = max(previous_peak, equity)
    return AccountMark(
        open_position_value_usd=open_value,
        open_position_cost_usd=open_cost,
        unrealized_pnl_usd=unrealized,
        total_equity_usd=equity,
        total_pnl_usd=total_pnl,
        return_pct=total_pnl / initial_equity * HUNDRED,
        equity_peak_usd=peak,
        drawdown_pct=(equity / peak - Decimal("1")) * HUNDRED,
    )


def evaluate_manual_close(position: Position, candle: Candle, config: ExecutionConfig,
                          requested_at: datetime) -> ExitFill | None:
    """Fill at the first completed minute after the request, never in historical catch-up."""
    if candle.exit_time <= requested_at:
        return None
    return _exit(position, candle, candle.close, "manual_close", config)
