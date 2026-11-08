"""Test the requested SOL trailing activation/giveback grid end to end."""

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

from src.backtesting.account import build_account_curve, select_spot_lots  # noqa: E402
from src.backtesting.costs import apply_costs  # noqa: E402
from run_sol_immediate_trail_experiment import generate_fills, select_while_flat  # noqa: E402


EXPERIMENT_ID = "sol_15d_touch_trailing_grid_0_2_v1"
DATA_DIR = ROOT / "data" / EXPERIMENT_ID
RESULT_DIR = ROOT / "results" / EXPERIMENT_ID
CONFIG_PATH = ROOT / "config/experiments" / f"{EXPERIMENT_ID}.json"
RAW_PATH = PROJECT / "stage1_research/data/raw/SOLUSDT/SOLUSDT_1m.parquet"
SIGNAL_PATH = PROJECT / "stage1_research/data/processed/SOLUSDT/SOLUSDT_3m_with_averages.parquet"
ACTIVATIONS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
GIVEBACKS = [10.0, 15.0, 20.0, 25.0, 30.0]
FEE_BPS = 10.0
SLIPPAGE_BPS = 2.0
INITIAL_EQUITY = 100.0
STOP_PCT = 4.0
MAX_HOLD = 1_440


def simulate_all(fills: pd.DataFrame, raw: pd.DataFrame,
                 activation_pct: float, giveback_pct: float) -> pd.DataFrame:
    times = pd.DatetimeIndex(raw.open_time)
    opened = raw.open.to_numpy(float)
    high = raw.high.to_numpy(float)
    low = raw.low.to_numpy(float)
    close = raw.close.to_numpy(float)
    rows = []

    for entry in fills.itertuples(index=False):
        start = int(times.searchsorted(entry.entry_timestamp))
        if start >= len(raw) or times[start] != entry.entry_timestamp:
            raise ValueError(f"Missing entry minute {entry.entry_timestamp}")
        entry_fill = float(entry.fill_price)
        activation = entry_fill * (1 + activation_pct / 100)
        hard_stop = entry_fill * (1 - STOP_PCT / 100)
        giveback = giveback_pct / 100
        active = False
        peak = entry_fill
        final = min(start + MAX_HOLD, len(raw))
        completed = None

        for index in range(start, final):
            duration = index - start + 1
            activation_hit = high[index] >= activation
            stop_hit = low[index] <= hard_stop
            if not active:
                if stop_hit:
                    completed = (
                        min(hard_stop, opened[index]),
                        "ambiguous_stop" if activation_hit else "protective_stop",
                        active or activation_hit,
                        peak,
                    )
                    break
                if activation_hit:
                    active = True
                    peak = max(entry_fill, high[index])
            else:
                trail = entry_fill + (peak - entry_fill) * (1 - giveback)
                if low[index] <= trail:
                    completed = (min(trail, opened[index]), "trailing_stop", True, peak)
                    break
                peak = max(peak, high[index])

            if duration >= MAX_HOLD:
                completed = (close[index], "time", active, peak)
                break

        if completed is None:
            continue
        raw_exit, exit_type, activated, peak_price = completed
        exit_fill = raw_exit * (1 - SLIPPAGE_BPS / 10_000)
        rows.append({
            "signal_id": entry.signal_id,
            "strategy": f"a{activation_pct:g}_g{giveback_pct:g}",
            "start_timestamp": entry.start_timestamp,
            "entry_timestamp": entry.entry_timestamp,
            "exit_timestamp": times[index] + pd.Timedelta(minutes=1),
            "exit_candle_open_time": times[index],
            "raw_entry_open": float(entry.raw_open),
            "entry_fill": entry_fill,
            "raw_exit_price": raw_exit,
            "exit_fill": exit_fill,
            "return_after_slippage_pct": (exit_fill / entry_fill - 1) * 100,
            "duration_minutes": duration,
            "exit_type": exit_type,
            "trailing_activated": activated,
            "peak_price": peak_price if activated else np.nan,
        })
    return pd.DataFrame(rows)


