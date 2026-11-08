"""Grid-test immediate 15-day-average touches with trailing-only exits."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
EXPERIMENT_ID = "sol_15d_immediate_touch_trailing_only_grid_v1"
RESULT_DIR = ROOT / "results" / EXPERIMENT_ID
DATA_DIR = ROOT / "data" / EXPERIMENT_ID
CONFIG_PATH = ROOT / "config/experiments" / f"{EXPERIMENT_ID}.json"
RAW_PATH = PROJECT / "stage1_research/data/raw/SOLUSDT/SOLUSDT_1m.parquet"
SIGNAL_PATH = PROJECT / "stage1_research/data/processed/SOLUSDT/SOLUSDT_3m_with_averages.parquet"

ACTIVATIONS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
GIVEBACKS = [10.0, 15.0, 20.0]
TOUCH_ZONE_PCT = 0.2
INITIAL_EQUITY = 100.0
FEE_RATE = 10.0 / 10_000
SLIPPAGE_RATE = 2.0 / 10_000


def immediate_touch_fills(signal: pd.DataFrame, raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Enter at the boundary after the first completed from-below touch candle."""
    zone = TOUCH_ZONE_PCT / 100
    prior = signal.shift(1)
    finite_average = np.isfinite(signal.average_15d)
    touched = (
        finite_average
        & (signal.high >= signal.average_15d * (1 - zone))
        & (signal.low <= signal.average_15d * (1 + zone))
    )
    new_episode = touched & ~touched.shift(1, fill_value=False)
    from_below = (
        new_episode
        & np.isfinite(prior.average_15d)
        & (prior.high < prior.average_15d * (1 - zone))
    )
    finite_regime = np.isfinite(signal[["average_7d", "average_15d", "average_30d"]]).all(axis=1)
    bearish = (
        (signal.average_7d < signal.average_15d)
        & (signal.average_15d < signal.average_30d)
    )
    eligible = from_below & finite_regime & ~bearish
    selected = signal.loc[eligible, ["open_time", "average_15d"]].copy()
    selected["entry_timestamp"] = selected.open_time + pd.Timedelta(minutes=3)
    raw_open = raw.set_index("open_time").open
    selected["raw_open"] = selected.entry_timestamp.map(raw_open)
    if selected.raw_open.isna().any():
        raise ValueError("An immediate entry boundary is absent from raw data")
    selected["entry_fill"] = selected.raw_open * (1 + SLIPPAGE_RATE)
    selected["signal_id"] = [f"immediate-touch-{i:04d}" for i in range(1, len(selected) + 1)]
    selected = selected.rename(columns={"open_time": "touch_timestamp"})
    return selected.reset_index(drop=True), {
        "touch_episodes": int(new_episode.sum()),
        "from_below_episodes": int(from_below.sum()),
        "bearish_or_missing_rejections": int((from_below & (~finite_regime | bearish)).sum()),
        "immediate_entry_signals": len(selected),
    }


def find_trailing_exit(start: int, entry_fill: float, raw_arrays: dict[str, np.ndarray],
                       activation_pct: float, giveback_pct: float) -> dict | None:
    """Return the first causal trailing exit, or None when still open at data end."""
    activation_price = entry_fill * (1 + activation_pct / 100)
    giveback = giveback_pct / 100
    active = False
    peak = entry_fill
    opened = raw_arrays["open"]
    high = raw_arrays["high"]
    low = raw_arrays["low"]

    for index in range(start, len(opened)):
        if not active:
            if high[index] >= activation_price:
                active = True
                peak = max(entry_fill, high[index])
            continue
        trail = entry_fill + (peak - entry_fill) * (1 - giveback)
        if low[index] <= trail:
            return {
                "exit_index": index,
                "raw_exit": min(trail, opened[index]),
                "peak_price": peak,
                "trailing_activated": True,
            }
        peak = max(peak, high[index])
    return None


