"""Replay the SOL 0.2% touch / immediate 15% profit-giveback experiment."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT))

from src.backtesting.account import build_account_curve, select_spot_lots  # noqa: E402
from src.backtesting.costs import apply_costs  # noqa: E402
from src.backtesting.entries import SignalCandle, SignalSpec, TouchSignalGenerator  # noqa: E402


CONFIG_PATH = ROOT / "config/experiments/sol_15d_touch_immediate_trail_v1.json"
OUTPUT = ROOT / "results/sol_15d_touch_immediate_trail_v1"
DATA = ROOT / "data/sol_15d_touch_immediate_trail_v1"
RAW_PATH = PROJECT / "stage1_research/data/raw/SOLUSDT/SOLUSDT_1m.parquet"
SIGNAL_PATH = PROJECT / "stage1_research/data/processed/SOLUSDT/SOLUSDT_3m_with_averages.parquet"


def generate_fills(signal: pd.DataFrame, slippage_bps: float) -> tuple[pd.DataFrame, dict]:
    spec = SignalSpec(
        name="sol_immediate_trail",
        timeframe="3min",
        touch_zone_pct=0.2,
        maximum_wait_minutes=30,
        avoid_strong_bearish=True,
    )
    generator = TouchSignalGenerator(spec)
    confirmed = []
    for row in signal.itertuples(index=False):
        candidate = generator.process(SignalCandle(
            open_time=row.open_time,
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            average_7d=float(row.average_7d),
            average_15d=float(row.average_15d),
            average_30d=float(row.average_30d),
        ))
        if candidate is not None and candidate.status == "confirmed":
            confirmed.append(candidate)
    generator.finalize()

    raw_opens = pd.read_parquet(RAW_PATH, columns=["open_time", "open"]).set_index("open_time").open
    rows = []
    for item in confirmed:
        raw_open = float(raw_opens.at[item.entry_timestamp])
        rows.append({
            "signal_id": item.signal_id,
            "strategy": item.strategy,
            "start_timestamp": item.start_timestamp,
            "entry_timestamp": item.entry_timestamp,
            "raw_open": raw_open,
            "fill_price": raw_open * (1 + slippage_bps / 10_000),
        })
    diagnostics = {
        "touch_episodes": generator.episodes_seen,
        "from_below_episodes": generator.from_below_episodes,
        "market_rejections": generator.market_rejections,
        "eligible_candidates": len(generator.candidates),
        "confirmed_signals": len(confirmed),
        "unconfirmed_candidates": len(generator.candidates) - len(confirmed),
    }
    return pd.DataFrame(rows), diagnostics


def simulate_outcome(entry: pd.Series, raw: pd.DataFrame, config: dict) -> dict | None:
    times = pd.DatetimeIndex(raw.open_time)
    start = int(times.searchsorted(entry.entry_timestamp))
    if start >= len(raw) or times[start] != entry.entry_timestamp:
        raise ValueError(f"Missing entry minute {entry.entry_timestamp}")

    exit_cfg = config["exit"]
    slippage_bps = float(config["costs"]["slippage_bps_per_side"])
    entry_fill = float(entry.fill_price)
    hard_stop = entry_fill * (1 - float(exit_cfg["protective_stop_pct"]) / 100)
    giveback = float(exit_cfg["trailing_giveback_of_open_profit_pct"]) / 100
    maximum_hold = int(exit_cfg["maximum_hold_minutes"])
    end = min(start + maximum_hold, len(raw))
    active = False
    peak = entry_fill

    for offset in range(start, end):
        candle = raw.iloc[offset]
        duration = offset - start + 1
        stop_hit = float(candle.low) <= hard_stop
        activation_hit = float(candle.high) > entry_fill
        if stop_hit:
            raw_exit = min(hard_stop, float(candle.open))
            exit_type = "ambiguous_stop" if (not active and activation_hit) else "protective_stop"
            break

        if active:
            trail = entry_fill + (peak - entry_fill) * (1 - giveback)
            if float(candle.low) <= trail:
                raw_exit = min(trail, float(candle.open))
                exit_type = "trailing_stop"
                break
            peak = max(peak, float(candle.high))
        elif activation_hit:
            active = True
            peak = float(candle.high)

        if duration >= maximum_hold:
            raw_exit = float(candle.close)
            exit_type = "time"
            break
    else:
        return None

    exit_fill = raw_exit * (1 - slippage_bps / 10_000)
    return {
        "signal_id": entry.signal_id,
        "strategy": entry.strategy,
        "start_timestamp": entry.start_timestamp,
        "entry_timestamp": entry.entry_timestamp,
        "exit_timestamp": pd.Timestamp(raw.iloc[offset].open_time) + pd.Timedelta(minutes=1),
        "exit_candle_open_time": raw.iloc[offset].open_time,
        "raw_entry_open": float(entry.raw_open),
        "entry_fill": entry_fill,
        "raw_exit_price": raw_exit,
        "exit_fill": exit_fill,
        "return_after_slippage_pct": (exit_fill / entry_fill - 1) * 100,
        "duration_minutes": duration,
        "exit_type": exit_type,
        "trailing_activated": active or activation_hit,
        "peak_price": peak if (active or activation_hit) else np.nan,
    }


def select_while_flat(outcomes: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    selected = []
    available_at = None
    for row in outcomes.sort_values(["entry_timestamp", "signal_id"]).itertuples(index=False):
        if available_at is None or row.entry_timestamp >= available_at:
            selected.append(row._asdict())
            available_at = row.exit_timestamp
    return pd.DataFrame(selected), len(outcomes) - len(selected)


def summarize(trades: pd.DataFrame, curve: pd.DataFrame, diagnostics: dict,
              ignored: int, config: dict) -> dict:
    pnl = trades.realized_pnl_usd.astype(float)
    returns = trades.net_return_pct.astype(float)
    gross_pnl = trades.quantity * (trades.raw_exit_price - trades.raw_entry_open)
    slippage_usd = trades.quantity * trades.total_slippage_per_unit
    exit_counts = trades.exit_type.value_counts()
    monthly_span = (
        (pd.Timestamp(curve.timestamp.iloc[-1]) - pd.Timestamp(curve.timestamp.iloc[0])).total_seconds()
        / (365.2425 / 12 * 86400)
    )
    wins = pnl > 0
    losses = pnl < 0
    gross_returns = trades.gross_raw_return_pct.astype(float)
    return {
        "data_start_utc": str(curve.timestamp.iloc[0]),
        "data_end_utc": str(curve.timestamp.iloc[-1]),
        "approximate_months": monthly_span,
        **diagnostics,
        "ignored_signals_while_position_open": ignored,
        "completed_trades": len(trades),
        "wins_after_costs": int(wins.sum()),
        "losses_after_costs": int(losses.sum()),
        "breakeven_after_costs": int((pnl == 0).sum()),
        "win_rate_after_costs_pct": float(wins.mean() * 100),
        "loss_rate_after_costs_pct": float(losses.mean() * 100),
        "gross_winning_trades_before_costs": int((gross_returns > 0).sum()),
        "gross_losing_trades_before_costs": int((gross_returns < 0).sum()),
        "gross_breakeven_trades_before_costs": int((gross_returns == 0).sum()),
        "gross_win_rate_before_costs_pct": float((gross_returns > 0).mean() * 100),
        "hypothetical_ending_equity_without_fees_or_slippage_usd": float(
            config["portfolio"]["initial_equity_usd"]
            * np.prod(1 + gross_returns.to_numpy() / 100)
        ),
        "trades_per_month": float(len(trades) / monthly_span),
        "trailing_activations": int(trades.trailing_activated.sum()),
        "trailing_stop_exits": int(exit_counts.get("trailing_stop", 0)),
        "protective_stop_exits": int(exit_counts.get("protective_stop", 0)),
        "ambiguous_stop_exits": int(exit_counts.get("ambiguous_stop", 0)),
        "time_exits": int(exit_counts.get("time", 0)),
        "starting_equity_usd": float(config["portfolio"]["initial_equity_usd"]),
        "ending_equity_usd": float(curve.total_equity_usd.iloc[-1]),
        "net_profit_usd": float(curve.total_equity_usd.iloc[-1] - config["portfolio"]["initial_equity_usd"]),
        "total_return_pct": float((curve.total_equity_usd.iloc[-1] / config["portfolio"]["initial_equity_usd"] - 1) * 100),
        "gross_price_pnl_usd": float(gross_pnl.sum()),
        "fees_usd": float((trades.entry_fee_usd + trades.exit_fee_usd).sum()),
        "slippage_usd": float(slippage_usd.sum()),
        "max_mark_to_market_drawdown_pct": float(curve.drawdown_pct.min()),
        "lowest_equity_usd": float(curve.total_equity_usd.min()),
        "mean_net_trade_return_pct": float(returns.mean()),
        "median_net_trade_return_pct": float(returns.median()),
        "best_trade_return_pct": float(returns.max()),
        "worst_trade_return_pct": float(returns.min()),
        "mean_duration_minutes": float(trades.duration_minutes.mean()),
        "median_duration_minutes": float(trades.duration_minutes.median()),
        "profit_factor_on_dollars": float(pnl[wins].sum() / abs(pnl[losses].sum())),
    }


def main() -> None:
    config = json.loads(CONFIG_PATH.read_text())
    raw = pd.read_parquet(RAW_PATH, columns=["open_time", "open", "high", "low", "close"])
    signal = pd.read_parquet(SIGNAL_PATH, columns=[
        "open_time", "open", "high", "low", "close",
        "average_7d", "average_15d", "average_30d",
    ])
    fills, diagnostics = generate_fills(signal, float(config["costs"]["slippage_bps_per_side"]))
    outcomes = [simulate_outcome(row, raw, config) for _, row in fills.iterrows()]
    complete = pd.DataFrame(item for item in outcomes if item is not None)
    selected, ignored = select_while_flat(complete)
    costed = apply_costs(selected, float(config["costs"]["fee_bps_per_side"]))
    lots = select_spot_lots(
        costed,
        raw,
        initial_equity_usd=float(config["portfolio"]["initial_equity_usd"]),
        equity_fraction_per_entry=1.0,
        maximum_positions=1,
    )
    if len(lots) != len(costed):
        raise AssertionError("The already non-overlapping trade list changed during account sizing")
    curve = build_account_curve(raw, lots, float(config["portfolio"]["initial_equity_usd"]))
    summary = summarize(lots, curve, diagnostics, ignored, config)

    DATA.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fills.to_parquet(DATA / "entry_fills.parquet", index=False)
    complete.to_parquet(DATA / "all_signal_outcomes.parquet", index=False)
    lots.to_parquet(DATA / "trade_ledger.parquet", index=False)
    lots.to_csv(DATA / "trade_ledger.csv", index=False)
    curve.to_parquet(DATA / "account_curve_1m.parquet", index=False)
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    report = f"""# SOL 15-day Touch with Immediate 15% Profit Trail

