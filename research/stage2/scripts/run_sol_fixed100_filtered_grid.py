"""Fixed-$100 SOL grid with the two surviving filters as an extra dimension.

Filters: none / close above 30-day average / skip entries 06–12 UTC / both.
Trail start per giveback = break-even (+0.245% at 10% … +0.315% at 30%), or
break-even + 1% with `--plus1`. Other rules as run_sol_fixed100_giveback_grid:
$300, up to 3 lots of min($100, free cash), 1/3/5m candles, 7–15 day average,
±0.1…0.5% zone, stops −0.5…−2%, no time exit. 23,760 combinations.
"""

from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

import run_sol_02_trail_stop_grid as g02
import run_sol_fixed100_giveback_grid as gb
import run_sol_fixed100_micro_trail_grid as micro
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

PLUS_ONE = "--plus1" in sys.argv
EXPERIMENT_ID = "sol_fixed100_filtered_plus1_grid_v1" if PLUS_ONE else "sol_fixed100_filtered_grid_v1"
RESULT_DIR = grid.ROOT / "results" / EXPERIMENT_ID
GIVEBACKS = [float(g) for g in range(10, 31, 2)]
EXIT_SETS = [(round(gb.break_even_activation(g) + (1.0 if PLUS_ONE else 0.0), 3), g) for g in GIVEBACKS]
ACTIVATIONS = sorted({a for a, _ in EXIT_SETS})
FILTERS = {"none": (False, False), "above_30d": (True, False), "skip_06_12": (False, True), "both": (True, True)}


def column_for(stop_index: int, activation: float, giveback: float) -> int:
    return ((stop_index * len(ACTIVATIONS) + ACTIVATIONS.index(activation)) * len(GIVEBACKS)
            + GIVEBACKS.index(giveback))


def filter_masks(signals: pd.DataFrame, minutes: int, daily: dict, times: pd.DatetimeIndex) -> tuple:
    entry = signals.entry_index.to_numpy()
    confirm_day = times[entry - minutes].floor("D")
    a30 = np.array([daily.get(d, (np.nan,) * 3)[2] for d in confirm_day])
    above = grid.CLOSE[entry - 1] > a30                       # confirmation candle close
    hour = times[entry].hour
    morning = (hour >= 6) & (hour < 12)
    return above, morning


