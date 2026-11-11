"""Pure paper-trading rules: lot sizing, fills, BNB/USDT fees, exits, marking."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import Decimal


# How a lot was opened. "signal" is the dip rule, "breakout" is Mode C, "manual" is a button press; "pullback"
# and "pyramid" are the two extra ways in, each of which can be switched on or off. Every way in draws from the
# SAME set of lots, first come first served - there are no reserved lots.
DIP = "dip"
BREAKOUT = "breakout"
PULLBACK = "pullback"
PYRAMID = "pyramid"
# Every way in can be switched off per coin. The dip and the breakout start on (they are the tested core).
MODULES = (DIP, BREAKOUT, PULLBACK, PYRAMID)
# The dip's lots are recorded as "signal"; every other way in uses its own name.
MODULE_OF_SOURCE = {"signal": DIP}

HUNDRED = Decimal("100")
TEN_THOUSAND = Decimal("10000")
ZERO = Decimal("0")


@dataclass(frozen=True)
class ExecutionConfig:
    """Fees and exits. Lot sizing lives in CoinAllocation so it can be changed live."""
    usdt_fee_bps: Decimal
    bnb_fee_bps: Decimal
    slippage_bps: Decimal
    stop_pct: Decimal
    trail_activation_pct: Decimal
    trail_giveback_pct: Decimal
    maximum_hold_minutes: int | None = None
    # Trend exit: once the trail has armed, hold while price stays above an EMA of the last
    # `trend_exit_ema_minutes` minutes instead of giving back a share of the open profit.
    trend_exit_ema_minutes: int | None = None
    trend_exit_requires_uptrend: bool = True
    # Mode C lots break out of a tighter band than a dip buys into, so they carry their own stop and trail.
    breakout_stop_pct: Decimal | None = None
    breakout_activation_pct: Decimal | None = None
    breakout_giveback_pct: Decimal | None = None

    @classmethod
    def from_strategy(cls, strategy: dict) -> "ExecutionConfig":
        execution = strategy["execution_model"]
        exit_rules = strategy["exit"]
        trailing = exit_rules["trailing_stop"]
        hold = exit_rules.get("maximum_hold_minutes")
        trend = exit_rules.get("trend_exit") or {}
        breakout = ((strategy.get("entry") or {}).get("consolidation_breakout") or {}).get("exit")
        return cls(
            usdt_fee_bps=Decimal(str(execution["usdt_fee_bps_per_side"])),
            bnb_fee_bps=Decimal(str(execution["bnb_fee_bps_per_side"])),
            slippage_bps=Decimal(str(execution["slippage_bps_per_side"])),
            stop_pct=Decimal(str(exit_rules["protective_stop_pct_from_entry_fill"])),
            trail_activation_pct=Decimal(str(trailing["activation_pct_from_entry_fill"])),
            trail_giveback_pct=Decimal(str(trailing["giveback_of_open_profit_pct"])),
            maximum_hold_minutes=int(hold) if hold is not None else None,
            trend_exit_ema_minutes=int(trend["ema_minutes"]) if trend.get("ema_minutes") else None,
            trend_exit_requires_uptrend=bool(trend.get("requires_uptrend", True)),
            breakout_stop_pct=Decimal(str(breakout["protective_stop_pct_from_entry_fill"])) if breakout else None,
            breakout_activation_pct=Decimal(str(breakout["activation_pct_from_entry_fill"])) if breakout else None,
            breakout_giveback_pct=Decimal(str(breakout["giveback_of_open_profit_pct"])) if breakout else None,
        )

    @property
    def break_even_floor_pct(self) -> Decimal:
        """How far above the fill a lot must sell to come out level: both sides' fee and slippage.

        Once a Mode A lot arms, its stop is lifted to this level, so a lot that has already proved itself and
        then comes all the way back cannot finish under water. It is derived from the fee schedule rather than
        chosen, so there is no number here to tune.
        """
        return (self.bnb_fee_bps + self.slippage_bps) * 2 / HUNDRED

    def for_source(self, entry_source: str) -> "ExecutionConfig":
        """The exit numbers this lot lives by. A Mode C lot uses its own; everything else uses the dip's."""
        if entry_source != BREAKOUT or self.breakout_stop_pct is None:
            return self
        return replace(self, stop_pct=self.breakout_stop_pct,
                       trail_activation_pct=self.breakout_activation_pct,
                       trail_giveback_pct=self.breakout_giveback_pct)


