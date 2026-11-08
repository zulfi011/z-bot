"""Search SOL signal candles, rolling averages, trailing exits, and stop combinations."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
EXPERIMENT_ID = "sol_full_ma_signal_exit_grid_v1"
RESULT_DIR = ROOT / "results" / EXPERIMENT_ID
DATA_DIR = ROOT / "data" / EXPERIMENT_ID
CONFIG_PATH = ROOT / "config/experiments" / f"{EXPERIMENT_ID}.json"
RAW_PATH = PROJECT / "stage1_research/data/raw/SOLUSDT/SOLUSDT_1m.parquet"

SIGNAL_MINUTES = [1, 3, 5]
AVERAGES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "12h": 720,
    "1d": 1_440,
    "3d": 4_320,
    "7d": 10_080,
    "15d": 21_600,
    "30d": 43_200,
}
ACTIVATIONS = [0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
GIVEBACKS = [10.0, 15.0, 20.0]
STOPS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
TOUCH_ZONE_PCT = 0.2
INITIAL_EQUITY = 100.0
FEE_RATE = 10.0 / 10_000
SLIPPAGE_RATE = 2.0 / 10_000


def signal_frame(raw: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes == 1:
        frame = raw[["open_time", "open", "high", "low", "close"]].copy()
    else:
        indexed = raw.set_index("open_time")
        frame = indexed.resample(f"{minutes}min", label="left", closed="left").agg({
            "open": "first", "high": "max", "low": "min", "close": "last",
        }).reset_index()
    regime_path = (
        PROJECT / "stage1_research/data/processed/SOLUSDT"
        / f"SOLUSDT_{minutes}m_with_averages.parquet"
    )
    regime = pd.read_parquet(
        regime_path, columns=["open_time", "average_7d", "average_15d", "average_30d"]
    )
    frame = frame.merge(regime, on="open_time", validate="one_to_one")
    return frame


def generate_confirmed_fills(frame: pd.DataFrame, signal_average: np.ndarray,
                             signal_minutes: int, raw_open: pd.Series,
                             average_label: str,
                             touch_zone_pct: float = TOUCH_ZONE_PCT) -> tuple[pd.DataFrame, dict]:
    zone = touch_zone_pct / 100
    high = frame.high.to_numpy(float)
    low = frame.low.to_numpy(float)
    opened = frame.open.to_numpy(float)
    close = frame.close.to_numpy(float)
    finite = np.isfinite(signal_average)
    touched = finite & (high >= signal_average * (1 - zone)) & (low <= signal_average * (1 + zone))
    new_episode = touched & ~np.r_[False, touched[:-1]]
    prior_below = np.zeros(len(frame), dtype=bool)
    prior_below[1:] = (
        np.isfinite(signal_average[:-1])
        & (high[:-1] < signal_average[:-1] * (1 - zone))
    )
    from_below = new_episode & prior_below
    averages = frame[["average_7d", "average_15d", "average_30d"]].to_numpy(float)
    regime_finite = np.isfinite(averages).all(axis=1)
    bearish = (averages[:, 0] < averages[:, 1]) & (averages[:, 1] < averages[:, 2])
    eligible = from_below & regime_finite & ~bearish
    max_steps = 30 // signal_minutes
    records = []

    for origin in np.flatnonzero(eligible):
        confirmed_at = None
        status = "expired"
        for offset in range(max_steps + 1):
            index = origin + offset
            if index >= len(frame):
                status = "truncated"
                break
            if close[index] > opened[index]:
                confirmed_at = index
                status = "confirmed"
                break
            if not touched[index]:
                status = "cancelled_at_episode_exit"
                break
        if confirmed_at is None:
            continue
        entry_timestamp = frame.open_time.iloc[confirmed_at] + pd.Timedelta(minutes=signal_minutes)
        if entry_timestamp not in raw_open.index:
            continue
        price = float(raw_open.at[entry_timestamp])
        records.append({
            "signal_id": f"{signal_minutes}m-{average_label}-{len(records)+1:05d}",
            "touch_timestamp": frame.open_time.iloc[origin],
            "confirmation_timestamp": frame.open_time.iloc[confirmed_at],
            "entry_timestamp": entry_timestamp,
            "entry_index": int(raw_open.index.searchsorted(entry_timestamp)),
            "raw_open": price,
            "entry_fill": price * (1 + SLIPPAGE_RATE),
        })
    columns = [
        "signal_id", "touch_timestamp", "confirmation_timestamp",
        "entry_timestamp", "entry_index", "raw_open", "entry_fill",
    ]
    return pd.DataFrame(records, columns=columns), {
        "touch_episodes": int(new_episode.sum()),
        "from_below_episodes": int(from_below.sum()),
        "eligible_after_market_filter": int(eligible.sum()),
        "confirmed_signals": len(records),
    }


def first_hit(mask: np.ndarray) -> int:
    hits = np.flatnonzero(mask)
    return int(hits[0]) if len(hits) else -1


class ThresholdIndex:
    """Segment trees for first future high/low threshold crossings."""

    def __init__(self, high: np.ndarray, low: np.ndarray):
        self.count = len(high)
        self.size = 1 << (self.count - 1).bit_length()
        self.high_tree = np.full(2 * self.size, -np.inf, dtype=float)
        self.low_tree = np.full(2 * self.size, np.inf, dtype=float)
        self.high_tree[self.size:self.size + self.count] = high
        self.low_tree[self.size:self.size + self.count] = low
        for node in range(self.size - 1, 0, -1):
            self.high_tree[node] = max(self.high_tree[node * 2], self.high_tree[node * 2 + 1])
            self.low_tree[node] = min(self.low_tree[node * 2], self.low_tree[node * 2 + 1])

    def first_ge(self, start: int, threshold: float) -> int:
        def search(node: int, left: int, right: int) -> int:
            if right <= start or self.high_tree[node] < threshold:
                return -1
            if right - left == 1:
                return left if left < self.count else -1
            middle = (left + right) // 2
            found = search(node * 2, left, middle)
            return found if found >= 0 else search(node * 2 + 1, middle, right)
        return search(1, 0, self.size)

    def first_le(self, start: int, threshold: float) -> int:
        def search(node: int, left: int, right: int) -> int:
            if right <= start or self.low_tree[node] > threshold:
                return -1
            if right - left == 1:
                return left if left < self.count else -1
            middle = (left + right) // 2
            found = search(node * 2, left, middle)
            return found if found >= 0 else search(node * 2 + 1, middle, right)
        return search(1, 0, self.size)


def precompute_outcomes(fills: pd.DataFrame, raw_arrays: dict[str, np.ndarray],
                        threshold_index: ThresholdIndex) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return exit index, raw exit, and type code for each signal and exit combination."""
    count = len(fills)
    shape = (count, len(ACTIVATIONS), len(GIVEBACKS), len(STOPS))
    exit_indices = np.full(shape, -1, dtype=np.int32)
    raw_exits = np.full(shape, np.nan, dtype=np.float64)
    # 1 trailing, 2 protective stop, 3 ambiguous stop, 0 still open.
    exit_types = np.zeros(shape, dtype=np.int8)
    opened, high, low = raw_arrays["open"], raw_arrays["high"], raw_arrays["low"]

    for fill_index, fill in enumerate(fills.itertuples(index=False)):
        start = int(fill.entry_index)
        entry = float(fill.entry_fill)
        future_high = high[start:]
        future_low = low[start:]
        stop_hits = []
        for stop in STOPS:
            stop_price = entry * (1 - stop / 100)
            absolute = threshold_index.first_le(start, stop_price)
            relative = absolute - start if absolute >= 0 else -1
            stop_hits.append((relative, stop_price))

        for activation_index, activation in enumerate(ACTIVATIONS):
            activation_price = entry * (1 + activation / 100)
            absolute = threshold_index.first_ge(start, activation_price)
            activation_relative = absolute - start if absolute >= 0 else -1
            trail_results = [(-1, np.nan) for _ in GIVEBACKS]
            # Process short chunks and stop as soon as every giveback variant
            # exits. This avoids scanning years of unused future data when a
            # trail is hit within the next few candles.
            if activation_relative >= 0 and activation_relative + 1 < len(future_high):
                unresolved = set(range(len(GIVEBACKS)))
                cursor = activation_relative + 1
                known_peak = float(future_high[activation_relative])
                chunk_size = 4_096
                while cursor < len(future_high) and unresolved:
                    chunk_end = min(cursor + chunk_size, len(future_high))
                    chunk_high = future_high[cursor:chunk_end]
                    chunk_low = future_low[cursor:chunk_end]
                    prior_peaks = np.maximum.accumulate(
                        np.r_[known_peak, chunk_high[:-1]]
                    )
                    for giveback_index in tuple(unresolved):
                        giveback = GIVEBACKS[giveback_index]
                        trails = entry + (prior_peaks - entry) * (1 - giveback / 100)
                        offset = first_hit(chunk_low <= trails)
                        if offset >= 0:
                            trail_results[giveback_index] = (
                                cursor + offset, float(trails[offset])
                            )
                            unresolved.remove(giveback_index)
                    known_peak = max(known_peak, float(np.max(chunk_high)))
                    cursor = chunk_end

            for giveback_index, (trail_relative, trail_price) in enumerate(trail_results):
                for stop_index, (stop_relative, stop_price) in enumerate(stop_hits):
                    if stop_relative >= 0 and (
                        activation_relative < 0 or stop_relative <= activation_relative
                    ):
                        absolute = start + stop_relative
                        exit_indices[fill_index, activation_index, giveback_index, stop_index] = absolute
                        raw_exits[fill_index, activation_index, giveback_index, stop_index] = min(
                            stop_price, opened[absolute]
                        )
                        exit_types[fill_index, activation_index, giveback_index, stop_index] = (
                            3 if stop_relative == activation_relative else 2
                        )
                    elif trail_relative >= 0:
                        absolute = start + trail_relative
                        exit_indices[fill_index, activation_index, giveback_index, stop_index] = absolute
                        raw_exits[fill_index, activation_index, giveback_index, stop_index] = min(
                            trail_price, opened[absolute]
                        )
                        exit_types[fill_index, activation_index, giveback_index, stop_index] = 1
    return exit_indices, raw_exits, exit_types


