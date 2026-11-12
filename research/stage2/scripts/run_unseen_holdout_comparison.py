"""Compare the frozen SOL strategy and 1m/30d candidate on unseen later data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import zipfile

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from run_sol_full_ma_signal_exit_grid import (  # noqa: E402
    ACTIVATIONS,
    GIVEBACKS,
    STOPS,
    ThresholdIndex,
    generate_confirmed_fills,
    precompute_outcomes,
    portfolio_result,
)


EXPERIMENT_ID = "unseen_holdout_fair_comparison_v1"
RESULT_DIR = ROOT / "results" / EXPERIMENT_ID
DATA_DIR = ROOT / "data" / EXPERIMENT_ID
DOWNLOAD_DIR = ROOT / "data/holdout_downloads"
HISTORY_PATH = PROJECT / "stage1/data/raw/SOLUSDT/SOLUSDT_1m.parquet"
HOLDOUT_START = pd.Timestamp("2026-08-01", tz="UTC")
HOLDOUT_END = pd.Timestamp("2026-09-10", tz="UTC")
FEE_RATE = 10.0 / 10_000
SLIPPAGE_RATE = 2.0 / 10_000

COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "number_of_trades", "taker_buy_base_volume",
    "taker_buy_quote_volume", "ignore",
]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def load_holdout() -> pd.DataFrame:
    parts = []
    archives = sorted(DOWNLOAD_DIR.glob("SOLUSDT-1m-*.zip"))
    if len(archives) != 10:
        raise ValueError(f"Expected 10 Binance archives, found {len(archives)}")
    for path in archives:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".csv")]
            if len(names) != 1:
                raise ValueError(f"Unexpected archive contents: {path}")
            with archive.open(names[0]) as stream:
                frame = pd.read_csv(stream, header=None, names=COLUMNS)
        unit = "us" if frame.open_time.iloc[0] > 10**14 else "ms"
        frame["open_time"] = pd.to_datetime(frame.open_time, unit=unit, utc=True)
        frame["close_time"] = pd.to_datetime(frame.close_time, unit=unit, utc=True)
        parts.append(frame)
    result = pd.concat(parts, ignore_index=True).drop_duplicates("open_time")
    result = result.sort_values("open_time").reset_index(drop=True)
    result = result.loc[
        result.open_time.ge(HOLDOUT_START) & result.open_time.lt(HOLDOUT_END)
    ].reset_index(drop=True)
    for column in ["open", "high", "low", "close", "volume", "quote_volume"]:
        result[column] = pd.to_numeric(result[column], errors="raise")
    times = pd.DatetimeIndex(result.open_time)
    if len(result) != 57_600 or times[0] != HOLDOUT_START or times[-1] != HOLDOUT_END - pd.Timedelta(minutes=1):
        raise ValueError("Holdout does not cover the exact expected period")
    if not ((times[1:] - times[:-1]) == pd.Timedelta(minutes=1)).all():
        raise ValueError("Holdout has a one-minute gap")
    return result


def daily_regime(raw: pd.DataFrame) -> pd.DataFrame:
    daily_close = raw.set_index("open_time").close.resample("1D").last()
    available = daily_close.shift(1)
    result = pd.DataFrame({"open_time": available.index})
    for days in [7, 15, 30]:
        result[f"average_{days}d"] = available.rolling(days, min_periods=days).mean().to_numpy()
    return result


def make_signal_frame(raw: pd.DataFrame, minutes: int, regime: pd.DataFrame) -> pd.DataFrame:
    if minutes == 1:
        frame = raw[["open_time", "open", "high", "low", "close"]].copy()
    else:
        frame = raw.set_index("open_time").resample(
            f"{minutes}min", label="left", closed="left"
        ).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).reset_index()
    return pd.merge_asof(
        frame.sort_values("open_time"), regime.sort_values("open_time"),
        on="open_time", direction="backward",
    )


def restrict_holdout(fills: pd.DataFrame) -> pd.DataFrame:
    return fills.loc[fills.touch_timestamp.ge(HOLDOUT_START)].reset_index(drop=True)


def frozen_selected_trades(fills: pd.DataFrame, raw: pd.DataFrame) -> tuple[pd.DataFrame, dict | None, int]:
    times = pd.DatetimeIndex(raw.open_time)
    opened, high, low, close = [raw[name].to_numpy(float) for name in ["open", "high", "low", "close"]]
    available = 0
    ignored = 0
    rows = []
    open_position = None
    for fill in fills.itertuples(index=False):
        start = int(fill.entry_index)
        if start < available:
            ignored += 1
            continue
        entry = float(fill.entry_fill)
        hard_stop = entry * 0.96
        activation = entry * 1.04
        active = False
        peak = entry
        completed = None
        end = min(start + 1_440, len(raw))
        for index in range(start, end):
            duration = index - start + 1
            if not active:
                activation_hit = high[index] >= activation
                if low[index] <= hard_stop:
                    completed = (
                        index, min(hard_stop, opened[index]),
                        "ambiguous_stop" if activation_hit else "protective_stop",
                    )
                    break
                if activation_hit:
                    active = True
                    peak = max(entry, high[index])
            else:
                trail = entry + 0.90 * (peak - entry)
                if low[index] <= trail:
                    completed = (index, min(trail, opened[index]), "trailing_stop")
                    break
                peak = max(peak, high[index])
            if duration == 1_440:
                completed = (index, close[index], "time")
                break
        if completed is None:
            open_position = {
                "signal_id": fill.signal_id,
                "entry_timestamp": fill.entry_timestamp,
                "entry_index": start,
                "raw_entry_open": float(fill.raw_open),
                "entry_fill": entry,
                "last_price": float(close[-1]),
            }
            ignored += int((fills.entry_timestamp > fill.entry_timestamp).sum())
            break
        index, raw_exit, exit_type = completed
        exit_fill = raw_exit * (1 - SLIPPAGE_RATE)
        rows.append({
            "signal_id": fill.signal_id,
            "touch_timestamp": fill.touch_timestamp,
            "confirmation_timestamp": fill.confirmation_timestamp,
            "entry_timestamp": fill.entry_timestamp,
            "exit_timestamp": times[index] + pd.Timedelta(minutes=1),
            "exit_index": index,
            "raw_entry_open": float(fill.raw_open),
            "entry_fill": entry,
            "raw_exit_price": raw_exit,
            "exit_fill": exit_fill,
            "duration_minutes": index - start + 1,
            "exit_type": exit_type,
        })
        available = index + 1
    return pd.DataFrame(rows), open_position, ignored


def account_result(strategy: str, trades: pd.DataFrame, open_position: dict | None,
                   ignored: int, allocation_fraction: float,
                   raw: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    times = pd.DatetimeIndex(raw.open_time)
    close = raw.close.to_numpy(float)
    holdout_start_index = int(times.searchsorted(HOLDOUT_START))
    values = np.full(len(raw) - holdout_start_index, 100.0)
    equity = 100.0
    peak = equity
    cursor = holdout_start_index
    wins = losses = 0
    fees = slippage = 0.0
    rows = []
    for trade in trades.itertuples(index=False):
        entry_index = int(times.searchsorted(trade.entry_timestamp))
        exit_index = int(trade.exit_index)
        values[cursor - holdout_start_index:entry_index - holdout_start_index] = equity
        allocation = equity * allocation_fraction
        cash = equity - allocation
        quantity = allocation / (float(trade.entry_fill) * (1 + FEE_RATE))
        values[entry_index - holdout_start_index:exit_index - holdout_start_index] = (
            cash + quantity * close[entry_index:exit_index]
        )
        exit_cash = quantity * float(trade.exit_fill) * (1 - FEE_RATE)
        next_equity = cash + exit_cash
        pnl = next_equity - equity
        wins += pnl > 0
        losses += pnl < 0
        entry_fee = quantity * float(trade.entry_fill) * FEE_RATE
        exit_fee = quantity * float(trade.exit_fill) * FEE_RATE
        slip = quantity * (
            float(trade.entry_fill) - float(trade.raw_entry_open)
            + float(trade.raw_exit_price) - float(trade.exit_fill)
        )
        fees += entry_fee + exit_fee
        slippage += slip
        row = trade._asdict()
        row.update({
            "allocation_fraction": allocation_fraction,
            "entry_equity_usd": equity,
            "allocation_usd": allocation,
            "quantity": quantity,
            "realized_pnl_usd": pnl,
            "ending_equity_usd": next_equity,
        })
        rows.append(row)
        equity = next_equity
        values[exit_index - holdout_start_index] = equity
        cursor = exit_index + 1
        peak = max(peak, equity)
    if open_position:
        entry_index = int(open_position["entry_index"])
        values[cursor - holdout_start_index:entry_index - holdout_start_index] = equity
        allocation = equity * allocation_fraction
        cash = equity - allocation
        quantity = allocation / (float(open_position["entry_fill"]) * (1 + FEE_RATE))
        values[entry_index - holdout_start_index:] = cash + quantity * close[entry_index:]
        fees += quantity * float(open_position["entry_fill"]) * FEE_RATE
        equity = float(values[-1])
        open_entry_timestamp = str(open_position["entry_timestamp"])
        open_position_return_pct = (
            quantity * float(close[-1]) / allocation - 1
        ) * 100
    else:
        values[cursor - holdout_start_index:] = equity
        open_entry_timestamp = None
        open_position_return_pct = None
    running_peak = np.maximum.accumulate(values)
    curve = pd.DataFrame({
        "timestamp": times[holdout_start_index:] + pd.Timedelta(minutes=1),
        "equity_usd": values,
        "drawdown_pct": (values / running_peak - 1) * 100,
    })
    count = wins + losses
    return {
        "strategy": strategy,
        "allocation_pct": allocation_fraction * 100,
        "confirmed_signals": len(trades) + ignored + int(open_position is not None),
        "completed_trades": count,
        "ignored_signals_while_position_open": ignored,
        "open_position_at_end": int(open_position is not None),
        "open_position_entry_timestamp": open_entry_timestamp,
        "open_position_return_pct": open_position_return_pct,
        "wins": int(wins),
        "losses": int(losses),
        "win_rate_pct": wins / count * 100 if count else np.nan,
        "ending_marked_equity_usd": equity,
        "return_pct": equity - 100,
        "maximum_mark_to_market_drawdown_pct": float(curve.drawdown_pct.min()),
        "fees_usd": fees,
        "slippage_usd": slippage,
    }, pd.DataFrame(rows)


def main() -> None:
    holdout = load_holdout()
    history = pd.read_parquet(HISTORY_PATH)
    raw = pd.concat([history, holdout], ignore_index=True)
    raw = raw.sort_values("open_time").drop_duplicates("open_time").reset_index(drop=True)
    times = pd.DatetimeIndex(raw.open_time)
    if not ((times[1:] - times[:-1]) == pd.Timedelta(minutes=1)).all():
        raise ValueError("Combined warm-up and holdout data are not continuous")
    regime = daily_regime(raw)
    raw_open = pd.Series(raw.open.to_numpy(float), index=times)

    # Frozen strategy signals: 3m candle and completed-daily-close 15d SMA.
    frozen_frame = make_signal_frame(raw, 3, regime)
    frozen_fills, frozen_diagnostics = generate_confirmed_fills(
        frozen_frame,
        frozen_frame.average_15d.to_numpy(float),
        3,
        raw_open,
        "daily15d",
        touch_zone_pct=0.5,
    )
    frozen_fills = restrict_holdout(frozen_fills)
    frozen_trades, frozen_open, frozen_ignored = frozen_selected_trades(
        frozen_fills, raw
    )

    # New candidate signals: 1m candle and 43,200-completed-minute SMA.
    candidate_frame = make_signal_frame(raw, 1, regime)
    rolling_30d = raw.close.rolling(43_200, min_periods=43_200).mean().shift(1).to_numpy(float)
    candidate_fills, candidate_diagnostics = generate_confirmed_fills(
        candidate_frame, rolling_30d, 1, raw_open, "rolling30d", touch_zone_pct=0.2
    )
    candidate_fills = restrict_holdout(candidate_fills)
    arrays = {name: raw[name].to_numpy(float) for name in ["open", "high", "low", "close"]}
    threshold = ThresholdIndex(arrays["high"], arrays["low"])
    exit_indices, raw_exits, exit_types = precompute_outcomes(
        candidate_fills, arrays, threshold
    )
    split_index = int(times.searchsorted(HOLDOUT_START))
    _, candidate_records, candidate_open = portfolio_result(
        candidate_fills, exit_indices, raw_exits, exit_types, arrays["close"],
        ACTIVATIONS.index(4.0), GIVEBACKS.index(20.0), STOPS.index(3.0),
        split_index, keep_ledger=True,
    )
    candidate_trades = pd.DataFrame(candidate_records)
    if len(candidate_trades):
        candidate_trades["exit_timestamp"] = (
            times[candidate_trades.exit_index.to_numpy(int)] + pd.Timedelta(minutes=1)
        )
    candidate_ignored = (
        len(candidate_fills) - len(candidate_trades) - int(candidate_open is not None)
    )

    results = []
    ledgers = {}
    for fraction in [0.25, 1.0]:
        frozen_result, frozen_ledger = account_result(
            "current_frozen_3m_daily15d_a4_g10_s4_t24h",
            frozen_trades, frozen_open, frozen_ignored, fraction, raw,
        )
        candidate_result, candidate_ledger = account_result(
            "new_candidate_1m_rolling30d_a4_g20_s3_no_time",
            candidate_trades, candidate_open, candidate_ignored, fraction, raw,
        )
        results.extend([frozen_result, candidate_result])
        ledgers[("frozen", fraction)] = frozen_ledger
        ledgers[("candidate", fraction)] = candidate_ledger
    comparison = pd.DataFrame(results)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    holdout.to_parquet(DATA_DIR / "SOLUSDT_1m_unseen_holdout.parquet", index=False)
    comparison.to_csv(RESULT_DIR / "fair_comparison.csv", index=False)
    for (name, fraction), ledger in ledgers.items():
        ledger.to_csv(DATA_DIR / f"{name}_{int(fraction*100)}pct_ledger.csv", index=False)
    validation = {
        "status": "PASS",
        "holdout_start": str(HOLDOUT_START),
        "holdout_end_exclusive": str(HOLDOUT_END),
        "holdout_minutes": len(holdout),
        "holdout_gaps": 0,
        "training_data_last_minute": str(history.open_time.max()),
        "frozen_entry_diagnostics_full_warmup": frozen_diagnostics,
        "candidate_entry_diagnostics_full_warmup": candidate_diagnostics,
        "frozen_historical_confirmed_signals_through_2026_07_31": (
            frozen_diagnostics["confirmed_signals"] - len(frozen_fills)
        ),
        "candidate_historical_confirmed_signals_through_2026_07_31": (
            candidate_diagnostics["confirmed_signals"] - len(candidate_fills)
        ),
        "frozen_holdout_confirmed_signals": len(frozen_fills),
        "candidate_holdout_confirmed_signals": len(candidate_fills),
        "download_sha256": {
            path.name: digest(path) for path in sorted(DOWNLOAD_DIR.glob("SOLUSDT-1m-*.zip"))
        },
    }
    (RESULT_DIR / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")

    rows = []
    for result in results:
        rows.append(
            f"| {result['allocation_pct']:.0f}% | {result['strategy']} | "
            f"{result['completed_trades']} | {result['wins']} / {result['losses']} | "
            f"{result['win_rate_pct']:.2f}% | ${result['ending_marked_equ_usd'] if False else result['ending_marked_equity_usd']:.2f} | "
            f"{result['return_pct']:+.2f}% | {result['maximum_mark_to_market_drawdown_pct']:.2f}% |"
        )
    report = f"""# Fair Unseen Holdout Comparison

## Holdout

This test uses 57,600 continuous public Binance SOLUSDT one-minute candles from **2026-08-01 through 2026-09-09 UTC**. The earlier research ended on 2026-07-31. Earlier candles are used only to warm indicators; every entry starts inside the unseen holdout.

Both strategies are limited to one position and are compared separately at identical 25% and 100% current-equity allocation. Both use the same 10 bps fee and 2 bps adverse slippage per side.

## Result

| Allocation | Strategy | Trades | Wins / losses | Win rate | Final $100 | Return | Max drawdown |
|---:|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

The 40-day holdout is genuinely later but short. A result with few or zero trades is inconclusive rather than proof of superiority.
"""
    (RESULT_DIR / "REPORT.md").write_text(report)
    print(comparison.to_string(index=False))
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()