## Rules tested

This is a historical experiment and does not change the deployed frozen strategy. It uses completed 3-minute candles, a ±0.2% touch zone approached from below, the existing bullish-candle confirmation within 30 minutes, and the existing strong-bearish regime rejection. Entry uses the raw one-minute open at the confirmation boundary with 2 bps adverse slippage.

Only one long spot position may be open. Each entry allocates 100% of current equity. A −4% emergency stop and 24-hour maximum hold remain. Trailing activates when a post-entry candle first trades strictly above the slipped entry price. Starting with the following candle, the stop retains 85% of the highest open profit known before that candle. Fees are 10 bps per side.

## Result

- Starting equity: **${summary['starting_equity_usd']:.2f}**
- Ending equity: **${summary['ending_equity_usd']:.2f}**
- Net return: **{summary['total_return_pct']:+.2f}%**
- Completed trades: **{summary['completed_trades']}** ({summary['trades_per_month']:.2f} per month)
- Wins / losses: **{summary['wins_after_costs']} / {summary['losses_after_costs']}**
- Net win rate: **{summary['win_rate_after_costs_pct']:.2f}%**
- Gross win rate before fees and slippage: **{summary['gross_win_rate_before_costs_pct']:.2f}%**
- Hypothetical ending equity without either cost: **${summary['hypothetical_ending_equity_without_fees_or_slippage_usd']:.2f}**
- Trailing activations / trailing exits: **{summary['trailing_activations']} / {summary['trailing_stop_exits']}**
- Protective and ambiguous stops: **{summary['protective_stop_exits'] + summary['ambiguous_stop_exits']}**
- Time exits: **{summary['time_exits']}**
- Maximum minute-marked drawdown: **{summary['max_mark_to_market_drawdown_pct']:.2f}%**
- Fees / slippage: **${summary['fees_usd']:.2f} / ${summary['slippage_usd']:.2f}**
- Profit factor: **{summary['profit_factor_on_dollars']:.3f}**

## Interpretation

The win rate is measured after fees and slippage. Because the trail begins after any positive movement and keeps 85% of open profit, many grossly positive exits can still be net losses after the 24 bps modeled round-trip friction. The minute account curve supplies the drawdown and final marked-equity figures.
"""
    (OUTPUT / "REPORT.md").write_text(report)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