def full_equity_path(costed: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    equity = INITIAL_EQUITY
    peak_equity = equity
    max_closed_drawdown = 0.0
    records = []
    for trade in costed.itertuples(index=False):
        allocation = equity
        quantity = allocation / float(trade.entry_cash_out_per_unit)
        exit_cash = quantity * float(trade.exit_cash_in_per_unit)
        pnl = exit_cash - allocation
        entry_fee = quantity * float(trade.entry_fee_per_unit)
        exit_fee = quantity * float(trade.exit_fee_per_unit)
        slippage = quantity * float(trade.total_slippage_per_unit)
        records.append({
            **trade._asdict(),
            "equity_at_entry_usd": equity,
            "allocation_usd": allocation,
            "allocation_pct_of_entry_equity": 100.0,
            "quantity": quantity,
            "entry_fee_usd": entry_fee,
            "exit_fee_usd": exit_fee,
            "exit_cash_usd": exit_cash,
            "realized_pnl_usd": pnl,
            "slippage_usd": slippage,
        })
        equity = exit_cash
        peak_equity = max(peak_equity, equity)
        max_closed_drawdown = min(max_closed_drawdown, (equity / peak_equity - 1) * 100)
    ledger = pd.DataFrame(records)
    return ledger, {
        "ending_equity_usd": equity,
        "total_return_pct": (equity / INITIAL_EQUITY - 1) * 100,
        "max_closed_equity_drawdown_pct": max_closed_drawdown,
    }


def summarize(ledger: pd.DataFrame, ignored: int, activation: float,
              giveback: float, equity_metrics: dict) -> dict:
    returns = ledger.net_return_pct.astype(float)
    pnl = ledger.realized_pnl_usd.astype(float)
    winners = pnl > 0
    losers = pnl < 0
    exits = ledger.exit_type.value_counts()
    return {
        "activation_pct": activation,
        "giveback_pct_of_open_profit": giveback,
        "completed_trades": len(ledger),
        "ignored_signals_while_open": ignored,
        "wins_after_costs": int(winners.sum()),
        "losses_after_costs": int(losers.sum()),
        "win_rate_after_costs_pct": float(winners.mean() * 100),
        "loss_rate_after_costs_pct": float(losers.mean() * 100),
        "trailing_activations": int(ledger.trailing_activated.sum()),
        "trailing_exits": int(exits.get("trailing_stop", 0)),
        "protective_and_ambiguous_stops": int(exits.get("protective_stop", 0) + exits.get("ambiguous_stop", 0)),
        "time_exits": int(exits.get("time", 0)),
        "mean_net_trade_return_pct": float(returns.mean()),
        "median_net_trade_return_pct": float(returns.median()),
        "mean_duration_minutes": float(ledger.duration_minutes.mean()),
        "median_duration_minutes": float(ledger.duration_minutes.median()),
        "fees_usd": float((ledger.entry_fee_usd + ledger.exit_fee_usd).sum()),
        "slippage_usd": float(ledger.slippage_usd.sum()),
        "profit_factor_on_dollars": float(
            pnl[winners].sum() / abs(pnl[losers].sum()) if losers.any() else np.inf
        ),
        **equity_metrics,
    }


def main() -> None:
    raw = pd.read_parquet(RAW_PATH, columns=["open_time", "open", "high", "low", "close"])
    signal = pd.read_parquet(SIGNAL_PATH, columns=[
        "open_time", "open", "high", "low", "close",
        "average_7d", "average_15d", "average_30d",
    ])
    fills, entry_diagnostics = generate_fills(signal, SLIPPAGE_BPS)
    leaderboard = []
    ledgers: dict[tuple[float, float], pd.DataFrame] = {}

    for activation in ACTIVATIONS:
        for giveback in GIVEBACKS:
            outcomes = simulate_all(fills, raw, activation, giveback)
            selected, ignored = select_while_flat(outcomes)
            costed = apply_costs(selected, FEE_BPS)
            ledger, equity_metrics = full_equity_path(costed)
            ledgers[(activation, giveback)] = ledger
            leaderboard.append(summarize(
                ledger, ignored, activation, giveback, equity_metrics
            ))

    table = pd.DataFrame(leaderboard).sort_values(
        ["ending_equity_usd", "max_closed_equity_drawdown_pct"],
        ascending=[False, False],
    ).reset_index(drop=True)
    table.insert(0, "rank", np.arange(1, len(table) + 1))
    winner = table.iloc[0].to_dict()
    best_key = (float(winner["activation_pct"]), float(winner["giveback_pct_of_open_profit"]))
    best_ledger = ledgers[best_key]

    # Reuse the production account component to obtain minute-marked drawdown for the winner.
    checked_lots = select_spot_lots(best_ledger, raw, INITIAL_EQUITY, 1.0, 1)
    if len(checked_lots) != len(best_ledger):
        raise AssertionError("Winner contains overlapping trades")
    curve = build_account_curve(raw, checked_lots, INITIAL_EQUITY)
    winner["max_mark_to_market_drawdown_pct"] = float(curve.drawdown_pct.min())
    winner["lowest_marked_equity_usd"] = float(curve.total_equity_usd.min())
    winner["data_start_utc"] = str(curve.timestamp.iloc[0])
    winner["data_end_utc"] = str(curve.timestamp.iloc[-1])
    winner["entry_diagnostics"] = entry_diagnostics
    split_at = pd.Timestamp("2025-09-01", tz="UTC")
    winner["period_split_utc"] = str(split_at)
    for label, segment in {
        "earlier_period": best_ledger.loc[best_ledger.entry_timestamp < split_at],
        "later_period": best_ledger.loc[best_ledger.entry_timestamp >= split_at],
    }.items():
        multiples = 1 + segment.net_return_pct.to_numpy(float) / 100
        winner[label] = {
            "trades": len(segment),
            "wins": int((segment.net_return_pct > 0).sum()),
            "losses": int((segment.net_return_pct < 0).sum()),
            "win_rate_pct": float((segment.net_return_pct > 0).mean() * 100),
            "independent_compounded_return_pct": float((np.prod(multiples) - 1) * 100),
        }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(RESULT_DIR / "leaderboard.csv", index=False)
    best_ledger.to_csv(DATA_DIR / "best_trade_ledger.csv", index=False)
    best_ledger.to_parquet(DATA_DIR / "best_trade_ledger.parquet", index=False)
    curve.to_parquet(DATA_DIR / "best_account_curve_1m.parquet", index=False)
    (RESULT_DIR / "best_result.json").write_text(json.dumps(winner, indent=2) + "\n")

    config = {
        "experiment_id": EXPERIMENT_ID,
        "status": "historical_grid_not_deployed",
        "entry": {
            "signal_timeframe": "3m",
            "average": "15d completed-daily-close SMA",
            "touch_zone_pct": 0.2,
            "approach": "from_below",
            "confirmation": "bullish candle within 30 minutes",
            "market_filter": "reject 7d < 15d < 30d",
        },
        "grid": {
            "activation_pct_from_entry_fill": ACTIVATIONS,
            "giveback_pct_of_open_profit": GIVEBACKS,
            "combinations": len(ACTIVATIONS) * len(GIVEBACKS),
        },
        "exit": {"protective_stop_pct": STOP_PCT, "maximum_hold_minutes": MAX_HOLD},
        "portfolio": {"initial_equity_usd": INITIAL_EQUITY, "positions": 1, "allocation_pct": 100},
        "costs": {"fee_bps_per_side": FEE_BPS, "slippage_bps_per_side": SLIPPAGE_BPS},
        "selection": "highest ending equity on the complete in-sample history",
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")

    top = table.head(10)
    top_lines = [
        "| Rank | Activate | Giveback | Trades | Win rate | Final $100 | Return | Closed DD |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in top.itertuples(index=False):
        top_lines.append(
            f"| {row.rank} | +{row.activation_pct:g}% | {row.giveback_pct_of_open_profit:g}% | "
            f"{row.completed_trades} | {row.win_rate_after_costs_pct:.2f}% | "
            f"${row.ending_equity_usd:.2f} | {row.total_return_pct:+.2f}% | "
            f"{row.max_closed_equity_drawdown_pct:.2f}% |"
        )
    report = f"""# SOL ±0.2% Touch — Trailing Grid

## Scope

This causal historical grid keeps the modified ±0.2% from-below entry, existing confirmation and market filter, −4% emergency stop, and 24-hour cap. It tests all 45 requested combinations of +1% through +5% activation in 0.5-point steps and 10% through 30% open-profit giveback. One position uses 100% of current equity. Results include 10 bps fees and 2 bps adverse slippage on each side.

## Best in-sample combination

- Activation: **+{winner['activation_pct']:g}%**
- Open-profit giveback: **{winner['giveback_pct_of_open_profit']:g}%**
- Final $100 account: **${winner['ending_equity_usd']:.2f}** ({winner['total_return_pct']:+.2f}%)
- Trades: **{winner['completed_trades']}**
- Wins / losses: **{winner['wins_after_costs']} / {winner['losses_after_costs']}**
- Win rate: **{winner['win_rate_after_costs_pct']:.2f}%**
- Trailing activations / exits: **{winner['trailing_activations']} / {winner['trailing_exits']}**
- Protective or ambiguous stops: **{winner['protective_and_ambiguous_stops']}**
- Time exits: **{winner['time_exits']}**
- Maximum minute-marked drawdown: **{winner['max_mark_to_market_drawdown_pct']:.2f}%**
- Fees / slippage: **${winner['fees_usd']:.2f} / ${winner['slippage_usd']:.2f}**
- Profit factor: **{winner['profit_factor_on_dollars']:.3f}**
- Earlier-period independent return: **{winner['earlier_period']['independent_compounded_return_pct']:+.2f}%** on **{winner['earlier_period']['trades']}** trades
- Later-period independent return: **{winner['later_period']['independent_compounded_return_pct']:+.2f}%** on **{winner['later_period']['trades']}** trades

## Top ten

{chr(10).join(top_lines)}

## Selection limit

The winner is selected on the same history used to compare the grid, so it is an in-sample research candidate. It should not replace the frozen forward strategy until it passes a chronological holdout or forward paper test.
"""
    (RESULT_DIR / "REPORT.md").write_text(report)
    print(json.dumps(winner, indent=2))
    print("\nTOP 10\n" + top.to_string(index=False))


if __name__ == "__main__":
    main()