@dataclass(frozen=True)
class AllocationLimits:
    minimum_lot_usd: Decimal
    maximum_lot_usd: Decimal
    maximum_lots: int

    @classmethod
    def from_strategy(cls, strategy: dict) -> "AllocationLimits":
        portfolio = strategy["portfolio"]
        return cls(Decimal(str(portfolio["minimum_lot_size_usd"])), Decimal(str(portfolio["maximum_lot_size_usd"])),
                   int(portfolio["maximum_lots_per_coin"]))


@dataclass(frozen=True)
class CoinAllocation:
    """How much of the account a coin may use: `lots` lots of `lot_size_usd`, shared by every way in.

    There are no reserved lots. The dip, Mode C, the pullback and the pyramid adds all draw from the same set,
    first come first served, and `entries` simply says which of the optional ways in are switched on.
    """
    lot_size_usd: Decimal
    lots: int
    entries: frozenset = field(default_factory=frozenset)

    def enabled(self, source: str) -> bool:
        return source in self.entries

    def allows(self, entry_source: str) -> bool:
        """May this way in open a lot at all?"""
        module = MODULE_OF_SOURCE.get(entry_source, entry_source)
        return module not in MODULES or module in self.entries

    def only_supported(self, supported: Mapping) -> "CoinAllocation":
        """The same allocation with any way in the coin's strategy does not have switched off."""
        return CoinAllocation(self.lot_size_usd, self.lots,
                              frozenset(name for name in self.entries if supported.get(name)))

    @property
    def target_capital_usd(self) -> Decimal:
        return self.lot_size_usd * self.lots

    @classmethod
    def default(cls, strategy: dict) -> "CoinAllocation":
        portfolio = strategy["portfolio"]
        return cls(Decimal(str(portfolio["default_lot_size_usd"])), int(portfolio["default_lots"]),
                   frozenset({DIP, BREAKOUT, PULLBACK}))


def validate_allocation(allocation: CoinAllocation, limits: AllocationLimits) -> list[str]:
    problems = []
    if allocation.lot_size_usd != allocation.lot_size_usd.quantize(Decimal("0.01")):
        problems.append("Lot size can have at most 2 decimals")
    if not limits.minimum_lot_usd <= allocation.lot_size_usd <= limits.maximum_lot_usd:
        problems.append(f"Lot size must be between ${limits.minimum_lot_usd:,.2f} and ${limits.maximum_lot_usd:,.2f}")
    if not 1 <= allocation.lots <= limits.maximum_lots:
        problems.append(f"Number of lots must be between 1 and {limits.maximum_lots}")
    return problems


def lot_allocation(coin_cash: Decimal, open_lots: int, allocation: CoinAllocation) -> Decimal | None:
    """Only full lots: buy exactly one lot when a slot is free and the coin's
    free cash covers it. Anything less is never traded."""
    if open_lots < allocation.lots and coin_cash >= allocation.lot_size_usd:
        return allocation.lot_size_usd
    return None


@dataclass(frozen=True)
class AllocationPlan:
    """Effect of setting a coin to `allocation`, given its current state."""
    current_capital_usd: Decimal      # coin free cash + cost of its open lots
    target_capital_usd: Decimal
    transfer_usd: Decimal             # + from unallocated into the coin, − back to unallocated
    coin_cash_after_usd: Decimal
    unallocated_after_usd: Decimal
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def plan_allocation(allocation: CoinAllocation, limits: AllocationLimits, coin_cash: Decimal,
                    open_lot_cost: Decimal, open_lots: int, unallocated: Decimal) -> AllocationPlan:
    """Rebalance the coin to exactly lot size × lots. Money comes from (or goes
    back to) unallocated cash; money inside open lots is never moved."""
    problems = validate_allocation(allocation, limits)
    current = coin_cash + open_lot_cost
    target = allocation.target_capital_usd
    transfer = target - current
    if transfer > unallocated:
        problems.append(f"Needs ${transfer:,.2f} from unallocated cash but only ${max(unallocated, ZERO):,.2f} is unallocated. "
                        "Add funds first or choose a smaller size.")
    if transfer < 0 and -transfer > coin_cash:
        problems.append(f"${open_lot_cost:,.2f} is inside {open_lots} open lot(s); only ${coin_cash:,.2f} of this coin's cash "
                        "is free to return. Choose at least "
                        f"${current - coin_cash:,.2f} in total, or wait for lots to close.")
    return AllocationPlan(current, target, transfer, coin_cash + transfer, unallocated - transfer, tuple(problems))


