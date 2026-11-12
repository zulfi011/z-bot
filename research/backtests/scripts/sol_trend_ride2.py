"""Follow-up: why the chain stops so early, and how far the trend exit can be pushed."""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import sol_trend_ride as ride
import stage3_replay as replay

WF = ride.WF


def main() -> None:
    raw = replay.load_raw(ride.SYMBOL, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP, grid.FEE = ride.SLIP, ride.FEE
    times = pd.DatetimeIndex(raw.open_time)
    entries = ride.live_entries(raw)
    emas = {span: pd.Series(grid.CLOSE).ewm(span=span, adjust=False).mean().to_numpy()
            for span in (60, 120, 180, 240, 360, 480)}
    pd.set_option("display.width", 250)

    print("=== how long do the chains actually get? (wait 5m and 10m, lower-high stop)")
    for wait in (5, 10):
        result = ride.sequence(entries, mode="chain", times=times, start=research.WINDOWS["full"][0],
                               end=research.WINDOWS["full"][1], wait=wait, downtrend="lower_high", ema=emas[60])
        ledger = result["ledger"]
        print(f"  wait {wait}m: " + ", ".join(f"link {k}: {v}" for k, v in ledger.link.value_counts().sort_index().items()))
        extra = ledger[ledger.link > 0]
        print(f"           extra buys {len(extra)}, of them winners {int((extra.return_pct > 0).sum())} "
              f"({100 * (extra.return_pct > 0).mean():.0f}%), average {extra.return_pct.mean():+.2f}%, "
              f"total {extra.return_pct.sum():+.1f}%")

    print("\n=== the trend exit, pushed: EMA length x stop size (one $100 lot, BNB fees)")
    rows = []
    for span in (60, 120, 180, 240, 360, 480):
        for stop in (1.5, 2.0, 2.5, 3.0):
            ride.STOP_PCT = stop
            row = ride.evaluate(f"EMA{span}, stop -{stop:g}%", entries, times, mode="trend", ema=emas[span])
            rows.append(row)
    ride.STOP_PCT = 2.0
    frame = pd.DataFrame(rows).set_index("variant")
    print(frame.sort_values("full", ascending=False).round(2).to_string())

    print("\n=== does the chain help on top of the best trend exit?")
    rows = []
    for span in (120, 240):
        rows.append(ride.evaluate(f"EMA{span} alone", entries, times, mode="trend", ema=emas[span]))
        for wait in (5, 10, 15):
            rows.append(ride.evaluate(f"EMA{span} + chain wait {wait}m", entries, times, mode="chain", wait=wait,
                                      downtrend="ema_break", ema=emas[span]))
    print(pd.DataFrame(rows).set_index("variant").round(2).to_string())


if __name__ == "__main__":
    main()
