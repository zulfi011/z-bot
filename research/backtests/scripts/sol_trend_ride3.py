"""The trend exit and the re-entry chain together, which the earlier run never actually tested."""

from __future__ import annotations

import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import sol_trend_ride as ride
import stage3_replay as replay


def main() -> None:
    raw = replay.load_raw(ride.SYMBOL, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP, grid.FEE = ride.SLIP, ride.FEE
    times = pd.DatetimeIndex(raw.open_time)
    entries = ride.live_entries(raw)
    emas = {span: pd.Series(grid.CLOSE).ewm(span=span, adjust=False).mean().to_numpy() for span in (120, 240, 480)}
    pd.set_option("display.width", 250)
    rows = [ride.evaluate("base (live rule today)", entries, times, mode="base")]
    for span in (120, 240, 480):
        rows.append(ride.evaluate(f"EMA{span} trend exit, no chain", entries, times, mode="trend", ema=emas[span]))
        for wait in (5, 10, 15, 30):
            for rule in ("lower_high", "ema_break"):
                rows.append(ride.evaluate(f"EMA{span} + chain {wait}m, {rule}", entries, times, mode="chain_trend",
                                          wait=wait, downtrend=rule, ema=emas[span]))
    out = pd.DataFrame(rows).set_index("variant")
    out.to_csv(grid.ROOT / "results" / "sol_trend_ride_chain.csv")
    print(out.sort_values("full", ascending=False).round(2).to_string())


if __name__ == "__main__":
    main()
