"""SOL live rule with $300 as 3 x $100 lots: the 12% giveback versus holding to an EMA of 1 to 10 hours.

Everything else is the live rule exactly: 3-minute signals, 12-day average, +-0.5% zone from below, bullish
confirmation within 30 minutes, no entries 06:00-12:00 UTC, avoid-strong-bearish filter, stop -2%, trailing
armed at +1.251%. The only thing that changes is what happens after the trail arms.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import sol_trend_ride as ride
import stage3_replay as replay

HOURS = list(range(1, 11))
WF = ride.WF
LABELS = ["base: give back 12%"] + [f"hold to EMA{h}h" for h in HOURS]


def build_table(entries, emas):
    """One exit column per variant, in the shape research.simulate expects."""
    cols = len(LABELS)
    idx = np.full((len(entries), cols), -1, dtype=np.int64)
    raw = np.full((len(entries), cols), np.nan)
    code = np.zeros((len(entries), cols), dtype=np.int8)
    for row, entry in enumerate(entries):
        for column, label in enumerate(LABELS):
            ema = None if column == 0 else emas[HOURS[column - 1]]
            out, price, reason, _ = ride.trade(int(entry), ride.ACTIVATION_PCT, ride.GIVEBACK_PCT,
                                               ema=ema, ema_exit=column > 0)
            if out < 0:
                continue
            idx[row, column], raw[row, column] = out, price
            code[row, column] = 2 if reason == "stop" else 1
    return idx, raw, code


def main() -> None:
    raw = replay.load_raw(ride.SYMBOL, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = ride.SLIP
    times = pd.DatetimeIndex(raw.open_time)
    entries = ride.live_entries(raw)
    emas = {h: pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy() for h in HOURS}
    print(f"{len(entries)} live entry signals", flush=True)

    research.TABLE = build_table(entries, emas)
    research.COLS = len(LABELS)
    research.LOT, research.LOTS, research.INITIAL = 100.0, 3, 300.0
    print("exit table built", flush=True)

    rows = []
    for fee_bps, fee_name in ((10.0, "USDT"), (7.5, "BNB")):
        grid.FEE = fee_bps / 10_000
        stats = {}
        for name, (start, end) in research.WINDOWS.items():
            mask = (times[entries] >= start) & (times[entries] < end)
            stats[name] = research.simulate(entries[mask], np.flatnonzero(mask))
        for column, label in enumerate(LABELS):
            full = {key: float(value[column]) for key, value in stats["full"].items()}
            wins, losses = full["wins"], full["trades"] - full["wins"]
            rows.append({"exit": label, "fees": fee_name, "trades": int(full["trades"]),
                         "win_rate": round(100 * full["wins"] / max(full["trades"], 1)),
                         "avg_win": full["gross_win"] / wins if wins else 0.0,
                         "avg_loss": -full["gross_loss"] / losses if losses else 0.0,
                         "full": full["profit"],
                         "earlier": float(stats["earlier"]["profit"][column]),
                         "later": float(stats["later"]["profit"][column]),
                         "unseen": float(stats["unseen"]["profit"][column]),
                         "walk_forward": sum(float(stats[w]["profit"][column]) for w in WF),
                         "wf_windows": f"{sum(float(stats[w]['profit'][column]) > 0 for w in WF)}/6",
                         "drawdown": full["dd"]})
    out = pd.DataFrame(rows)
    out.to_csv(grid.ROOT / "results" / "sol_ema_hold_3lots.csv", index=False)
    pd.set_option("display.width", 250)
    for fee in ("BNB", "USDT"):
        print(f"\n=== SOL live rule, $300 as 3 x $100 lots, {fee} fees")
        print(out[out.fees == fee].drop(columns=["fees"]).set_index("exit").round(2).to_string())


if __name__ == "__main__":
    main()