def next_lot_status(coin_cash: Decimal, open_lots: int, allocation: CoinAllocation, unallocated: Decimal) -> dict:
    """Plain description of what the next signal would buy, for the dashboard."""
    lot = lot_allocation(coin_cash, open_lots, allocation)
    shortfall = max(ZERO, allocation.lot_size_usd - coin_cash)
    slot_free = open_lots < allocation.lots
    return {
        "next_lot_usd": lot,
        "lot_number": open_lots + 1,
        "slot_free": slot_free,
        "shortfall_to_full_lot_usd": shortfall if slot_free and lot is None else ZERO,
        "needs_top_up": slot_free and lot is None,
        "top_up_from_unallocated_usd": min(shortfall, max(unallocated, ZERO)) if slot_free and lot is None else ZERO,
        "top_up_deposit_needed_usd": max(ZERO, shortfall - max(unallocated, ZERO)) if slot_free and lot is None else ZERO,
    }


@dataclass(frozen=True)
class FeeContext:
    """What the account can pay fees with at the moment of a fill."""
    bnb_enabled: bool
    bnb_balance: Decimal
    bnb_price: Decimal | None


@dataclass(frozen=True)
class Fee:
    asset: str          # "BNB" or "USDT"
    rate_bps: Decimal
    usd: Decimal        # USD value of the fee
    bnb: Decimal        # BNB deducted from the fee wallet (0 for USDT fees)


def choose_fee(notional_usd: Decimal, context: FeeContext, config: ExecutionConfig) -> Fee:
    """Pay in BNB at the discounted rate when enabled and affordable; otherwise USDT."""
    if context.bnb_enabled and context.bnb_price and context.bnb_price > ZERO:
        usd = notional_usd * config.bnb_fee_bps / TEN_THOUSAND
        bnb = usd / context.bnb_price
        if bnb <= context.bnb_balance:
            return Fee("BNB", config.bnb_fee_bps, usd, bnb)
    return Fee("USDT", config.usdt_fee_bps, notional_usd * config.usdt_fee_bps / TEN_THOUSAND, ZERO)


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
    entry_time: datetime
    raw_entry_price: Decimal
    entry_fill_price: Decimal
    quantity: Decimal
    allocation_usd: Decimal          # cash taken from the account
    entry_fee_usd: Decimal
    entry_fee_asset: str = "USDT"
    bars_held: int = 0
    trailing_active: bool = False
    peak_price: Decimal | None = None
    trailing_started_at: datetime | None = None
    symbol: str = "SOLUSDT"
    entry_source: str = "signal"
    # True when this lot was opened in a clean uptrend, so it exits on the EMA instead of the giveback.
    trend_exit_active: bool = False
    # Set when a minute closed below the EMA; the sale happens at the next minute's open.
    trend_exit_pending: bool = False


@dataclass(frozen=True)
class EntryFill:
    fill_price: Decimal
    quantity: Decimal
    notional_usd: Decimal
    fee: Fee
    slippage_usd: Decimal
    allocation_usd: Decimal


