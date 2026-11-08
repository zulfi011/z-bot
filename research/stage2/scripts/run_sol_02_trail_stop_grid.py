"""SOL ±0.2% 15-day touch from below, one 100%-equity position, trailing exits,
optional protective stop, no time exit — every combination, on Stage 3 rules.

Signals and exit paths come from the verified fast grid functions; the best
rows plus the live strategy and the 1x50% candidate are then re-run on the exact
Stage 3 replay over identical windows.
"""

from __future__ import annotations

import copy
import json
import sys
import time

import numpy as np
import pandas as pd

import run_sol_stage3_space_grid as grid
import stage3_replay as replay

EXPERIMENT_ID = "sol_02_trail_stop_grid_v1"
RESULT_DIR = grid.ROOT / "results" / EXPERIMENT_ID
LIVE_CSV = replay.HOLDOUT_DIR / "SOLUSDT_live_db_1m.csv"
PROPOSED = grid.ROOT / "config/experiments/sol_15d_touch_v2_single_lot_PROPOSED.json"

ENTRY = {"signal_minutes": 3, "average_days": 15, "zone_pct": 0.2,
         "approach": "from_below", "market_filter": "avoid_strong_bearish"}
ACTIVATIONS = [0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]          # 0 = immediate
GIVEBACKS = [10.0, 15.0, 20.0]
NO_STOP = 100.0                                                   # stop price 0: never hit
STOPS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, NO_STOP]
NO_LIMIT_MINUTES = 10**9
UTC = "UTC"


def load_all() -> pd.DataFrame:
    raw = replay.load_raw(grid.SYMBOL, include_holdout=True)
    if LIVE_CSV.exists():
        live = pd.read_csv(LIVE_CSV)
        live["open_time"] = pd.to_datetime(live.open_time, utc=True)
        overlap = raw.merge(live, on="open_time", suffixes=("", "_live"))
        for column in ["open", "high", "low", "close"]:
            if (overlap[column] - overlap[f"{column}_live"].astype(float)).abs().max() > 1e-9:
                raise ValueError("Live database candles disagree with Binance archives")
        newer = live[live.open_time > raw.open_time.max()]
        raw = pd.concat([raw, newer[["open_time", "open", "high", "low", "close"]].astype(
            {c: float for c in ["open", "high", "low", "close"]})]).reset_index(drop=True)
    if not (raw.open_time.diff().iloc[1:] == pd.Timedelta(minutes=1)).all():
        raise ValueError("SOL data is not continuous")
    return raw


def periods(raw: pd.DataFrame) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    end = raw.open_time.max() + pd.Timedelta(minutes=1)
    return {
        "full": (pd.Timestamp("2024-10-01", tz=UTC), pd.Timestamp("2026-08-01", tz=UTC)),
        "earlier": grid.PERIODS["earlier"],
        "later": grid.PERIODS["later"],
        "unseen": (pd.Timestamp("2026-08-01", tz=UTC), end),
    }


def single_lot(entries: np.ndarray, rows: np.ndarray, column: int) -> dict:
    """One 100%-equity lot; a new signal is taken only after the lot has exited."""
    equity, busy_until = grid.INITIAL, -1
    pnl, reasons, open_lot = [], {1: 0, 2: 0, 3: 0}, 0
    for entry, row in zip(entries, rows):
        if entry <= busy_until:
            continue
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        quantity = equity / (fill * (1 + grid.FEE))
        exit_index = grid.TABLE_IDX[row, column]
        if exit_index < 0:
            open_lot = 1
            equity = quantity * grid.CLOSE[-1]
            break
        cash = quantity * grid.TABLE_RAW[row, column] * (1 - grid.SLIP) * (1 - grid.FEE)
        pnl.append(cash - equity)
        reasons[int(grid.TABLE_CODE[row, column])] += 1
        equity, busy_until = cash, exit_index
    pnl = np.array(pnl)
    losses = -pnl[pnl < 0].sum()
    return {"trades": len(pnl), "wins": int((pnl > 0).sum()), "losses": int((pnl < 0).sum()),
            "final_usd": equity, "return_pct": equity - grid.INITIAL,
            "profit_factor": pnl[pnl > 0].sum() / losses if losses else np.nan,
            "trailing_exits": reasons[1], "stop_exits": reasons[2] + reasons[3],
            "open_at_end": open_lot}


def strategy_for(activation: float, giveback: float, stop: float, lots=1, fraction=1.0,
                 zone=0.2, hold=NO_LIMIT_MINUTES) -> dict:
    strategy = copy.deepcopy(json.loads(replay.STRATEGY_FILES[grid.SYMBOL].read_text()))
    strategy["entry"]["touch_zone_pct"] = zone
    strategy["exit"]["protective_stop_pct_from_entry_fill"] = stop
    strategy["exit"]["trailing_stop"]["activation_pct_from_entry_fill"] = activation
    strategy["exit"]["trailing_stop"]["giveback_of_open_profit_pct"] = giveback
    strategy["exit"]["maximum_hold_minutes"] = hold
    strategy["portfolio"]["maximum_open_positions"] = lots
    strategy["portfolio"]["equity_fraction_per_entry"] = fraction
    return strategy