def portfolio_result(fills: pd.DataFrame, exit_indices: np.ndarray, raw_exits: np.ndarray,
                     exit_types: np.ndarray, raw_close: np.ndarray,
                     activation_index: int, giveback_index: int,
                     stop_index: int, split_index: int,
                     keep_ledger: bool = False) -> tuple[dict, list[dict], dict | None]:
    equity = INITIAL_EQUITY
    peak = equity
    closed_drawdown = 0.0
    available_index = 0
    ignored = 0
    records = []
    open_position = None
    wins = losses = trailing = protective = ambiguous = 0
    fees = slippage = 0.0
    earlier_multiple = 1.0
    later_multiple = 1.0
    entry_indices = fills.entry_index.to_numpy(np.int32)
    entry_fills = fills.entry_fill.to_numpy(float)
    raw_opens = fills.raw_open.to_numpy(float)

    for fill_pos in range(len(fills)):
        entry_index = int(entry_indices[fill_pos])
        if entry_index < available_index:
            ignored += 1
            continue
        entry_fill = float(entry_fills[fill_pos])
        raw_open = float(raw_opens[fill_pos])
        quantity = equity / (entry_fill * (1 + FEE_RATE))
        exit_index = int(exit_indices[fill_pos, activation_index, giveback_index, stop_index])
        if exit_index < 0:
            fill = fills.iloc[fill_pos]
            open_position = {
                "signal_id": fill.signal_id,
                "touch_timestamp": fill.touch_timestamp,
                "entry_timestamp": fill.entry_timestamp,
                "entry_index": entry_index,
                "raw_entry_open": float(fill.raw_open),
                "entry_fill": entry_fill,
                "quantity": quantity,
                "entry_equity_usd": equity,
                "entry_fee_usd": quantity * entry_fill * FEE_RATE,
                "last_price": float(raw_close[-1]),
                "marked_value_usd": quantity * float(raw_close[-1]),
                "status": "open_at_data_end",
            }
            ignored += len(fills) - fill_pos - 1
            fees += open_position["entry_fee_usd"]
            marked_multiple = open_position["marked_value_usd"] / equity
            if entry_index < split_index:
                earlier_multiple *= marked_multiple
            else:
                later_multiple *= marked_multiple
            break

        raw_exit = float(raw_exits[fill_pos, activation_index, giveback_index, stop_index])
        exit_fill = raw_exit * (1 - SLIPPAGE_RATE)
        exit_cash = quantity * exit_fill * (1 - FEE_RATE)
        pnl = exit_cash - equity
        code = int(exit_types[fill_pos, activation_index, giveback_index, stop_index])
        wins += pnl > 0
        losses += pnl < 0
        trailing += code == 1
        protective += code == 2
        ambiguous += code == 3
        entry_fee = quantity * entry_fill * FEE_RATE
        exit_fee = quantity * exit_fill * FEE_RATE
        slip = quantity * (
            entry_fill - raw_open + raw_exit - exit_fill
        )
        fees += entry_fee + exit_fee
        slippage += slip
        trade_multiple = exit_cash / equity
        if entry_index < split_index:
            earlier_multiple *= trade_multiple
        else:
            later_multiple *= trade_multiple
        if keep_ledger:
            fill = fills.iloc[fill_pos]
            records.append({
                "signal_id": fill.signal_id,
                "touch_timestamp": fill.touch_timestamp,
                "confirmation_timestamp": fill.confirmation_timestamp,
                "entry_timestamp": fill.entry_timestamp,
                "exit_index": exit_index,
                "raw_entry_open": raw_open,
                "entry_fill": entry_fill,
                "raw_exit_price": raw_exit,
                "exit_fill": exit_fill,
                "duration_minutes": exit_index - entry_index + 1,
                "entry_equity_usd": equity,
                "quantity": quantity,
                "entry_fee_usd": entry_fee,
                "exit_fee_usd": exit_fee,
                "slippage_usd": slip,
                "exit_cash_usd": exit_cash,
                "realized_pnl_usd": pnl,
                "net_return_pct": (exit_cash / equity - 1) * 100,
                "exit_type": {1: "trailing_stop", 2: "protective_stop", 3: "ambiguous_stop"}[code],
            })
        equity = exit_cash
        peak = max(peak, equity)
        closed_drawdown = min(closed_drawdown, (equity / peak - 1) * 100)
        available_index = exit_index + 1

    ending = float(open_position["marked_value_usd"]) if open_position else equity
    trades = wins + losses
    result = {
        "completed_trades": trades,
        "ignored_signals_while_position_open": ignored,
        "open_position_at_data_end": int(open_position is not None),
        "wins_after_costs": int(wins),
        "losses_after_costs": int(losses),
        "win_rate_after_costs_pct": wins / trades * 100 if trades else np.nan,
        "trailing_exits": int(trailing),
        "protective_stops": int(protective),
        "ambiguous_stops": int(ambiguous),
        "realized_equity_usd": equity,
        "ending_marked_equity_usd": ending,
        "total_return_pct": (ending / INITIAL_EQUITY - 1) * 100,
        "max_closed_equity_drawdown_pct": closed_drawdown,
        "fees_paid_usd": fees,
        "slippage_usd": slippage,
        "earlier_period_return_pct": (earlier_multiple - 1) * 100,
        "later_period_return_pct": (later_multiple - 1) * 100,
        "minimum_period_return_pct": min(earlier_multiple, later_multiple) * 100 - 100,
    }
    return result, records, open_position