def describe(row: dict) -> str:
    return (f"{int(row['signal_minutes'])}m candles, {int(row['average_days'])}-day average, "
            f"±{row['zone_pct']:g}% zone, stop −{row['stop_pct']:g}%, trail from +{row['activation_pct']:g}% "
            f"with {row['giveback_pct']:g}% giveback, filter {row['filter']}")


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    raw = g02.load_all()
    windows = g02.periods(raw)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.STOPS, grid.ACTIVATIONS, grid.GIVEBACKS = np.array(micro.STOPS), np.array(ACTIVATIONS), np.array(GIVEBACKS)
    grid.BASE_PARAMS = [(s, a, g) for s in micro.STOPS for a in ACTIVATIONS for g in GIVEBACKS]
    times = pd.DatetimeIndex(raw.open_time)

    decimal_daily = replay.daily_averages(raw)
    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals) for d, vals in decimal_daily.items()}
    extra = {n: {d: float(v) if v is not None else np.nan for d, v in replay.daily_average_n(raw, n).items()}
             for n in micro.AVERAGE_DAYS}
    sets = {}
    for minutes in micro.TIMEFRAMES:
        frame = grid.signal_frame(raw, daily, minutes)
        days = frame["open_time"].floor("D")
        for n in micro.AVERAGE_DAYS:
            if n not in (7, 15):
                frame[n] = np.array([extra[n].get(d, np.nan) for d in days])
            for zone in micro.ZONES:
                signals = grid.fast_signals(frame, {"signal_minutes": minutes, "average_days": n, "zone_pct": zone,
                                                    "approach": "from_below", "market_filter": "avoid_strong_bearish"})
                signals = signals[signals.entry_index < len(raw)].reset_index(drop=True)
                sets[(minutes, n, zone)] = (signals, filter_masks(signals, minutes, daily, times))
    unique = np.unique(np.concatenate([s.entry_index.to_numpy() for s, _ in sets.values()]))
    grid.TABLE_IDX, grid.TABLE_RAW, grid.TABLE_CODE = grid.exit_outcomes(unique)
    print(f"{EXPERIMENT_ID}: {len(unique):,} entries, exits ready ({time.time() - started:.0f}s)", flush=True)

    rows = []
    for (minutes, n, zone), (signals, (above, morning)) in sets.items():
        entries = signals.entry_index.to_numpy()
        table_rows = np.searchsorted(unique, entries)
        windows_mask = {p: (signals.touch_time >= s).to_numpy() & (times[entries] < e) for p, (s, e) in windows.items()}
        for name, (need_above, skip) in FILTERS.items():
            keep = (above if need_above else True) & ~(morning & skip)
            for stop_index, stop in enumerate(micro.STOPS):
                for activation, giveback in EXIT_SETS:
                    row = {"signal_minutes": minutes, "average_days": n, "zone_pct": zone, "stop_pct": stop,
                           "activation_pct": activation, "giveback_pct": giveback, "filter": name}
                    column = column_for(stop_index, activation, giveback)
                    for period, mask in windows_mask.items():
                        m = mask & keep
                        row.update({f"{period}_{k}": v for k, v in
                                    micro.simulate(entries[m], table_rows[m], column).items()})
                    rows.append(row)
    board = pd.DataFrame(rows).sort_values("full_profit_usd", ascending=False).reset_index(drop=True)
    board.insert(0, "rank", np.arange(1, len(board) + 1))
    board.to_csv(RESULT_DIR / f"all_{len(board)}_combinations.csv", index=False)
    print(f"grid done: {len(board):,} ({time.time() - started:.0f}s)", flush=True)

    both = board[(board.earlier_profit_usd > 0) & (board.later_profit_usd > 0)]
    finalists = board.head(3).to_dict("records")
    for _, row in both.head(1).iterrows():
        if int(row["rank"]) > 3:
            finalists.append(row.to_dict())
    exact_rows, candle_cache, signal_cache = [], {}, {}
    for row in finalists:
        minutes, n, zone = int(row["signal_minutes"]), int(row["average_days"]), row["zone_pct"]
        strategy = gb.strategy_for(row)
        strategy["exit"]["trailing_stop"]["activation_pct_from_entry_fill"] = float(row["activation_pct"])
        if (minutes, n) not in candle_cache:
            candle_cache[(minutes, n)] = replay.signal_candles(raw, minutes, decimal_daily, signal_days=n)
        if (minutes, n, zone) not in signal_cache:
            signal_cache[(minutes, n, zone)], _ = replay.generate_signals(strategy, candle_cache[(minutes, n)])
        signals, (above, morning) = sets[(minutes, n, zone)]
        need_above, skip = FILTERS[row["filter"]]
        allowed = set(signals.entry_index[(above if need_above else True) & ~(morning & skip)])
        chosen = [s for s in signal_cache[(minutes, n, zone)]
                  if times.searchsorted(pd.Timestamp(s["entry_time"])) in allowed]
        for period, (start, end) in windows.items():
            result = replay.replay_execution(strategy, raw, chosen, start, end, allocate=micro.lot_allocation)
            exact_rows.append({"rank": int(row["rank"]), "rules": describe(row), "period": period,
                               "exact_signals": len(signal_cache[(minutes, n, zone)]), "fast_signals": len(signals),
                               **replay.summarize(result, initial=micro.INITIAL)})
        print(f"exact: #{int(row['rank'])} {describe(row)} ({time.time() - started:.0f}s)", flush=True)
    exact = pd.DataFrame(exact_rows)
    exact.to_csv(RESULT_DIR / "exact_finalists.csv", index=False)

    pd.set_option("display.width", 250)
    cols = ["rank", "signal_minutes", "average_days", "zone_pct", "stop_pct", "activation_pct", "giveback_pct",
            "filter", "full_trades", "full_win_rate_pct", "full_profit_usd", "earlier_profit_usd",
            "later_profit_usd", "unseen_profit_usd", "full_approx_dd_pct"]
    print(board[cols].head(12).round(3).to_string(index=False))
    print(f"\nprofitable full: {(board.full_profit_usd > 0).sum()} / {len(board)} | positive earlier and later: "
          f"{len(both)} | median ${board.full_profit_usd.median():.2f}")
    print("by filter: profitable", board.groupby("filter").full_profit_usd.apply(lambda x: int((x > 0).sum())).to_dict(),
          "median", board.groupby("filter").full_profit_usd.median().round(1).to_dict())
    print("positive both periods by filter", both.groupby("filter").size().to_dict())
    print(both[cols].head(12).round(3).to_string(index=False))
    print(exact[["rank", "period", "exact_signals", "fast_signals", "trades", "win_rate_pct", "net_profit_usd",
                 "max_drawdown_pct", "profit_factor", "average_winner_pct", "average_loser_pct", "fees_usd",
                 "slippage_usd", "trailing_exits", "stop_exits", "trades_per_month"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