def label(activation: float, giveback: float, stop: float) -> str:
    start = "immediate" if activation == 0 else f"+{activation:g}%"
    return f"trail {start}, {giveback:g}% giveback, {'no stop' if stop == NO_STOP else f'−{stop:g}% stop'}"


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    raw = load_all()
    windows = periods(raw)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.STOPS, grid.ACTIVATIONS, grid.GIVEBACKS = (np.array(STOPS), np.array(ACTIVATIONS), np.array(GIVEBACKS))
    grid.BASE_PARAMS = [(s, a, g) for s in STOPS for a in ACTIVATIONS for g in GIVEBACKS]

    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals)
             for d, vals in replay.daily_averages(raw).items()}
    signals = grid.fast_signals(grid.signal_frame(raw, daily, 3), ENTRY)
    signals = signals[signals.entry_index < len(raw)].reset_index(drop=True)
    entries = signals.entry_index.to_numpy()
    grid.TABLE_IDX, grid.TABLE_RAW, grid.TABLE_CODE = grid.exit_outcomes(entries)
    times = pd.DatetimeIndex(raw.open_time)
    print(f"{len(signals)} signals, exit paths ready ({time.time() - started:.0f}s)", flush=True)

    rows = []
    for column, (stop, activation, giveback) in enumerate(grid.BASE_PARAMS):
        row = {"activation_pct": activation, "giveback_pct": giveback, "stop_pct": stop,
               "rules": label(activation, giveback, stop)}
        for period, (start, end) in windows.items():
            mask = (signals.touch_time >= start).to_numpy() & (times[entries] < end)
            result = single_lot(entries[mask], np.flatnonzero(mask), column)
            row.update({f"{period}_{k}": v for k, v in result.items()})
        rows.append(row)
    board = pd.DataFrame(rows).sort_values("full_final_usd", ascending=False).reset_index(drop=True)
    board.insert(0, "rank", np.arange(1, len(board) + 1))
    board.to_csv(RESULT_DIR / "all_192_combinations.csv", index=False)

    earlier_pick = board.sort_values("earlier_final_usd", ascending=False).iloc[0]
    finalists = {f"#{int(r['rank'])} full history: {r['rules']}": strategy_for(
        r.activation_pct, r.giveback_pct, r.stop_pct) for _, r in board.head(3).iterrows()}
    finalists[f"best on earlier only: {earlier_pick['rules']}"] = strategy_for(
        earlier_pick.activation_pct, earlier_pick.giveback_pct, earlier_pick.stop_pct)
    finalists["CURRENT live (±0.5%, 2×25%, −4%/+4%/10%, 24h)"] = json.loads(
        replay.STRATEGY_FILES[grid.SYMBOL].read_text())
    finalists["CANDIDATE 1×50% (±0.5%, −4%/+4%/10%, 24h)"] = json.loads(PROPOSED.read_text())

    averages = replay.daily_averages(raw)
    candles = replay.signal_candles(raw, 3, averages)
    signal_cache: dict[float, list] = {}
    exact_rows = []
    for name, strategy in finalists.items():
        zone = strategy["entry"]["touch_zone_pct"]
        if zone not in signal_cache:
            signal_cache[zone], _ = replay.generate_signals(strategy, candles)
        for period, (start, end) in windows.items():
            summary = replay.summarize(replay.replay_execution(strategy, raw, signal_cache[zone], start, end))
            exact_rows.append({"strategy": name, "period": period, **summary})
        print(f"exact: {name} ({time.time() - started:.0f}s)", flush=True)
    exact = pd.DataFrame(exact_rows)
    exact.to_csv(RESULT_DIR / "exact_comparison.csv", index=False)

    pd.set_option("display.width", 250)
    cols = ["rank", "rules", "full_trades", "full_wins", "full_losses", "full_final_usd",
            "earlier_return_pct", "later_return_pct", "unseen_return_pct", "unseen_trades", "full_open_at_end"]
    print(board[cols].head(20).round(2).to_string(index=False))
    print("\nprofitable full:", int((board.full_return_pct > 0).sum()), "/ 192;",
          "positive earlier and later:", int(((board.earlier_return_pct > 0) & (board.later_return_pct > 0)).sum()))
    print(exact.pivot_table(index="strategy", columns="period", sort=False,
                            values=["return_pct", "max_drawdown_pct", "trades", "win_rate_pct"]).round(2).to_string())


if __name__ == "__main__":
    main()