def marked_curve(ledger: pd.DataFrame, open_position: dict | None,
                 raw: pd.DataFrame) -> pd.DataFrame:
    times = pd.DatetimeIndex(raw.open_time)
    values = np.full(len(raw), INITIAL_EQUITY, dtype=float)
    current = INITIAL_EQUITY
    cursor = 0
    positions = ledger.to_dict("records")
    if open_position:
        positions.append(open_position)
    for position in positions:
        entry = int(times.searchsorted(position["entry_timestamp"]))
        values[cursor:entry] = current
        if "exit_index" in position:
            exit_index = int(position["exit_index"])
            values[entry:exit_index] = (
                float(position["quantity"]) * raw.close.iloc[entry:exit_index].to_numpy(float)
            )
            current = float(position["exit_cash_usd"])
            values[exit_index] = current
            cursor = exit_index + 1
        else:
            values[entry:] = (
                float(position["quantity"]) * raw.close.iloc[entry:].to_numpy(float)
            )
            cursor = len(raw)
    values[cursor:] = current
    peaks = np.maximum.accumulate(values)
    return pd.DataFrame({
        "timestamp": times + pd.Timedelta(minutes=1),
        "marked_equity_usd": values,
        "drawdown_pct": (values / peaks - 1) * 100,
    })


