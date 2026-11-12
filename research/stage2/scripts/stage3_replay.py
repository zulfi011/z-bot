"""Historical replay of a Stage 3 strategy JSON using Stage 3's own domain code.

The signal state machine (`FrozenSignalEngine`) and the fill/exit rules
(`create_entry`, `evaluate_exit`) are imported unchanged from
`engine/backend/app/domain`, and the per-minute ordering below
mirrors `PaperExecutionService._process_next`. Any strategy dict in the Stage 3
JSON schema can be replayed, so candidate strategies are measured with exactly
the same machinery as the live baseline.
"""

from __future__ import annotations

import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
STAGE3 = PROJECT.parent / "engine"
LEGACY = Path(__file__).resolve().parent / "stage3_legacy"
ARCHIVED = ROOT / "config/archived_stage3_v1"
sys.path.insert(0, str(LEGACY))

from app.domain.execution import (  # noqa: E402
    Candle,
    ExecutionConfig,
    Position,
    _exit,
    create_entry,
    evaluate_exit,
)
from app.domain.signal_engine import FrozenSignalEngine, SignalCandle  # noqa: E402

RAW_DIR = PROJECT / "stage1/data/raw"
HOLDOUT_DIR = ROOT / "data/holdout_downloads"
STRATEGY_FILES = {
    "SOLUSDT": ARCHIVED / "sol_frozen_strategy.json",
    "ETHUSDT": ARCHIVED / "eth_frozen_strategy.json",
    "BTCUSDT": ARCHIVED / "btc_frozen_strategy.json",
}

# Same persisted precision as PaperExecutionService so replay and live agree.
MONEY = Decimal("0.00000001")
PRICE = Decimal("0.0000000001")
QUANTITY = Decimal("0.000000000001")
HUNDRED = Decimal("100")


def load_raw(symbol: str, include_holdout: bool = False) -> pd.DataFrame:
    frame = pd.read_parquet(
        RAW_DIR / symbol / f"{symbol}_1m.parquet",
        columns=["open_time", "open", "high", "low", "close"],
    )
    if include_holdout:
        extra = load_holdout_zips(symbol)
        if extra.empty:
            raise FileNotFoundError(f"No holdout downloads for {symbol}")
        frame = pd.concat([frame, extra]).drop_duplicates("open_time").sort_values("open_time")
    return frame.reset_index(drop=True)


def load_holdout_zips(symbol: str) -> pd.DataFrame:
    parts = []
    for path in sorted(HOLDOUT_DIR.glob(f"{symbol}-1m-*.zip")):
        with zipfile.ZipFile(path) as archive:
            with archive.open(archive.namelist()[0]) as handle:
                part = pd.read_csv(handle, header=None, usecols=range(5))
        if not str(part.iloc[0, 0]).isdigit():
            part = part.iloc[1:]
        parts.append(part)
    if not parts:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close"])
    frame = pd.concat(parts)
    frame.columns = ["open_time", "open", "high", "low", "close"]
    stamps = frame.open_time.astype("int64")
    # Binance spot archives switched from milliseconds to microseconds in 2025.
    micros = np.where(stamps > 10**14, stamps, stamps * 1000)
    frame["open_time"] = pd.to_datetime(micros, unit="us", utc=True)
    for column in ["open", "high", "low", "close"]:
        frame[column] = frame[column].astype(float)
    return frame


def _dec(value) -> Decimal:
    return Decimal(str(value))


def daily_averages(raw: pd.DataFrame) -> dict[pd.Timestamp, tuple]:
    """Match signal_repository.refresh_derived_data: complete UTC days only,
    ROWS-based SMA with count == period, effective from the next UTC day."""
    day = raw.open_time.dt.floor("D")
    grouped = raw.groupby(day).agg(close=("close", "last"), n=("close", "size"))
    complete = grouped[grouped.n == 1440]
    closes = [_dec(value) for value in complete.close]
    result = {}
    for position, effective_day in enumerate(complete.index):
        averages = []
        for period in (7, 15, 30):
            if position + 1 >= period:
                window = closes[position + 1 - period:position + 1]
                averages.append(sum(window, Decimal("0")) / period)
            else:
                averages.append(None)
        result[effective_day + pd.Timedelta(days=1)] = tuple(averages)
    return result


