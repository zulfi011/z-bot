"""Pull one real ETH trade under the optimal rule, plus how long trades actually last."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

HOURS = 16


def main() -> None:
    rule = live.load_rule("eth")
    raw = replay.load_raw("ETHUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    times = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=HOURS * 60, adjust=False).mean().to_numpy()
    dip = live.live_entries(raw, rule)

    rows = []
    for entry in dip:
        entry = int(entry)
        mode = "A" if bullish[entry] else "B"
        a = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], 4.5, ema if bullish[entry] else None)
        b = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], 4.5, None)
        if a[0] < 0:
            continue
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        rows.append({"entry": entry, "mode": mode, "hours": (a[0] - entry) / 60,
                     "gain_pct": (a[1] / fill - 1) * 100,
                     "modeB_gain_pct": (b[1] / fill - 1) * 100 if b[0] >= 0 else np.nan,
                     "modeB_hours": (b[0] - entry) / 60 if b[0] >= 0 else np.nan,
                     "exit": a[0], "time": times[entry]})
    frame = pd.DataFrame(rows)
    print("=== how long trades actually last (hours held)")
    print(frame.groupby("mode").hours.describe(percentiles=[.25, .5, .75, .9]).round(1).to_string())
    print(f"\nMode A trades closing within 16 hours: "
          f"{100 * (frame[frame['mode'] == 'A'].hours < 16).mean():.0f}%")
    print(f"Mode A trades closing within 1 hour:   "
          f"{100 * (frame[frame['mode'] == 'A'].hours < 1).mean():.0f}%")

    a = frame[(frame['mode'] == "A") & frame.modeB_gain_pct.notna()].copy()
    a["edge"] = a.gain_pct - a.modeB_gain_pct
    print(f"\nMode A vs Mode B on the same {len(a)} trades: "
          f"A better on {100 * (a.edge > 0).mean():.0f}%, average difference {a.edge.mean():+.2f}%")
    # a representative winner: closest to the median of the trades where A beat B
    winners = a[a.edge > 0].sort_values("edge")
    pick = winners.iloc[int(len(winners) * 0.75)]
    entry, exit_ = int(pick.entry), int(pick.exit)
    start, stop = entry - 120, min(exit_ + 120, len(grid.CLOSE) - 1)
    fill = grid.OPEN[entry] * (1 + grid.SLIP)
    b_exit = int(frame.loc[frame.entry == entry, "exit"].iloc[0])
    b = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], 4.5, None)
    payload = {"times": [t.isoformat() for t in times[start:stop + 1]],
               "close": [round(float(v), 2) for v in grid.CLOSE[start:stop + 1]],
               "ema": [round(float(v), 2) for v in ema[start:stop + 1]],
               "start": start, "entry": entry, "exit_a": exit_, "exit_b": int(b[0]),
               "fill": round(fill, 2), "stop_level": round(fill * 0.955, 2),
               "arm_level": round(fill * 1.01315, 2),
               "price_a": round(float(pick.gain_pct), 2), "price_b": round(float(pick.modeB_gain_pct), 2),
               "exit_price_a": round(float(grid.OPEN[exit_]), 2), "exit_price_b": round(float(b[1]), 2),
               "hours_a": round(float(pick.hours), 1), "hours_b": round(float(pick.modeB_hours), 1)}
    out = grid.ROOT / "results" / "eth_example_trade.json"
    out.write_text(json.dumps(payload))
    print(f"\n=== example trade  entry {times[entry]}  fill ${fill:.2f}")
    print(f"  Mode A: out after {pick.hours:.1f}h at ${grid.OPEN[exit_]:.2f}  ({pick.gain_pct:+.2f}%)")
    print(f"  Mode B: out after {pick.modeB_hours:.1f}h at ${b[1]:.2f}  ({pick.modeB_gain_pct:+.2f}%)")
    print(f"  saved {out}")


if __name__ == "__main__":
    main()
