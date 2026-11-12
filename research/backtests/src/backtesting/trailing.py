"""Conservative raw-minute exit simulation and chronological trade selection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


FEE_RATE = 10.0 / 10_000
SLIPPAGE_RATE = 2.0 / 10_000
STOP_PCT = 4.0
FIXED_TARGET_PCT = 4.0
MAX_HOLD_MINUTES = 1_440


@dataclass(frozen=True)
class ExitResult:
    entry_fill: float
    raw_exit: float
    exit_fill: float
    net_return_pct: float
    duration_minutes: int
    exit_type: str
    activation_reached: bool


def _finish(entry_fill: float, raw_exit: float, duration: int, exit_type: str,
            activation_reached: bool) -> ExitResult:
    exit_fill = raw_exit * (1 - SLIPPAGE_RATE)
    net_multiple = exit_fill * (1 - FEE_RATE) / (entry_fill * (1 + FEE_RATE))
    return ExitResult(
        entry_fill=entry_fill,
        raw_exit=raw_exit,
        exit_fill=exit_fill,
        net_return_pct=(net_multiple - 1) * 100,
        duration_minutes=duration,
        exit_type=exit_type,
        activation_reached=activation_reached,
    )


def simulate_fixed(path: pd.DataFrame) -> ExitResult:
    """Replay the frozen +4% target, -4% stop and 24-hour exit."""
    entry_fill = float(path.iloc[0].open) * (1 + SLIPPAGE_RATE)
    target = entry_fill * (1 + FIXED_TARGET_PCT / 100)
    stop = entry_fill * (1 - STOP_PCT / 100)
    for offset, candle in enumerate(path.itertuples(index=False)):
        target_hit = candle.high >= target
        stop_hit = candle.low <= stop
        if stop_hit:
            kind = "ambiguous_stop" if target_hit else "protective_stop"
            return _finish(entry_fill, min(stop, candle.open), offset + 1, kind, target_hit)
        if target_hit:
            return _finish(entry_fill, max(target, candle.open), offset + 1,
                           "profit_target", True)
    return _finish(entry_fill, float(path.iloc[-1].close), len(path), "time", False)


def simulate_trailing(path: pd.DataFrame, activation_pct: float,
                      giveback_pct: float) -> ExitResult:
    """Activate on a threshold, then trail the prior known open profit.

    The activation candle cannot also trigger the trail because OHLC data does
    not reveal intraminute ordering. A hard-stop hit on that candle wins.
    Each later candle uses the peak known before that candle, preventing the
    candle's high from raising a stop that its earlier low may have crossed.
    """
    entry_fill = float(path.iloc[0].open) * (1 + SLIPPAGE_RATE)
    activation = entry_fill * (1 + activation_pct / 100)
    hard_stop = entry_fill * (1 - STOP_PCT / 100)
    peak = entry_fill
    active = False

    for offset, candle in enumerate(path.itertuples(index=False)):
        if not active:
            activation_hit = candle.high >= activation
            stop_hit = candle.low <= hard_stop
            if stop_hit:
                kind = "ambiguous_stop" if activation_hit else "protective_stop"
                return _finish(entry_fill, min(hard_stop, candle.open), offset + 1,
                               kind, activation_hit)
            if activation_hit:
                active = True
                peak = max(peak, float(candle.high))
            continue

        trail = entry_fill + (peak - entry_fill) * (1 - giveback_pct / 100)
        if candle.low <= trail:
            return _finish(entry_fill, min(trail, candle.open), offset + 1,
                           "trailing_stop", True)
        peak = max(peak, float(candle.high))

    return _finish(entry_fill, float(path.iloc[-1].close), len(path), "time", active)


def select_one_position(trades: pd.DataFrame) -> pd.DataFrame:
    """Keep the earliest signal available while a single spot position is flat."""
    ordered = trades.sort_values(["entry_timestamp", "episode_id"])
    selected: list[int] = []
    available_at: pd.Timestamp | None = None
    for row in ordered.itertuples():
        if available_at is None or row.entry_timestamp >= available_at:
            selected.append(row.Index)
            available_at = row.entry_timestamp + pd.Timedelta(minutes=row.duration_minutes)
    return trades.loc[selected].sort_values("entry_timestamp").reset_index(drop=True)


def performance(trades: pd.DataFrame) -> dict[str, float | int]:
    values = trades.net_return_pct.astype(float)
    wins = values[values > 0]
    losses = values[values < 0]
    equity = np.r_[1.0, np.cumprod(1 + values.to_numpy() / 100)]
    peaks = np.maximum.accumulate(equity)
    drawdowns = (equity / peaks - 1) * 100
    profit_factor = wins.sum() / abs(losses.sum()) if len(losses) else np.inf
    exits = trades.exit_type.value_counts()
    return {
        "trades": len(trades),
        "wins": int((values > 0).sum()),
        "win_rate_pct": (values > 0).mean() * 100 if len(values) else np.nan,
        "mean_return_pct": values.mean(),
        "median_return_pct": values.median(),
        "profit_factor": profit_factor,
        "compounded_return_pct": (equity[-1] - 1) * 100,
        "max_drawdown_pct": drawdowns.min(),
        "worst_trade_pct": values.min(),
        "target_exits": int(exits.get("profit_target", 0)),
        "trailing_exits": int(exits.get("trailing_stop", 0)),
        "stop_exits": int(exits.get("protective_stop", 0) + exits.get("ambiguous_stop", 0)),
        "time_exits": int(exits.get("time", 0)),
        "activation_rate_pct": trades.activation_reached.mean() * 100,
    }

