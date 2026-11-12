"""Chronological spot-position exits for fixed-target and trailing modes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd

from .engine import CloseEvent, HistoryView, OpenEvent, StrategyEvent


@dataclass(frozen=True)
class ExitSpec:
    strategy: str
    mode: str
    stop_pct: float
    maximum_hold_minutes: int
    exit_slippage_bps: float
    target_pct: float | None = None
    trail_activation_pct: float | None = None
    trail_giveback_pct: float | None = None

    def __post_init__(self):
        if self.mode not in {"fixed_profit_target", "trailing_after_activation"}:
            raise ValueError(f"Unsupported exit mode: {self.mode}")
        if self.stop_pct <= 0 or self.maximum_hold_minutes < 1 or self.exit_slippage_bps < 0:
            raise ValueError("Invalid stop, holding time, or slippage")
        if self.mode == "fixed_profit_target" and (self.target_pct is None or self.target_pct <= 0):
            raise ValueError("Fixed-target mode requires a positive target")
        if self.mode == "trailing_after_activation":
            if self.trail_activation_pct is None or self.trail_activation_pct <= 0:
                raise ValueError("Trailing mode requires a positive activation")
            if self.trail_giveback_pct is None or not 0 < self.trail_giveback_pct < 100:
                raise ValueError("Trailing giveback must be between 0 and 100")


@dataclass
class Position:
    signal_id: str
    strategy: str
    entry_timestamp: pd.Timestamp
    raw_entry_open: float
    entry_fill: float
    bars_held: int = 0
    trailing_active: bool = False
    peak: float | None = None


@dataclass(frozen=True)
class CompletedTrade:
    signal_id: str
    strategy: str
    entry_timestamp: pd.Timestamp
    exit_timestamp: pd.Timestamp
    exit_candle_open_time: pd.Timestamp
    raw_entry_open: float
    entry_fill: float
    raw_exit_price: float
    exit_fill: float
    return_after_slippage_pct: float
    duration_minutes: int
    exit_type: str
    trailing_activated: bool
    peak_price: float | None


@dataclass(frozen=True)
class IgnoredEntry:
    signal_id: str
    strategy: str
    timestamp: pd.Timestamp
    reason: str


def _complete(position: Position, event: CloseEvent, raw_exit: float,
              exit_type: str, slippage_bps: float) -> CompletedTrade:
    exit_fill = raw_exit * (1 - slippage_bps / 10_000)
    return CompletedTrade(
        signal_id=position.signal_id,
        strategy=position.strategy,
        entry_timestamp=position.entry_timestamp,
        exit_timestamp=event.timestamp,
        exit_candle_open_time=event.candle.open_time,
        raw_entry_open=position.raw_entry_open,
        entry_fill=position.entry_fill,
        raw_exit_price=raw_exit,
        exit_fill=exit_fill,
        return_after_slippage_pct=(exit_fill / position.entry_fill - 1) * 100,
        duration_minutes=position.bars_held,
        exit_type=exit_type,
        trailing_activated=position.trailing_active,
        peak_price=position.peak,
    )


def evaluate_exit(position: Position, event: CloseEvent, spec: ExitSpec) -> CompletedTrade | None:
    """Advance one open position by one completed raw 1-minute candle."""
    position.bars_held += 1
    candle = event.candle
    hard_stop = position.entry_fill * (1 - spec.stop_pct / 100)

    if spec.mode == "fixed_profit_target":
        target = position.entry_fill * (1 + float(spec.target_pct) / 100)
        target_hit = candle.high >= target
        stop_hit = candle.low <= hard_stop
        if stop_hit:
            kind = "ambiguous_stop" if target_hit else "protective_stop"
            return _complete(position, event, min(hard_stop, candle.open), kind,
                             spec.exit_slippage_bps)
        if target_hit:
            return _complete(position, event, max(target, candle.open), "profit_target",
                             spec.exit_slippage_bps)

    elif not position.trailing_active:
        activation = position.entry_fill * (1 + float(spec.trail_activation_pct) / 100)
        activation_hit = candle.high >= activation
        stop_hit = candle.low <= hard_stop
        if stop_hit:
            kind = "ambiguous_stop" if activation_hit else "protective_stop"
            return _complete(position, event, min(hard_stop, candle.open), kind,
                             spec.exit_slippage_bps)
        if activation_hit:
            position.trailing_active = True
            position.peak = max(position.entry_fill, candle.high)

    else:
        prior_peak = float(position.peak)
        trail = position.entry_fill + (prior_peak - position.entry_fill) * (
            1 - float(spec.trail_giveback_pct) / 100
        )
        if candle.low <= trail:
            return _complete(position, event, min(trail, candle.open), "trailing_stop",
                             spec.exit_slippage_bps)
        position.peak = max(prior_peak, candle.high)

    if position.bars_held >= spec.maximum_hold_minutes:
        return _complete(position, event, candle.close, "time", spec.exit_slippage_bps)
    return None


class ExitReplayStrategy:
    """Open frozen entry fills while flat and manage their exits minute by minute."""

    REQUIRED = ["signal_id", "strategy", "timestamp", "raw_open", "fill_price"]

    def __init__(self, entry_fills: pd.DataFrame, specs: dict[str, ExitSpec]):
        missing = [column for column in self.REQUIRED if column not in entry_fills]
        if missing:
            raise ValueError(f"Missing entry-fill columns: {missing}")
        if set(entry_fills.strategy.unique()) - specs.keys():
            raise ValueError("Entry fill has no exit specification")
        frame = entry_fills.sort_values(["timestamp", "strategy", "signal_id"]).copy()
        if frame.signal_id.duplicated().any():
            raise ValueError("Duplicate entry signal ID")
        self.specs = specs
        self.orders = {
            timestamp: group.to_dict("records")
            for timestamp, group in frame.groupby("timestamp", sort=True)
        }
        self.positions: dict[str, Position] = {}
        self.completed: list[CompletedTrade] = []
        self.ignored: list[IgnoredEntry] = []
        self.incomplete: list[dict] = []

    def on_open(self, event: OpenEvent, history: HistoryView) -> Iterable[StrategyEvent] | None:
        orders = self.orders.pop(event.timestamp, [])
        output = []
        grouped: dict[str, list[dict]] = {}
        for order in orders:
            grouped.setdefault(order["strategy"], []).append(order)
        for strategy, candidates in grouped.items():
            candidates.sort(key=lambda row: row["signal_id"])
            if strategy in self.positions:
                for order in candidates:
                    self.ignored.append(IgnoredEntry(
                        order["signal_id"], strategy, event.timestamp, "position_open"
                    ))
                continue
            chosen, *duplicates = candidates
            if chosen["raw_open"] != event.price:
                raise ValueError("Frozen entry raw open does not match replay candle")
            self.positions[strategy] = Position(
                signal_id=chosen["signal_id"],
                strategy=strategy,
                entry_timestamp=event.timestamp,
                raw_entry_open=float(chosen["raw_open"]),
                entry_fill=float(chosen["fill_price"]),
            )
            output.append(StrategyEvent("position_opened", {
                "signal_id": chosen["signal_id"], "strategy": strategy,
                "entry_fill": float(chosen["fill_price"]),
            }))
            for order in duplicates:
                self.ignored.append(IgnoredEntry(
                    order["signal_id"], strategy, event.timestamp, "same_timestamp_duplicate"
                ))
        return output or None

    def on_close(self, event: CloseEvent, history: HistoryView) -> Iterable[StrategyEvent] | None:
        output = []
        for strategy, position in list(self.positions.items()):
            trade = evaluate_exit(position, event, self.specs[strategy])
            if trade is None:
                continue
            self.completed.append(trade)
            del self.positions[strategy]
            output.append(StrategyEvent("position_closed", asdict(trade)))
        return output or None

    def finalize(self, final_close_timestamp: pd.Timestamp) -> None:
        if self.orders:
            raise RuntimeError("Entry orders remain outside the raw candle history")
        for position in self.positions.values():
            self.incomplete.append({
                "signal_id": position.signal_id,
                "strategy": position.strategy,
                "entry_timestamp": position.entry_timestamp,
                "observed_until": final_close_timestamp,
                "observed_minutes": position.bars_held,
                "trailing_activated": position.trailing_active,
                "peak_price": position.peak,
                "status": "incomplete_data_end",
            })

    def completed_frame(self) -> pd.DataFrame:
        return pd.DataFrame(asdict(trade) for trade in self.completed)

    def ignored_frame(self) -> pd.DataFrame:
        return pd.DataFrame(asdict(entry) for entry in self.ignored)

    def incomplete_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.incomplete)

