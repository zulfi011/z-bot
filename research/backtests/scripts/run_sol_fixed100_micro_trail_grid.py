"""SOL fixed-$100 lots with a +0.245% / 10% micro trail, no time exit.

$300 account, up to 3 lots, each lot min($100, free cash). Touch from below of a
7–15 day completed-close average (±0.1…0.5%), bullish confirmation within 30
minutes, live "avoid strong bearish" filter. Stops −0.5/−1/−1.5/−2%.
540 combinations; the best rows are re-run on the exact Stage 3 replay.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal

import numpy as np
import pandas as pd

import run_sol_02_trail_stop_grid as g02
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

EXPERIMENT_ID = "sol_fixed100_micro_trail_grid_v1"
RESULT_DIR = grid.ROOT / "results" / EXPERIMENT_ID
DATA_DIR = grid.ROOT / "data" / EXPERIMENT_ID

TIMEFRAMES = [1, 3, 5]
AVERAGE_DAYS = list(range(7, 16))
ZONES = [0.1, 0.2, 0.3, 0.4, 0.5]
STOPS = [0.5, 1.0, 1.5, 2.0]
ACTIVATION = 0.245
GIVEBACK = 10.0
INITIAL = 300.0
LOT_USD = 100.0
MAX_LOTS = 3
NEVER = np.iinfo(np.int64).max


def lot_allocation(marked: Decimal, cash: Decimal) -> Decimal:
    return min(Decimal("100"), cash)


def simulate(entries: np.ndarray, rows: np.ndarray, column: int) -> dict:
    cash, lots = INITIAL, []          # lot: (exit_index, quantity, cost, exit_unit_cash, kind)
    pnl, kinds = [], {1: 0, 2: 0, 3: 0}
    fees = slippage = 0.0
    skipped = 0
    peak, drawdown = INITIAL, 0.0
    hold_minutes = []

    def close(lot, entry_index=None) -> None:
        nonlocal cash, fees, slippage
        exit_index, quantity, cost, unit, kind, opened = lot
        raw_exit = unit / ((1 - grid.SLIP) * (1 - grid.FEE))
        cash += quantity * unit
        pnl.append(quantity * unit - cost)
        kinds[kind] += 1
        fees += quantity * raw_exit * (1 - grid.SLIP) * grid.FEE
        slippage += quantity * raw_exit * grid.SLIP
        hold_minutes.append(exit_index - opened + 1)

    for entry, row in zip(entries, rows):
        for lot in [lot for lot in lots if lot[0] < entry]:
            close(lot)
        lots = [lot for lot in lots if lot[0] >= entry]
        marked = cash + sum(lot[1] for lot in lots) * grid.OPEN[entry]
        peak = max(peak, marked)
        drawdown = min(drawdown, marked / peak - 1)
        allocation = min(LOT_USD, cash)
        if len(lots) >= MAX_LOTS or allocation <= 1e-8:
            skipped += 1
            continue
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        quantity = allocation / (fill * (1 + grid.FEE))
        fees += quantity * fill * grid.FEE
        slippage += quantity * (fill - grid.OPEN[entry])
        exit_index = grid.TABLE_IDX[row, column]
        unit = grid.TABLE_RAW[row, column] * (1 - grid.SLIP) * (1 - grid.FEE)
        lots.append((NEVER if exit_index < 0 else int(exit_index), quantity, allocation,
                     unit, int(grid.TABLE_CODE[row, column]), int(entry)))
        cash -= allocation
    for lot in [lot for lot in lots if lot[0] < NEVER]:
        close(lot)
    still_open = [lot for lot in lots if lot[0] == NEVER]
    final = cash + sum(lot[1] for lot in still_open) * grid.CLOSE[-1]
    peak = max(peak, final)
    drawdown = min(drawdown, final / peak - 1)
    pnl = np.array(pnl)
    losses = -pnl[pnl < 0].sum()
    return {
        "trades": len(pnl), "wins": int((pnl > 0).sum()), "losses": int((pnl < 0).sum()),
        "win_rate_pct": (pnl > 0).mean() * 100 if len(pnl) else np.nan,
        "final_usd": final, "profit_usd": final - INITIAL, "return_pct": (final / INITIAL - 1) * 100,
        "profit_factor": pnl[pnl > 0].sum() / losses if losses else np.nan,
        "avg_win_usd": pnl[pnl > 0].mean() if (pnl > 0).any() else np.nan,
        "avg_loss_usd": pnl[pnl < 0].mean() if (pnl < 0).any() else np.nan,
        "approx_dd_pct": drawdown * 100, "fees_usd": fees, "slippage_usd": slippage,
        "trailing_exits": kinds[1], "stop_exits": kinds[2] + kinds[3],
        "skipped_signals": skipped, "open_at_end": len(still_open),
        "median_hold_minutes": float(np.median(hold_minutes)) if hold_minutes else np.nan,
    }


def strategy_for(row: dict) -> dict:
    strategy = g02.strategy_for(ACTIVATION, GIVEBACK, float(row["stop_pct"]), lots=MAX_LOTS,
                                fraction=1.0, zone=float(row["zone_pct"]))
    strategy["strategy_id"] = "sol_fixed100_micro_trail"
    strategy["market"]["signal_timeframe"] = f"{int(row['signal_minutes'])}m"
    strategy["averages"]["signal_average_days"] = int(row["average_days"])
    strategy["portfolio"]["initial_paper_equity_usd"] = INITIAL
    strategy["portfolio"]["position_size_method"] = "fixed_usd_capped_at_free_cash"
    strategy["portfolio"]["fixed_allocation_usd"] = LOT_USD
    return strategy


def describe(row: dict) -> str:
    return (f"{int(row['signal_minutes'])}m candles, {int(row['average_days'])}-day average, "
            f"±{row['zone_pct']:g}% zone, stop −{row['stop_pct']:g}%")


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw = g02.load_all()
    windows = g02.periods(raw)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.STOPS, grid.ACTIVATIONS, grid.GIVEBACKS = np.array(STOPS), np.array([ACTIVATION]), np.array([GIVEBACK])
    grid.BASE_PARAMS = [(s, ACTIVATION, GIVEBACK) for s in STOPS]
    times = pd.DatetimeIndex(raw.open_time)

    decimal_daily = replay.daily_averages(raw)
    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals) for d, vals in decimal_daily.items()}
    extra = {n: {d: float(v) if v is not None else np.nan for d, v in replay.daily_average_n(raw, n).items()}
             for n in AVERAGE_DAYS}
    signal_sets = {}
    for minutes in TIMEFRAMES:
        frame = grid.signal_frame(raw, daily, minutes)
        days = frame["open_time"].floor("D")
        for n in AVERAGE_DAYS:
            frame[n] = np.array([extra[n].get(d, np.nan) for d in days]) if n not in (7, 15) else frame[n]
            for zone in ZONES:
                config = {"signal_minutes": minutes, "average_days": n, "zone_pct": zone,
                          "approach": "from_below", "market_filter": "avoid_strong_bearish"}
                signals = grid.fast_signals(frame, config)
                signal_sets[(minutes, n, zone)] = signals[signals.entry_index < len(raw)].reset_index(drop=True)
    unique = np.unique(np.concatenate([s.entry_index.to_numpy() for s in signal_sets.values()]))
    grid.TABLE_IDX, grid.TABLE_RAW, grid.TABLE_CODE = grid.exit_outcomes(unique)
    print(f"{sum(map(len, signal_sets.values())):,} signals, {len(unique):,} entries, exits ready "
          f"({time.time() - started:.0f}s)", flush=True)

    rows = []
    for (minutes, n, zone), signals in signal_sets.items():
        entries = signals.entry_index.to_numpy()
        table_rows = np.searchsorted(unique, entries)
        for column, stop in enumerate(STOPS):
            row = {"signal_minutes": minutes, "average_days": n, "zone_pct": zone, "stop_pct": stop}
            for period, (start, end) in windows.items():
                mask = (signals.touch_time >= start).to_numpy() & (times[entries] < end)
                row.update({f"{period}_{k}": v for k, v in
                            simulate(entries[mask], table_rows[mask], column).items()})
            rows.append(row)
    board = pd.DataFrame(rows).sort_values("full_profit_usd", ascending=False).reset_index(drop=True)
    board.insert(0, "rank", np.arange(1, len(board) + 1))
    board.to_csv(RESULT_DIR / "all_540_combinations.csv", index=False)
    print(f"grid done ({time.time() - started:.0f}s)", flush=True)

    both = board[(board.earlier_profit_usd > 0) & (board.later_profit_usd > 0)]
    finalists = board.head(3).to_dict("records")
    if len(both) and int(both.iloc[0]["rank"]) > 3:
        finalists.append(both.iloc[0].to_dict())
    exact_rows = []
    for row in finalists:
        strategy = strategy_for(row)
        candles = replay.signal_candles(raw, int(row["signal_minutes"]), decimal_daily,
                                        signal_days=int(row["average_days"]))
        signals, _ = replay.generate_signals(strategy, candles)
        fast_count = len(signal_sets[(row["signal_minutes"], row["average_days"], row["zone_pct"])])
        for period, (start, end) in windows.items():
            result = replay.replay_execution(strategy, raw, signals, start, end, allocate=lot_allocation)
            summary = replay.summarize(result, initial=INITIAL)
            exact_rows.append({"rank": int(row["rank"]), "rules": describe(row), "period": period,
                               "exact_signals": len(signals), "fast_signals": fast_count, **summary})
            if period == "full":
                result.trades.to_csv(DATA_DIR / f"rank{int(row['rank'])}_full_trades.csv", index=False)
        print(f"exact: #{int(row['rank'])} {describe(row)} ({time.time() - started:.0f}s)", flush=True)
    exact = pd.DataFrame(exact_rows)
    exact.to_csv(RESULT_DIR / "exact_finalists.csv", index=False)
    (RESULT_DIR / "best_candidate_strategy.json").write_text(json.dumps(strategy_for(board.iloc[0]), indent=2) + "\n")

    pd.set_option("display.width", 250)
    cols = ["rank", "signal_minutes", "average_days", "zone_pct", "stop_pct", "full_trades", "full_win_rate_pct",
            "full_profit_usd", "earlier_profit_usd", "later_profit_usd", "unseen_profit_usd", "full_approx_dd_pct",
            "full_fees_usd", "full_median_hold_minutes"]
    print(board[cols].head(15).round(2).to_string(index=False))
    print("\nprofitable full:", int((board.full_profit_usd > 0).sum()), "/", len(board),
          "| positive earlier and later:", len(both))
    print(exact.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