def run_combination(fills: pd.DataFrame, raw: pd.DataFrame,
                    activation_pct: float, giveback_pct: float) -> tuple[pd.DataFrame, dict | None, dict]:
    times = pd.DatetimeIndex(raw.open_time)
    arrays = {name: raw[name].to_numpy(float) for name in ["open", "high", "low", "close"]}
    available_index = 0
    equity = INITIAL_EQUITY
    completed = []
    open_position = None
    ignored = 0

    for signal in fills.itertuples(index=False):
        entry_index = int(times.searchsorted(signal.entry_timestamp))
        if entry_index < available_index:
            ignored += 1
            continue
        quantity = equity / (float(signal.entry_fill) * (1 + FEE_RATE))
        exit_result = find_trailing_exit(
            entry_index, float(signal.entry_fill), arrays, activation_pct, giveback_pct
        )
        if exit_result is None:
            open_position = {
                "signal_id": signal.signal_id,
                "touch_timestamp": signal.touch_timestamp,
                "entry_timestamp": signal.entry_timestamp,
                "entry_index": entry_index,
                "raw_entry_open": float(signal.raw_open),
                "entry_fill": float(signal.entry_fill),
                "quantity": quantity,
                "entry_equity_usd": equity,
                "entry_fee_usd": quantity * float(signal.entry_fill) * FEE_RATE,
                "last_price": float(arrays["close"][-1]),
                "marked_value_usd": quantity * float(arrays["close"][-1]),
                "unrealized_return_pct": (
                    quantity * float(arrays["close"][-1]) / equity - 1
                ) * 100,
                "status": "open_at_data_end_no_permitted_exit",
            }
            ignored += int((fills.entry_timestamp > signal.entry_timestamp).sum())
            break

        exit_index = int(exit_result["exit_index"])
        exit_fill = float(exit_result["raw_exit"]) * (1 - SLIPPAGE_RATE)
        exit_cash = quantity * exit_fill * (1 - FEE_RATE)
        net_return = (exit_cash / equity - 1) * 100
        completed.append({
            "signal_id": signal.signal_id,
            "activation_pct": activation_pct,
            "giveback_pct_of_open_profit": giveback_pct,
            "touch_timestamp": signal.touch_timestamp,
            "entry_timestamp": signal.entry_timestamp,
            "exit_timestamp": times[exit_index] + pd.Timedelta(minutes=1),
            "raw_entry_open": float(signal.raw_open),
            "entry_fill": float(signal.entry_fill),
            "raw_exit_price": float(exit_result["raw_exit"]),
            "exit_fill": exit_fill,
            "peak_price": float(exit_result["peak_price"]),
            "duration_minutes": exit_index - entry_index + 1,
            "entry_equity_usd": equity,
            "quantity": quantity,
            "entry_fee_usd": quantity * float(signal.entry_fill) * FEE_RATE,
            "exit_fee_usd": quantity * exit_fill * FEE_RATE,
            "slippage_usd": quantity * (
                float(signal.entry_fill) - float(signal.raw_open)
                + float(exit_result["raw_exit"]) - exit_fill
            ),
            "exit_cash_usd": exit_cash,
            "realized_pnl_usd": exit_cash - equity,
            "net_return_pct": net_return,
            "exit_type": "trailing_stop",
        })
        equity = exit_cash
        available_index = exit_index + 1

    ending_marked_equity = (
        float(open_position["marked_value_usd"]) if open_position is not None else equity
    )
    ledger = pd.DataFrame(completed)
    stats = {
        "activation_pct": activation_pct,
        "giveback_pct_of_open_profit": giveback_pct,
        "completed_trades": len(ledger),
        "ignored_signals_while_position_open": ignored,
        "open_position_at_data_end": int(open_position is not None),
        "wins_after_costs": int((ledger.net_return_pct > 0).sum()) if len(ledger) else 0,
        "losses_after_costs": int((ledger.net_return_pct < 0).sum()) if len(ledger) else 0,
        "win_rate_after_costs_pct": float((ledger.net_return_pct > 0).mean() * 100) if len(ledger) else np.nan,
        "mean_duration_minutes": float(ledger.duration_minutes.mean()) if len(ledger) else np.nan,
        "median_duration_minutes": float(ledger.duration_minutes.median()) if len(ledger) else np.nan,
        "longest_completed_trade_minutes": int(ledger.duration_minutes.max()) if len(ledger) else 0,
        "realized_equity_usd": equity,
        "ending_marked_equity_usd": ending_marked_equity,
        "marked_total_return_pct": (ending_marked_equity / INITIAL_EQUITY - 1) * 100,
        "fees_paid_usd": float((ledger.entry_fee_usd + ledger.exit_fee_usd).sum())
            + (float(open_position["entry_fee_usd"]) if open_position is not None else 0),
        "slippage_on_completed_trades_usd": float(ledger.slippage_usd.sum()) if len(ledger) else 0.0,
    }
    return ledger, open_position, stats