def create_entry(raw_open: Decimal, allocation: Decimal, config: ExecutionConfig,
                 context: FeeContext) -> EntryFill:
    """Spend `allocation` of cash. A USDT fee comes out of the allocation; a BNB
    fee is charged to the fee wallet, so the full allocation buys SOL."""
    fill = raw_open * (Decimal("1") + config.slippage_bps / TEN_THOUSAND)
    fee = choose_fee(allocation, context, config)
    if fee.asset == "USDT":
        quantity = allocation / (fill * (Decimal("1") + config.usdt_fee_bps / TEN_THOUSAND))
        notional = quantity * fill
        fee = Fee("USDT", config.usdt_fee_bps, notional * config.usdt_fee_bps / TEN_THOUSAND, ZERO)
    else:
        quantity = allocation / fill
        notional = allocation
    return EntryFill(
        fill_price=fill,
        quantity=quantity,
        notional_usd=notional,
        fee=fee,
        slippage_usd=quantity * (fill - raw_open),
        allocation_usd=allocation,
    )


@dataclass(frozen=True)
class ExitSignal:
    reason: str
    raw_price: Decimal
    exit_time: datetime
    duration_minutes: int


@dataclass(frozen=True)
class ExitFill:
    reason: str
    raw_price: Decimal
    fill_price: Decimal
    fee: Fee
    slippage_usd: Decimal
    cash_in_usd: Decimal
    net_pnl_usd: Decimal       # after every fee, BNB fees at their USD value
    net_return_pct: Decimal
    exit_time: datetime
    duration_minutes: int


def uses_trend_exit(position: Position, config: ExecutionConfig) -> bool:
    """Mode A: hold to the EMA. Only for lots opened in a clean uptrend, when the strategy asks for it."""
    if config.trend_exit_ema_minutes is None:
        return False
    return position.trend_exit_active or not config.trend_exit_requires_uptrend


def evaluate_exit(position: Position, candle: Candle, config: ExecutionConfig,
                  ema: Decimal | None = None) -> ExitSignal | None:
    """Advance one lot through one completed minute.

    The stop is checked first. The activation minute cannot trigger the trail;
    the trail uses the peak known before the current minute. Gaps fill at the
    worse of the level and the minute's open.

    Once the trail has armed, a lot on the trend exit (Mode A) ignores the giveback and holds while
    minutes keep closing above `ema`. The first close below it sells at the NEXT minute's open, which
    is why the sale is deferred by one minute rather than filled inside the closing minute.
    """
    position.bars_held += 1
    config = config.for_source(position.entry_source)
    stop = position.entry_fill_price * (Decimal("1") - config.stop_pct / HUNDRED)
    if position.trend_exit_pending:
        # A previous minute closed below the EMA: this minute's open is the fill.
        return ExitSignal("trend_exit", candle.open, candle.exit_time, position.bars_held)
    if not position.trailing_active:
        activation = position.entry_fill_price * (Decimal("1") + config.trail_activation_pct / HUNDRED)
        activation_hit = candle.high >= activation
        if candle.low <= stop:
            reason = "ambiguous_stop" if activation_hit else "protective_stop"
            return ExitSignal(reason, min(stop, candle.open), candle.exit_time, position.bars_held)
        if activation_hit:
            position.trailing_active = True
            position.trailing_started_at = candle.open_time
            position.peak_price = max(position.entry_fill_price, candle.high)
    elif uses_trend_exit(position, config):
        # Armed and riding the line: the stop moves up to break even plus costs, so a lot that has already
        # proved itself cannot come all the way back and finish negative.
        floor = position.entry_fill_price * (Decimal("1") + config.break_even_floor_pct / HUNDRED)
        if floor > stop:
            stop = floor
            if candle.low <= stop:
                return ExitSignal("break_even", min(stop, candle.open), candle.exit_time, position.bars_held)
        if candle.low <= stop:
            return ExitSignal("protective_stop", min(stop, candle.open), candle.exit_time, position.bars_held)
        position.peak_price = max(position.peak_price or position.entry_fill_price, candle.high)
        if ema is not None and candle.close < ema:
            position.trend_exit_pending = True
    else:
        if position.peak_price is None:
            raise ValueError("Active trailing position has no peak price")
        trail = trailing_stop_price(position, config)
        if candle.low <= trail:
            return ExitSignal("trailing_stop", min(trail, candle.open), candle.exit_time, position.bars_held)
        position.peak_price = max(position.peak_price, candle.high)
    if config.maximum_hold_minutes is not None and position.bars_held >= config.maximum_hold_minutes:
        return ExitSignal("time", candle.close, candle.exit_time, position.bars_held)
    return None