def daily_average_n(raw: pd.DataFrame, period: int) -> dict[pd.Timestamp, Decimal | None]:
    """Same completed-day SMA as daily_averages for any period length."""
    day = raw.open_time.dt.floor("D")
    grouped = raw.groupby(day).agg(close=("close", "last"), n=("close", "size"))
    complete = grouped[grouped.n == 1440]
    closes = [_dec(value) for value in complete.close]
    return {
        effective_day + pd.Timedelta(days=1): (
            sum(closes[position + 1 - period:position + 1], Decimal("0")) / period
            if position + 1 >= period else None
        )
        for position, effective_day in enumerate(complete.index)
    }


@dataclass(frozen=True)
class SignalCandleN(SignalCandle):
    """Signal candle carrying an extra N-day average for non-7/15/30 signals."""
    average_nd: Decimal | None = None


class AnyAverageEngine(FrozenSignalEngine):
    """FrozenSignalEngine with the touch measured against `average_nd`; the
    7/15/30-day regime filter is unchanged. Not deployable in Stage 3 as-is."""

    def __init__(self, *args, signal_average_days: int, **kwargs) -> None:
        super().__init__(*args, signal_average_days=15, **kwargs)
        self.signal_average_days = signal_average_days

    def signal_average(self, candle: SignalCandleN) -> Decimal | None:
        return candle.average_nd


