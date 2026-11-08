"""Test protective stops for the +2% activation / 10% giveback SOL candidate."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from run_sol_immediate_trail_experiment import generate_fills  # noqa: E402
from run_sol_trailing_only_grid import marked_curve  # noqa: E402


EXPERIMENT_ID = "sol_15d_confirmed_a2_g10_stop_grid_v1"
RESULT_DIR = ROOT / "results" / EXPERIMENT_ID
DATA_DIR = ROOT / "data" / EXPERIMENT_ID
CONFIG_PATH = ROOT / "config/experiments" / f"{EXPERIMENT_ID}.json"
RAW_PATH = PROJECT / "stage1_research/data/raw/SOLUSDT/SOLUSDT_1m.parquet"
SIGNAL_PATH = PROJECT / "stage1_research/data/processed/SOLUSDT/SOLUSDT_3m_with_averages.parquet"

STOPS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
ACTIVATION_PCT = 2.0
GIVEBACK_PCT = 10.0
INITIAL_EQUITY = 100.0
FEE_RATE = 10.0 / 10_000
SLIPPAGE_RATE = 2.0 / 10_000


def find_exit(start: int, entry_fill: float, raw_arrays: dict[str, np.ndarray],
              stop_pct: float) -> dict | None:
    activation_price = entry_fill * (1 + ACTIVATION_PCT / 100)
    hard_stop = entry_fill * (1 - stop_pct / 100)
    giveback = GIVEBACK_PCT / 100
    active = False
    peak = entry_fill
    opened = raw_arrays["open"]
    high = raw_arrays["high"]
    low = raw_arrays["low"]

    for index in range(start, len(opened)):
        if not active:
            activation_hit = high[index] >= activation_price
            stop_hit = low[index] <= hard_stop
            if stop_hit:
                return {
                    "exit_index": index,
                    "raw_exit": min(hard_stop, opened[index]),
                    "exit_type": "ambiguous_stop" if activation_hit else "protective_stop",
                    "trailing_activated": activation_hit,
                    "peak_price": high[index] if activation_hit else np.nan,
                }
            if activation_hit:
                active = True
                peak = max(entry_fill, high[index])
            continue

        trail = entry_fill + (peak - entry_fill) * (1 - giveback)
        if low[index] <= trail:
            return {
                "exit_index": index,
                "raw_exit": min(trail, opened[index]),
                "exit_type": "trailing_stop",
                "trailing_activated": True,
                "peak_price": peak,
            }
        peak = max(peak, high[index])
    return None


def run_stop(fills: pd.DataFrame, raw: pd.DataFrame,
             stop_pct: float) -> tuple[pd.DataFrame, dict | None, dict]:
    times = pd.DatetimeIndex(raw.open_time)
    arrays = {name: raw[name].to_numpy(float) for name in ["open", "high", "low", "close"]}
    available_index = 0
    equity = INITIAL_EQUITY
    ignored = 0
    completed = []
    open_position = None

    for signal in fills.itertuples(index=False):
        entry_index = int(times.searchsorted(signal.entry_timestamp))
        if entry_index < available_index:
            ignored += 1
            continue
        quantity = equity / (float(signal.entry_fill) * (1 + FEE_RATE))
        result = find_exit(entry_index, float(signal.entry_fill), arrays, stop_pct)
        if result is None:
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
                "status": "open_at_data_end",
            }
            ignored += int((fills.entry_timestamp > signal.entry_timestamp).sum())
            break

        exit_index = int(result["exit_index"])
        raw_exit = float(result["raw_exit"])
        exit_fill = raw_exit * (1 - SLIPPAGE_RATE)
        exit_cash = quantity * exit_fill * (1 - FEE_RATE)
        completed.append({
            "signal_id": signal.signal_id,
            "stop_pct": stop_pct,
            "activation_pct": ACTIVATION_PCT,
            "giveback_pct_of_open_profit": GIVEBACK_PCT,
            "touch_timestamp": signal.touch_timestamp,
            "entry_timestamp": signal.entry_timestamp,
            "exit_timestamp": times[exit_index] + pd.Timedelta(minutes=1),
            "raw_entry_open": float(signal.raw_open),
            "entry_fill": float(signal.entry_fill),
            "raw_exit_price": raw_exit,
            "exit_fill": exit_fill,
            "peak_price": result["peak_price"],
            "trailing_activated": bool(result["trailing_activated"]),
            "duration_minutes": exit_index - entry_index + 1,
            "entry_equity_usd": equity,
            "quantity": quantity,
            "entry_fee_usd": quantity * float(signal.entry_fill) * FEE_RATE,
            "exit_fee_usd": quantity * exit_fill * FEE_RATE,
            "slippage_usd": quantity * (
                float(signal.entry_fill) - float(signal.raw_open) + raw_exit - exit_fill
            ),
            "exit_cash_usd": exit_cash,
            "realized_pnl_usd": exit_cash - equity,
            "net_return_pct": (exit_cash / equity - 1) * 100,
            "exit_type": result["exit_type"],
        })
        equity = exit_cash
        available_index = exit_index + 1

    ledger = pd.DataFrame(completed)
    ending_marked = float(open_position["marked_value_usd"]) if open_position else equity
    pnl = ledger.realized_pnl_usd if len(ledger) else pd.Series(dtype=float)
    wins = pnl > 0
    losses = pnl < 0
    exits = ledger.exit_type.value_counts() if len(ledger) else pd.Series(dtype=int)
    stats = {
        "stop_pct": stop_pct,
        "completed_trades": len(ledger),
        "ignored_signals_while_position_open": ignored,
        "open_position_at_data_end": int(open_position is not None),
        "wins_after_costs": int(wins.sum()),
        "losses_after_costs": int(losses.sum()),
        "win_rate_after_costs_pct": float(wins.mean() * 100) if len(ledger) else np.nan,
        "loss_rate_after_costs_pct": float(losses.mean() * 100) if len(ledger) else np.nan,
        "trailing_activations": int(ledger.trailing_activated.sum()) if len(ledger) else 0,
        "trailing_exits": int(exits.get("trailing_stop", 0)),
        "protective_stops": int(exits.get("protective_stop", 0)),
        "ambiguous_stops": int(exits.get("ambiguous_stop", 0)),
        "mean_duration_minutes": float(ledger.duration_minutes.mean()) if len(ledger) else np.nan,
        "median_duration_minutes": float(ledger.duration_minutes.median()) if len(ledger) else np.nan,
        "realized_equity_usd": equity,
        "ending_marked_equity_usd": ending_marked,
        "total_return_pct": (ending_marked / INITIAL_EQUITY - 1) * 100,
        "fees_paid_usd": float((ledger.entry_fee_usd + ledger.exit_fee_usd).sum())
            + (float(open_position["entry_fee_usd"]) if open_position else 0),
        "slippage_on_completed_trades_usd": float(ledger.slippage_usd.sum()) if len(ledger) else 0,
        "profit_factor_on_dollars": float(pnl[wins].sum() / abs(pnl[losses].sum()))
            if losses.any() else np.inf,
    }
    return ledger, open_position, stats


def main() -> None:
    raw = pd.read_parquet(RAW_PATH, columns=["open_time", "open", "high", "low", "close"])
    signal = pd.read_parquet(SIGNAL_PATH, columns=[
        "open_time", "open", "high", "low", "close",
        "average_7d", "average_15d", "average_30d",
    ])
    fills, diagnostics = generate_fills(signal, slippage_bps=2.0)
    fills = fills.rename(columns={"start_timestamp": "touch_timestamp", "fill_price": "entry_fill"})
    rows = []
    outputs = {}
    for stop in STOPS:
        ledger, open_position, stats = run_stop(fills, raw, stop)
        rows.append(stats)
        outputs[stop] = (ledger, open_position)

    leaderboard = pd.DataFrame(rows).sort_values(
        ["ending_marked_equity_usd", "profit_factor_on_dollars"], ascending=False
    ).reset_index(drop=True)
    leaderboard.insert(0, "rank", np.arange(1, len(leaderboard) + 1))
    best = leaderboard.iloc[0].to_dict()
    best_ledger, best_open = outputs[float(best["stop_pct"])]
    curve = marked_curve(best_ledger, best_open, raw)
    best["maximum_mark_to_market_drawdown_pct"] = float(curve.drawdown_pct.min())
    best["lowest_marked_equity_usd"] = float(curve.marked_equity_usd.min())
    best["entry_diagnostics"] = diagnostics
    best["data_start_utc"] = str(curve.timestamp.iloc[0])
    best["data_end_utc"] = str(curve.timestamp.iloc[-1])
    winning = best_ledger.loc[best_ledger.net_return_pct > 0]
    losing = best_ledger.loc[best_ledger.net_return_pct < 0]
    best["average_winner_pct"] = float(winning.net_return_pct.mean())
    best["average_loser_pct"] = float(losing.net_return_pct.mean())
    gross_returns = best_ledger.raw_exit_price / best_ledger.raw_entry_open - 1
    best["hypothetical_ending_equity_without_costs_usd"] = float(
        INITIAL_EQUITY * np.prod(1 + gross_returns.to_numpy())
    )
    split_at = pd.Timestamp("2025-09-01", tz="UTC")
    for label, segment in {
        "earlier_period": best_ledger.loc[best_ledger.entry_timestamp < split_at],
        "later_period": best_ledger.loc[best_ledger.entry_timestamp >= split_at],
    }.items():
        best[label] = {
            "trades": len(segment),
            "wins": int((segment.net_return_pct > 0).sum()),
            "losses": int((segment.net_return_pct < 0).sum()),
            "compounded_return_pct": float(
                (np.prod(1 + segment.net_return_pct.to_numpy(float) / 100) - 1) * 100
            ),
        }
    if best_open:
        best["open_position"] = {
            name: (str(value) if isinstance(value, pd.Timestamp) else value)
            for name, value in best_open.items() if name != "quantity"
        }

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    leaderboard.to_csv(RESULT_DIR / "leaderboard.csv", index=False)
    best_ledger.to_csv(DATA_DIR / "best_trade_ledger.csv", index=False)
    best_ledger.to_parquet(DATA_DIR / "best_trade_ledger.parquet", index=False)
    curve.to_parquet(DATA_DIR / "best_marked_account_curve_1m.parquet", index=False)
    (RESULT_DIR / "best_result.json").write_text(json.dumps(best, indent=2) + "\n")

    config = {
        "experiment_id": EXPERIMENT_ID,
        "status": "historical_grid_not_deployed",
        "entry": {
            "touch_zone_pct": 0.2,
            "approach": "from_below",
            "confirmation": "bullish 3m candle within 30 minutes",
            "market_filter": "reject 7d < 15d < 30d",
        },
        "trailing": {"activation_pct": ACTIVATION_PCT, "giveback_pct": GIVEBACK_PCT},
        "protective_stop_pct_grid": STOPS,
        "maximum_hold": None,
        "portfolio": {"initial_equity_usd": 100, "positions": 1, "allocation_pct": 100},
        "costs": {"fee_bps_per_side": 10, "slippage_bps_per_side": 2},
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")

    lines = [
        "| Rank | Stop | Trades | Wins | Losses | Win rate | Trail exits | Stop exits | Final $100 | Return |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in leaderboard.itertuples(index=False):
        lines.append(
            f"| {row.rank} | −{row.stop_pct:g}% | {row.completed_trades} | {row.wins_after_costs} | "
            f"{row.losses_after_costs} | {row.win_rate_after_costs_pct:.2f}% | {row.trailing_exits} | "
            f"{row.protective_stops + row.ambiguous_stops} | ${row.ending_marked_equity_usd:.2f} | "
            f"{row.total_return_pct:+.2f}% |"
        )
    report = f"""# SOL +2%/10% Trail — Protective Stop Grid