def main() -> None:
    raw = pd.read_parquet(RAW_PATH, columns=["open_time", "open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    raw_open = pd.Series(raw.open.to_numpy(float), index=times)
    raw_arrays = {name: raw[name].to_numpy(float) for name in ["open", "high", "low", "close"]}
    threshold_index = ThresholdIndex(raw_arrays["high"], raw_arrays["low"])
    split_index = int(times.searchsorted(pd.Timestamp("2025-09-01", tz="UTC")))
    # Each value is known at the next minute open; current-candle closes are excluded.
    rolling_averages = {
        label: raw.close.rolling(minutes, min_periods=minutes).mean().shift(1).to_numpy(float)
        for label, minutes in AVERAGES.items()
    }
    leaderboard_rows = []
    diagnostics_rows = []

    for signal_minutes in SIGNAL_MINUTES:
        frame = signal_frame(raw, signal_minutes)
        raw_indices = times.searchsorted(pd.DatetimeIndex(frame.open_time))
        for average_label, average_minutes in AVERAGES.items():
            average = rolling_averages[average_label][raw_indices]
            fills, diagnostics = generate_confirmed_fills(
                frame, average, signal_minutes, raw_open, average_label
            )
            diagnostics_rows.append({
                "signal_minutes": signal_minutes,
                "average": average_label,
                "average_minutes": average_minutes,
                **diagnostics,
            })
            exit_indices, raw_exits, exit_types = precompute_outcomes(
                fills, raw_arrays, threshold_index
            )
            for ai, activation in enumerate(ACTIVATIONS):
                for gi, giveback in enumerate(GIVEBACKS):
                    for si, stop in enumerate(STOPS):
                        result, _, _ = portfolio_result(
                            fills, exit_indices, raw_exits, exit_types, raw_arrays["close"],
                            ai, gi, si, split_index,
                        )
                        leaderboard_rows.append({
                            "signal_minutes": signal_minutes,
                            "average": average_label,
                            "average_minutes": average_minutes,
                            "activation_pct": activation,
                            "giveback_pct": giveback,
                            "stop_pct": stop,
                            **result,
                        })
            print(f"completed {signal_minutes}m / {average_label}: {len(fills)} signals", flush=True)

    leaderboard = pd.DataFrame(leaderboard_rows).sort_values(
        ["ending_marked_equity_usd", "max_closed_equity_drawdown_pct"],
        ascending=[False, False],
    ).reset_index(drop=True)
    leaderboard.insert(0, "rank", np.arange(1, len(leaderboard) + 1))
    diagnostics = pd.DataFrame(diagnostics_rows)
    best = leaderboard.iloc[0].to_dict()
    positive_both = leaderboard.loc[
        (leaderboard.earlier_period_return_pct > 0)
        & (leaderboard.later_period_return_pct > 0)
    ].copy()
    balanced = None
    if len(positive_both):
        balanced = positive_both.sort_values(
            ["minimum_period_return_pct", "ending_marked_equity_usd"],
            ascending=False,
        ).iloc[0].to_dict()
    key = (int(best["signal_minutes"]), str(best["average"]))
    best_frame = signal_frame(raw, key[0])
    best_raw_indices = times.searchsorted(pd.DatetimeIndex(best_frame.open_time))
    fills, _ = generate_confirmed_fills(
        best_frame,
        rolling_averages[key[1]][best_raw_indices],
        key[0], raw_open, key[1],
    )
    exit_indices, raw_exits, exit_types = precompute_outcomes(
        fills, raw_arrays, threshold_index
    )
    ai = ACTIVATIONS.index(float(best["activation_pct"]))
    gi = GIVEBACKS.index(float(best["giveback_pct"]))
    si = STOPS.index(float(best["stop_pct"]))
    _, records, open_position = portfolio_result(
        fills, exit_indices, raw_exits, exit_types, raw_arrays["close"],
        ai, gi, si, split_index, keep_ledger=True,
    )
    ledger = pd.DataFrame(records)
    if len(ledger):
        ledger["exit_timestamp"] = times[ledger.exit_index.to_numpy(int)] + pd.Timedelta(minutes=1)
    curve = marked_curve(ledger, open_position, raw)
    best["maximum_mark_to_market_drawdown_pct"] = float(curve.drawdown_pct.min())
    best["lowest_marked_equity_usd"] = float(curve.marked_equity_usd.min())
    best["data_start_utc"] = str(curve.timestamp.iloc[0])
    best["data_end_utc"] = str(curve.timestamp.iloc[-1])
    if open_position:
        best["open_position"] = {
            name: (str(value) if isinstance(value, pd.Timestamp) else value)
            for name, value in open_position.items() if name != "quantity"
        }

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    leaderboard.to_csv(RESULT_DIR / "leaderboard_6048.csv", index=False)
    diagnostics.to_csv(RESULT_DIR / "entry_diagnostics.csv", index=False)
    ledger.to_csv(DATA_DIR / "best_trade_ledger.csv", index=False)
    ledger.to_parquet(DATA_DIR / "best_trade_ledger.parquet", index=False)
    curve.to_parquet(DATA_DIR / "best_account_curve_1m.parquet", index=False)
    (RESULT_DIR / "best_result.json").write_text(json.dumps(best, indent=2) + "\n")
    if balanced is not None:
        (RESULT_DIR / "balanced_candidate.json").write_text(
            json.dumps(balanced, indent=2) + "\n"
        )

    config = {
        "experiment_id": EXPERIMENT_ID,
        "status": "historical_grid_not_deployed",
        "combination_count": len(leaderboard),
        "signal_candle_minutes": SIGNAL_MINUTES,
        "rolling_sma_lengths_minutes": AVERAGES,
        "average_causality": "rolling SMA of completed 1m closes, available at signal candle open",
        "entry": {
            "touch_zone_pct": TOUCH_ZONE_PCT,
            "approach": "from_below",
            "confirmation": "first bullish signal candle within 30 minutes",
            "market_filter": "reject completed-daily-close regime 7d < 15d < 30d",
        },
        "exit": {
            "activation_pct_grid": ACTIVATIONS,
            "giveback_pct_grid": GIVEBACKS,
            "protective_stop_pct_grid": STOPS,
            "time_exit": None,
        },
        "portfolio": {"initial_equity_usd": 100, "positions": 1, "allocation_pct": 100},
        "costs": {"fee_bps_per_side": 10, "slippage_bps_per_side": 2},
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")

    top_lines = [
        "| Rank | Candle | Average | Activate | Giveback | Stop | Trades | Win rate | Final $100 | Closed DD |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in leaderboard.head(20).itertuples(index=False):
        activation = "Immediate" if row.activation_pct == 0 else f"+{row.activation_pct:g}%"
        top_lines.append(
            f"| {row.rank} | {row.signal_minutes}m | {row.average} | {activation} | "
            f"{row.giveback_pct:g}% | −{row.stop_pct:g}% | {row.completed_trades} | "
            f"{row.win_rate_after_costs_pct:.2f}% | ${row.ending_marked_equity_usd:.2f} | "
            f"{row.max_closed_equity_drawdown_pct:.2f}% |"
        )
    report = f"""# SOL Full Moving-Average, Signal-Candle, and Exit Grid

## Search

The replay tested all **{len(leaderboard):,}** requested combinations across 1-, 3-, and 5-minute signal candles; twelve causal rolling simple moving averages from 1 minute through 30 days; immediate through +4% trailing activation; 10%, 15%, and 20% peak-profit giveback; and −1% through −4% protective stops. Every entry uses bullish confirmation, one 100%-equity spot position, realistic fees/slippage, and no time exit.

## Best in-sample result

- Signal candle: **{int(best['signal_minutes'])} minute**
- Rolling average: **{best['average']}**
- Trailing activation: **{'Immediate' if best['activation_pct'] == 0 else f"+{best['activation_pct']:g}%"}**
- Giveback: **{best['giveback_pct']:g}%**
- Protective stop: **−{best['stop_pct']:g}%**
- Final $100 account: **${best['ending_marked_equity_usd']:.2f}**
- Total return: **{best['total_return_pct']:+.2f}%**
- Completed trades: **{best['completed_trades']}**
- Wins / losses: **{best['wins_after_costs']} / {best['losses_after_costs']}**
- Win rate: **{best['win_rate_after_costs_pct']:.2f}%**
- Maximum minute-marked drawdown: **{best['maximum_mark_to_market_drawdown_pct']:.2f}%**
- Earlier / later return: **{best['earlier_period_return_pct']:+.2f}% / {best['later_period_return_pct']:+.2f}%**

## Best candidate positive in both periods

{f"- Signal / average: **{int(balanced['signal_minutes'])}m / {balanced['average']}**; activation **{balanced['activation_pct']:g}%**; giveback **{balanced['giveback_pct']:g}%**; stop **−{balanced['stop_pct']:g}%**; full return **{balanced['total_return_pct']:+.2f}%**; earlier/later **{balanced['earlier_period_return_pct']:+.2f}% / {balanced['later_period_return_pct']:+.2f}%**." if balanced is not None else "No configuration was profitable in both periods."}

## Top 20

{chr(10).join(top_lines)}

## Research limit

This is a large in-sample parameter search. The highest-ranked row is a hypothesis selected from 6,048 attempts, not a frozen strategy. It requires chronological holdout and forward-paper validation before use.
"""
    (RESULT_DIR / "REPORT.md").write_text(report)
    print(json.dumps(best, indent=2))
    print("\nTOP 20\n" + leaderboard.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
