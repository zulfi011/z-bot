"""Adapter from the deployed ETH-v5 research rules to the canonical engine."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .engine import CandidateTrade, MarketData

STAGE2_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = STAGE2_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import all_coins_compare as compare  # noqa: E402
import eth_floor_and_arm as floor_arm  # noqa: E402
import eth_pullback as pullback  # noqa: E402
import live_ema_hold_all as live  # noqa: E402
import run_eth_full_research as research  # noqa: E402
import run_sol_stage3_space_grid as grid  # noqa: E402
import three_modes as modes  # noqa: E402


def build_baseline() -> tuple[MarketData, list[CandidateTrade], dict[str, tuple[pd.Timestamp, pd.Timestamp]]]:
    """Build ETH-v5 candidates exactly as the accepted $430.16 historical control."""
    raw, bullish = compare.load("ETHUSDT")
    rule = live.load_rule("eth")
    trend_line = pd.Series(grid.CLOSE).ewm(span=16 * 60, adjust=False).mean().to_numpy()
    floor_arm.LINE_FLOOR = trend_line * (1 + floor_arm.COSTS / 100)
    sources = (
        (live.live_entries(raw, rule), "dip", modes.DIP_STOP,
         rule["activation_pct"], rule["giveback_pct"]),
        ([trade["entry"] for trade in compare.mode_c(
            raw, rule, 120, 12, 2.5, 30, 1.283, 22.0, 3.5
        )], "breakout", 3.5, 1.283, 22.0),
        (pullback.pullback_entries(
            grid.CLOSE, bullish, 24, 180, grid.TIMES, blocked=rule["blocked"]
        ), "pullback", modes.DIP_STOP, rule["activation_pct"], rule["giveback_pct"]),
    )
    book = floor_arm.book(
        sources, bullish, trend_line, floor_arm.DEPLOYED_ARM, "buy price", "on arming"
    )
    candidates = [
        CandidateTrade(
            entry=int(trade["entry"]), exit=int(trade["exit"]), exit_price=float(trade["price"]),
            source=str(trade["source"]), exit_code=int(trade["why"]),
            candidate_id=f"{trade['source']}:{grid.TIMES[int(trade['entry'])].isoformat()}:{index}",
            exit_kind=_exit_kind(trade),
            arm_index=_arm_index(trade),
            bullish_entry=bool(bullish[int(trade["entry"])]),
        )
        for index, trade in enumerate(book)
    ]
    market = MarketData(
        times=pd.DatetimeIndex(grid.TIMES), open=grid.OPEN.copy(), close=grid.CLOSE.copy()
    )
    windows = dict(research.WINDOWS)
    windows["post_selection_2026_08_09"] = windows.pop("unseen")
    return market, candidates, windows


def _exit_kind(trade: dict) -> str:
    """Separate an unarmed protective stop from an armed break-even-floor exit."""
    if int(trade["why"]) != 2:
        return "strategy_exit" if int(trade["why"]) == 1 else "data_endpoint"
    entry, exit_at = int(trade["entry"]), int(trade["exit"])
    arm_pct = 1.283 if trade["source"] == "breakout" else 1.315
    fill = float(grid.OPEN[entry]) * (1 + grid.SLIP)
    armed = np.any(grid.HIGH[entry:exit_at + 1] >= fill * (1 + arm_pct / 100))
    return "break_even" if armed else "protective_stop"


def _arm_index(trade: dict) -> int | None:
    entry, exit_at = int(trade["entry"]), int(trade["exit"])
    arm_pct = 1.283 if trade["source"] == "breakout" else 1.315
    fill = float(grid.OPEN[entry]) * (1 + grid.SLIP)
    hits = np.flatnonzero(grid.HIGH[entry:exit_at + 1] >= fill * (1 + arm_pct / 100))
    return entry + int(hits[0]) if len(hits) else None