def trailing_stop_price(position: Position, config: ExecutionConfig) -> Decimal:
    peak = position.peak_price or position.entry_fill_price
    return position.entry_fill_price + (peak - position.entry_fill_price) * (
        Decimal("1") - config.trail_giveback_pct / HUNDRED
    )


def fill_exit(position: Position, signal: ExitSignal, config: ExecutionConfig,
              context: FeeContext) -> ExitFill:
    fill = signal.raw_price * (Decimal("1") - config.slippage_bps / TEN_THOUSAND)
    notional = position.quantity * fill
    fee = choose_fee(notional, context, config)
    cash_in = notional - (fee.usd if fee.asset == "USDT" else ZERO)
    entry_bnb_fee = position.entry_fee_usd if position.entry_fee_asset == "BNB" else ZERO
    exit_bnb_fee = fee.usd if fee.asset == "BNB" else ZERO
    pnl = cash_in - position.allocation_usd - entry_bnb_fee - exit_bnb_fee
    invested = position.allocation_usd + entry_bnb_fee
    return ExitFill(
        reason=signal.reason,
        raw_price=signal.raw_price,
        fill_price=fill,
        fee=fee,
        slippage_usd=position.quantity * (signal.raw_price - fill),
        cash_in_usd=cash_in,
        net_pnl_usd=pnl,
        net_return_pct=pnl / invested * HUNDRED,
        exit_time=signal.exit_time,
        duration_minutes=signal.duration_minutes,
    )


def manual_exit_signal(position: Position, candle: Candle, requested_at: datetime) -> ExitSignal | None:
    """A manual close fills at the close of the first minute completed after the request."""
    if candle.exit_time <= requested_at:
        return None
    return ExitSignal("manual_close", candle.close, candle.exit_time, position.bars_held)


@dataclass(frozen=True)
class AccountMark:
    open_position_value_usd: Decimal
    open_position_cost_usd: Decimal
    unrealized_pnl_usd: Decimal
    bnb_value_usd: Decimal
    total_value_usd: Decimal
    strategy_pnl_usd: Decimal
    performance_equity_usd: Decimal
    performance_peak_usd: Decimal
    drawdown_pct: Decimal
    return_pct: Decimal


def mark_account(cash: Decimal, positions: list[Position], price: Decimal | Mapping[str, Decimal],
                 bnb_balance: Decimal, bnb_price: Decimal | None, realized_pnl: Decimal,
                 net_deposits: Decimal, initial_deposit: Decimal, previous_peak: Decimal) -> AccountMark:
    """Total value includes the BNB wallet. Performance (drawdown, return) uses
    only trading results so deposits, withdrawals and BNB price moves don't count.

    `price` is one price for every position or a price per symbol."""
    def mark(position: Position) -> Decimal:
        return price[position.symbol] if isinstance(price, Mapping) else price

    open_value = sum((position.quantity * mark(position) for position in positions), ZERO)
    open_cost = sum(
        (position.allocation_usd + (position.entry_fee_usd if position.entry_fee_asset == "BNB" else ZERO)
         for position in positions), ZERO,
    )
    unrealized = open_value - open_cost
    bnb_value = bnb_balance * bnb_price if bnb_price else ZERO
    strategy_pnl = realized_pnl + unrealized
    performance = initial_deposit + strategy_pnl
    peak = max(previous_peak, performance)
    return AccountMark(
        open_position_value_usd=open_value,
        open_position_cost_usd=open_cost,
        unrealized_pnl_usd=unrealized,
        bnb_value_usd=bnb_value,
        total_value_usd=cash + open_value + bnb_value,
        strategy_pnl_usd=strategy_pnl,
        performance_equity_usd=performance,
        performance_peak_usd=peak,
        drawdown_pct=(performance / peak - Decimal("1")) * HUNDRED if peak > ZERO else ZERO,
        return_pct=strategy_pnl / net_deposits * HUNDRED if net_deposits > ZERO else ZERO,
    )