def signal_candles(raw: pd.DataFrame, minutes: int,
                   averages: dict[pd.Timestamp, tuple],
                   signal_days: int | None = None) -> list[SignalCandle]:
    indexed = raw.set_index("open_time")
    frame = indexed.resample(f"{minutes}min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    counts = indexed.close.resample(f"{minutes}min", label="left", closed="left").count()
    frame = frame[counts == minutes]
    candles = []
    empty = (None, None, None)
    extra = daily_average_n(raw, signal_days) if signal_days else None
    for stamp, row in zip(frame.index, frame.itertuples(index=False)):
        a7, a15, a30 = averages.get(stamp.floor("D"), empty)
        values = dict(
            open_time=stamp.to_pydatetime(),
            open=_dec(row.open), high=_dec(row.high), low=_dec(row.low), close=_dec(row.close),
            average_7d=a7, average_15d=a15, average_30d=a30,
        )
        if extra is None:
            candles.append(SignalCandle(**values))
        else:
            candles.append(SignalCandleN(**values, average_nd=extra.get(stamp.floor("D"))))
    return candles


def generate_signals(strategy: dict, candles: list[SignalCandle]) -> tuple[list[dict], dict]:
    entry = strategy["entry"]
    days = int(strategy["averages"]["signal_average_days"])
    arguments = (
        strategy["strategy_id"],
        _dec(entry["touch_zone_pct"]),
        int(entry["confirmation"]["maximum_wait_minutes"]),
        entry["approach"],
        entry["market_filter"]["type"],
        int(strategy["market"]["signal_timeframe"].removesuffix("m")),
    )
    if isinstance(candles[0], SignalCandleN):
        engine = AnyAverageEngine(*arguments, signal_average_days=days)
    else:
        engine = FrozenSignalEngine(*arguments, days)
    episodes: dict[str, datetime] = {}
    signals = []
    outcomes: dict[str, int] = {}
    for candle in candles:
        transition = engine.process(candle)
        if transition.episode and transition.episode.status == "pending_confirmation":
            episodes[transition.episode.episode_id] = transition.episode.touch_time
        if transition.resolution:
            resolution = transition.resolution
            outcomes[resolution.status] = outcomes.get(resolution.status, 0) + 1
            if resolution.status == "confirmed":
                signals.append({
                    "signal_id": resolution.episode_id,
                    "touch_time": episodes[resolution.episode_id],
                    "confirmation_time": resolution.confirmation_time,
                    "entry_time": resolution.entry_time,
                })
    diagnostics = {
        "touch_episodes": engine.episodes_seen,
        "from_below_episodes": engine.from_below_episodes,
        "market_filter_rejections": engine.market_rejections,
        "confirmed_signals": outcomes.get("confirmed", 0),
        "cancelled_at_episode_exit": outcomes.get("cancelled_at_episode_exit", 0),
        "expired_wait_limit": outcomes.get("expired_wait_limit", 0),
    }
    return signals, diagnostics


@dataclass
class ReplayResult:
    trades: pd.DataFrame
    equity_points: pd.DataFrame
    ignored_signals: int
    open_positions_at_end: int
    final_equity: float
    fees_paid: float
    slippage_paid: float
    start: pd.Timestamp
    end: pd.Timestamp
    diagnostics: dict = field(default_factory=dict)


def breakeven_exit(trigger_pct: float, level_pct: float):
    """Stage 3 exits plus a break-even stop: once a candle's high reaches
    +trigger_pct (before the trail is active), from the next candle the stop
    rises to entry fill × (1 + level_pct). Stop-first and gap-fill rules match
    evaluate_exit. Not part of Stage 3."""
    trigger = Decimal(str(trigger_pct)) / HUNDRED
    level = Decimal(str(level_pct)) / HUNDRED

    def rule(position: Position, candle: Candle, config: ExecutionConfig):
        armed = getattr(position, "breakeven_armed", False)
        if armed and not position.trailing_active:
            price = position.entry_fill_price * (1 + level)
            if candle.low <= price:
                position.bars_held += 1
                return _exit(position, candle, min(price, candle.open), "breakeven_stop", config)
        result = evaluate_exit(position, candle, config)
        if (result is None and not armed and not position.trailing_active
                and candle.high >= position.entry_fill_price * (1 + trigger)):
            position.breakeven_armed = True
        return result

    return rule


def replay_execution(strategy: dict, raw: pd.DataFrame, signals: list[dict],
                     start: pd.Timestamp, end: pd.Timestamp,
                     allocate=None, exit_rule=None) -> ReplayResult:
    """Mirror PaperExecutionService._process_next for signals whose touch and
    entry fall inside [start, end). Open lots are managed until they exit.
    `allocate(marked, cash)` overrides Stage 3's equity-fraction sizing."""
    config = ExecutionConfig.from_strategy(strategy)
    times = pd.DatetimeIndex(raw.open_time)
    opens, highs, lows, closes = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    entries: dict[int, list[str]] = {}
    for signal in signals:
        entry_time = pd.Timestamp(signal["entry_time"])
        if not (start <= pd.Timestamp(signal["touch_time"]) and entry_time < end):
            continue
        index = int(times.searchsorted(entry_time))
        if index < len(times) and times[index] == entry_time:
            entries.setdefault(index, []).append(signal["signal_id"])
    entry_order = sorted(entries)

    cash = config.initial_equity
    fees = slippage = Decimal("0")
    positions: list[Position] = []
    trades = []
    points = []
    ignored = 0
    pointer = 0
    index = entry_order[0] if entry_order else len(times)

    def candle_at(i: int) -> Candle:
        return Candle(times[i].to_pydatetime(), _dec(opens[i]), _dec(highs[i]),
                      _dec(lows[i]), _dec(closes[i]))

    while index < len(times):
        candle = candle_at(index)
        if pointer < len(entry_order) and entry_order[pointer] == index:
            for signal_id in sorted(entries[index]):
                if len(positions) >= config.maximum_positions:
                    ignored += 1
                    continue
                marked = cash + sum((p.quantity * candle.open for p in positions), Decimal("0"))
                allocation = (allocate(marked, cash) if allocate
                              else min(marked * config.equity_fraction, cash))
                if allocation <= MONEY:
                    ignored += 1
                    continue
                fill = create_entry(candle.open, allocation, config)
                position = Position(
                    position_id=f"position:{signal_id}", signal_id=signal_id,
                    entry_time=candle.open_time, raw_entry_price=candle.open,
                    entry_fill_price=fill.fill_price.quantize(PRICE),
                    quantity=fill.quantity.quantize(QUANTITY),
                    allocation_usd=fill.allocation_usd.quantize(MONEY),
                    entry_fee_usd=fill.fee_usd.quantize(MONEY),
                    strategy_id=strategy["strategy_id"], symbol=strategy["market"]["symbol"],
                )
                cash -= position.allocation_usd
                fees += fill.fee_usd.quantize(MONEY)
                slippage += fill.slippage_usd.quantize(MONEY)
                positions.append(position)
            pointer += 1

        still_open = []
        for position in positions:
            result = (exit_rule or evaluate_exit)(position, candle, config)
            if result is None:
                if position.peak_price is not None:
                    position.peak_price = position.peak_price.quantize(PRICE)
                still_open.append(position)
                continue
            exit_cash = result.cash_in_usd.quantize(MONEY)
            pnl = exit_cash - position.allocation_usd
            cash += exit_cash
            fees += result.fee_usd.quantize(MONEY)
            slippage += result.slippage_usd.quantize(MONEY)
            trades.append({
                "signal_id": position.signal_id,
                "entry_time": pd.Timestamp(position.entry_time),
                "exit_time": pd.Timestamp(result.exit_time),
                "allocation_usd": float(position.allocation_usd),
                "entry_fill_price": float(position.entry_fill_price),
                "exit_fill_price": float(result.fill_price),
                "exit_reason": result.reason,
                "duration_minutes": result.duration_minutes,
                "net_pnl_usd": float(pnl),
                "net_return_pct": float(pnl / position.allocation_usd * HUNDRED),
                "peak_price": float(position.peak_price) if position.peak_price else None,
            })
        positions = still_open
        equity = float(cash) + sum(float(p.quantity) * closes[index] for p in positions)
        points.append((times[index] + pd.Timedelta(minutes=1), equity))

        if positions:
            index += 1
        elif pointer < len(entry_order):
            index = entry_order[pointer]
        else:
            break

    last_close = closes[-1]
    final = float(cash) + sum(float(p.quantity) * last_close for p in positions)
    return ReplayResult(
        trades=pd.DataFrame(trades),
        equity_points=pd.DataFrame(points, columns=["timestamp", "equity_usd"]),
        ignored_signals=ignored,
        open_positions_at_end=len(positions),
        final_equity=final,
        fees_paid=float(fees),
        slippage_paid=float(slippage),
        start=start,
        end=end,
    )


def summarize(result: ReplayResult, initial: float = 100.0) -> dict:
    trades = result.trades
    count = len(trades)
    pnl = trades.net_pnl_usd if count else pd.Series(dtype=float)
    returns = trades.net_return_pct if count else pd.Series(dtype=float)
    wins = int((pnl > 0).sum())
    losses = int((pnl < 0).sum())
    gross_win = float(pnl[pnl > 0].sum())
    gross_loss = float(-pnl[pnl < 0].sum())
    curve = result.equity_points.equity_usd.to_numpy(float)
    curve = np.r_[initial, curve]
    drawdown = float(((curve / np.maximum.accumulate(curve)) - 1).min() * 100)
    months = (result.end - result.start) / pd.Timedelta(days=30.4375)
    reasons = trades.exit_reason.value_counts().to_dict() if count else {}
    return {
        "period_start": str(result.start.date()),
        "period_end": str((result.end - pd.Timedelta(minutes=1)).date()),
        "trades": count,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": wins / count * 100 if count else float("nan"),
        "final_equity_usd": result.final_equity,
        "net_profit_usd": result.final_equity - initial,
        "return_pct": (result.final_equity / initial - 1) * 100,
        "profit_factor": gross_win / gross_loss if gross_loss else float("nan"),
        "average_trade_pct": float(returns.mean()) if count else float("nan"),
        "average_winner_pct": float(returns[pnl > 0].mean()) if wins else float("nan"),
        "average_loser_pct": float(returns[pnl < 0].mean()) if losses else float("nan"),
        "best_trade_pct": float(returns.max()) if count else float("nan"),
        "worst_trade_pct": float(returns.min()) if count else float("nan"),
        "max_drawdown_pct": drawdown,
        "lowest_equity_usd": float(curve.min()),
        "trailing_exits": int(reasons.get("trailing_stop", 0)),
        "stop_exits": int(reasons.get("protective_stop", 0) + reasons.get("ambiguous_stop", 0)),
        "time_exits": int(reasons.get("time", 0)),
        "breakeven_exits": int(reasons.get("breakeven_stop", 0)),
        "fees_usd": result.fees_paid,
        "slippage_usd": result.slippage_paid,
        "signals_ignored_two_lots_full": result.ignored_signals,
        "open_positions_at_end": result.open_positions_at_end,
        "average_hold_hours": float(trades.duration_minutes.mean() / 60) if count else float("nan"),
        "trades_per_month": count / months if months else float("nan"),
    }