## Scope

This experiment keeps the confirmed ±0.2% from-below touch entry, +2% trailing activation, 10% giveback of peak open profit, one 100%-equity position, and realistic fees/slippage. It adds protective stops from −1% through −4% in 0.5-point steps. There is no time exit.

## Best full-history result

- Protective stop: **−{best['stop_pct']:g}%**
- Final $100 account: **${best['ending_marked_equity_usd']:.2f}** ({best['total_return_pct']:+.2f}%)
- Completed trades: **{best['completed_trades']}**
- Wins / losses: **{best['wins_after_costs']} / {best['losses_after_costs']}**
- Win rate: **{best['win_rate_after_costs_pct']:.2f}%**
- Trailing exits: **{best['trailing_exits']}**
- Protective or ambiguous stop exits: **{best['protective_stops'] + best['ambiguous_stops']}**
- Profit factor: **{best['profit_factor_on_dollars']:.3f}**
- Maximum minute-marked drawdown: **{best['maximum_mark_to_market_drawdown_pct']:.2f}%**
- Average winner / loser: **{best['average_winner_pct']:+.2f}% / {best['average_loser_pct']:+.2f}%**
- Earlier / later period return: **{best['earlier_period']['compounded_return_pct']:+.2f}% / {best['later_period']['compounded_return_pct']:+.2f}%**

## All stops

{chr(10).join(lines)}

This is an in-sample stop comparison and has not changed the deployed frozen strategy.
"""
    (RESULT_DIR / "REPORT.md").write_text(report)
    print(json.dumps(best, indent=2))
    print("\n" + leaderboard.to_string(index=False))


if __name__ == "__main__":
    main()