def marked_curve(ledger: pd.DataFrame, open_position: dict | None,
                 raw: pd.DataFrame) -> pd.DataFrame:
    """Build the best candidate's causal cash/market-value curve."""
    times = pd.DatetimeIndex(raw.open_time)
    values = np.full(len(raw), INITIAL_EQUITY, dtype=float)
    cursor = 0
    current_equity = INITIAL_EQUITY
    positions = list(ledger.to_dict("records"))
    if open_position is not None:
        positions.append(open_position)
    for position in positions:
        entry_index = int(times.searchsorted(position["entry_timestamp"]))
        values[cursor:entry_index] = current_equity
        if "exit_timestamp" in position:
            exit_index = int(times.searchsorted(position["exit_timestamp"])) - 1
            values[entry_index:exit_index] = (
                float(position["quantity"]) * raw.close.iloc[entry_index:exit_index].to_numpy(float)
            )
            current_equity = float(position["exit_cash_usd"])
            values[exit_index] = current_equity
            cursor = exit_index + 1
        else:
            values[entry_index:] = (
                float(position["quantity"]) * raw.close.iloc[entry_index:].to_numpy(float)
            )
            cursor = len(raw)
    values[cursor:] = current_equity
    peaks = np.maximum.accumulate(values)
    return pd.DataFrame({
        "timestamp": times + pd.Timedelta(minutes=1),
        "marked_equity_usd": values,
        "drawdown_pct": (values / peaks - 1) * 100,
    })


