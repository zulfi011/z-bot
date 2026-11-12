"""Rebuild raw-candle trade outcomes under alternative execution costs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .costs import apply_costs
from .engine import Candle, CloseEvent
from .exits import ExitSpec, Position, evaluate_exit


def rebuild_cost_scenario_outcomes(
    entry_fills: pd.DataFrame,
    raw_candles: pd.DataFrame,
    fee_bps_per_side: float,
    slippage_bps_per_side: float,
    maximum_hold_minutes: int = 1_440,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Replay every signal because entry slippage changes exit thresholds."""
    required_fills = ["signal_id", "strategy", "timestamp", "raw_open"]
    required_raw = ["open_time", "open", "high", "low", "close"]
    missing = [c for c in required_fills if c not in entry_fills]
    if missing:
        raise ValueError(f"Missing entry columns: {missing}")
    missing = [c for c in required_raw if c not in raw_candles]
    if missing:
        raise ValueError(f"Missing candle columns: {missing}")
    if fee_bps_per_side < 0 or slippage_bps_per_side < 0:
        raise ValueError("Costs cannot be negative")

    specs = {
        "primary": ExitSpec(
            "primary", "trailing_after_activation", 4, maximum_hold_minutes,
            slippage_bps_per_side, trail_activation_pct=4, trail_giveback_pct=10,
        ),
        "control": ExitSpec(
            "control", "fixed_profit_target", 4, maximum_hold_minutes,
            slippage_bps_per_side, target_pct=4,
        ),
    }
    times = pd.DatetimeIndex(raw_candles.open_time)
    rows: list[dict] = []
    incomplete: list[dict] = []
    slip_rate = slippage_bps_per_side / 10_000

    for fill in entry_fills.sort_values(["timestamp", "strategy", "signal_id"]).itertuples(index=False):
        if fill.strategy not in specs:
            raise ValueError(f"Unknown strategy: {fill.strategy}")
        start = int(times.searchsorted(fill.timestamp))
        if start >= len(raw_candles) or times[start] != fill.timestamp:
            raise ValueError(f"Entry candle is absent: {fill.signal_id}")
        raw_open = float(raw_candles.open.iloc[start])
        if not np.isclose(raw_open, fill.raw_open, rtol=0, atol=0):
            raise ValueError(f"Entry raw open changed: {fill.signal_id}")
        entry_fill = raw_open * (1 + slip_rate)
        position = Position(fill.signal_id, fill.strategy, fill.timestamp, raw_open, entry_fill)
        result = None
        available = raw_candles.iloc[start:start + maximum_hold_minutes]
        for offset, candle_row in enumerate(available.itertuples(index=False)):
            candle = Candle(
                candle_row.open_time, float(candle_row.open), float(candle_row.high),
                float(candle_row.low), float(candle_row.close),
            )
            event = CloseEvent(
                start + offset, candle.open_time + pd.Timedelta(minutes=1), candle
            )
            result = evaluate_exit(position, event, specs[fill.strategy])
            if result is not None:
                break
        if result is None:
            incomplete.append({
                "signal_id": fill.signal_id,
                "strategy": fill.strategy,
                "entry_timestamp": fill.timestamp,
                "observed_minutes": len(available),
            })
            continue
        rows.append({
            "signal_id": result.signal_id,
            "strategy": result.strategy,
            "entry_timestamp": result.entry_timestamp,
            "exit_timestamp": result.exit_timestamp,
            "duration_minutes": result.duration_minutes,
            "exit_type": result.exit_type,
            "raw_entry_open": result.raw_entry_open,
            "entry_fill": result.entry_fill,
            "raw_exit_price": result.raw_exit_price,
            "exit_fill": result.exit_fill,
            "return_after_slippage_pct": result.return_after_slippage_pct,
        })
    return apply_costs(pd.DataFrame(rows), fee_bps_per_side), pd.DataFrame(incomplete)