def main() -> None:
    raw = pd.read_parquet(RAW_PATH, columns=["open_time", "open", "high", "low", "close"])
    signal = pd.read_parquet(SIGNAL_PATH, columns=[
        "open_time", "open", "high", "low", "close",
        "average_7d", "average_15d", "average_30d",
    ])
    fills, diagnostics = immediate_touch_fills(signal, raw)
    rows = []
    outputs = {}
    for activation in ACTIVATIONS:
        for giveback in GIVEBACKS:
            ledger, open_position, stats = run_combination(
                fills, raw, activation, giveback
            )
            rows.append(stats)
            outputs[(activation, giveback)] = (ledger, open_position)

    leaderboard = pd.DataFrame(rows).sort_values(
        ["ending_marked_equity_usd", "realized_equity_usd"], ascending=False
    ).reset_index(drop=True)
    leaderboard.insert(0, "rank", np.arange(1, len(leaderboard) + 1))
    best = leaderboard.iloc[0].to_dict()
    key = (float(best["activation_pct"]), float(best["giveback_pct_of_open_profit"]))
    best_ledger, best_open = outputs[key]
    curve = marked_curve(best_ledger, best_open, raw)
    best["maximum_mark_to_market_drawdown_pct"] = float(curve.drawdown_pct.min())
    best["lowest_marked_equity_usd"] = float(curve.marked_equity_usd.min())
    best["entry_diagnostics"] = diagnostics
    best["data_start_utc"] = str(curve.timestamp.iloc[0])
    best["data_end_utc"] = str(curve.timestamp.iloc[-1])
    if best_open is not None:
        best["open_position"] = {
            key: (str(value) if isinstance(value, pd.Timestamp) else value)
            for key, value in best_open.items()
            if key != "quantity"
        }

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    leaderboard.to_csv(RESULT_DIR / "leaderboard.csv", index=False)
    best_ledger.to_csv(DATA_DIR / "best_completed_trade_ledger.csv", index=False)
    best_ledger.to_parquet(DATA_DIR / "best_completed_trade_ledger.parquet", index=False)
    curve.to_parquet(DATA_DIR / "best_marked_account_curve_1m.parquet", index=False)
    (RESULT_DIR / "best_result.json").write_text(json.dumps(best, indent=2) + "\n")

    config = {
        "experiment_id": EXPERIMENT_ID,
        "status": "historical_grid_not_deployed",
        "entry": {
            "touch_zone_pct": TOUCH_ZONE_PCT,
            "approach": "from_below",
            "timing": "raw_1m open after first completed touching 3m candle",
            "bullish_confirmation": False,
            "market_filter": "reject 7d < 15d < 30d",
        },
        "exit": {
            "only_permitted_exit": "trailing_stop_after_activation",
            "hard_stop": None,
            "maximum_hold": None,
            "activation_pct_grid": ACTIVATIONS,
            "open_profit_giveback_pct_grid": GIVEBACKS,
            "activation_candle_can_exit": False,
            "trail_uses_prior_completed_1m_peak": True,
        },
        "portfolio": {"initial_equity_usd": 100, "maximum_positions": 1, "allocation_pct": 100},
        "costs": {"fee_bps_per_side": 10, "slippage_bps_per_side": 2},
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")

    table_lines = [
        "| Rank | Activate | Giveback | Completed | Wins | Losses | Win rate | Open at end | Final marked $100 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in leaderboard.itertuples(index=False):
        table_lines.append(
            f"| {row.rank} | +{row.activation_pct:g}% | {row.giveback_pct_of_open_profit:g}% | "
            f"{row.completed_trades} | {row.wins_after_costs} | {row.losses_after_costs} | "
            f"{row.win_rate_after_costs_pct:.2f}% | {row.open_position_at_data_end} | "
            f"${row.ending_marked_equity_usd:.2f} |"
        )
    open_note = (
        f"The final position remains open from **{best_open['entry_timestamp']}** and is marked at "
        f"**${best_open['marked_value_usd']:.2f}** at the last SOL close."
        if best_open is not None else "The best combination has no open position at data end."
    )
    report = f"""# SOL Immediate Touch, Trailing-Only Exit Grid

## Rules

Buy at the raw one-minute open immediately after the first completed 3-minute candle touches the ±0.2% zone from below. The existing strong-bearish market filter remains. There is no bullish confirmation, hard stop, or time exit. One position receives 100% of current equity. The only sale is a causal trailing stop after the selected activation threshold. Results include 10 bps fees and 2 bps adverse slippage per side.

## Best full-history marked result

- Activation: **+{best['activation_pct']:g}%**
- Giveback of peak open profit: **{best['giveback_pct_of_open_profit']:g}%**
- Completed trades: **{best['completed_trades']}**
- Wins / losses after costs: **{best['wins_after_costs']} / {best['losses_after_costs']}**
- Completed-trade win rate: **{best['win_rate_after_costs_pct']:.2f}%**
- Realized equity before the open final position: **${best['realized_equity_usd']:.2f}**
- Final marked equity: **${best['ending_marked_equity_usd']:.2f}**
- Marked return: **{best['marked_total_return_pct']:+.2f}%**
- Maximum minute-marked drawdown: **{best['maximum_mark_to_market_drawdown_pct']:.2f}%**

{open_note}

## All combinations

{chr(10).join(table_lines)}

## Interpretation limit

Completed-trade win rate excludes the final open position. Because this strategy forbids every other exit, an unactivated position can remain invested indefinitely and block all later signals. Final ranking therefore uses marked account value, not a fabricated data-end sale.
"""
    (RESULT_DIR / "REPORT.md").write_text(report)
    print(json.dumps(best, indent=2))
    print("\n" + leaderboard.to_string(index=False))


if __name__ == "__main__":
    main()
