"""The EMA hold only helps in the strong first year. Does switching on the trend regime fix that?

Variant: when the market is in a clean uptrend at entry (7-day > 15-day > 30-day average), hold to the EMA;
otherwise fall back to the live 12% giveback. Control: the opposite switch.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import sol_trend_ride as ride
import stage3_replay as replay

HOURS = [2, 4, 6, 8, 10]
WF = ride.WF


def regime_flags(raw: pd.DataFrame) -> np.ndarray:
    """Per 1-minute bar: is 7d > 15d > 30d, using the same completed-day averages the live rule uses."""
    daily = replay.daily_averages(raw)
    days = raw.open_time.dt.floor("D")
    values = np.array([[np.nan if v is None else float(v) for v in daily.get(day, (None,) * 3)] for day in days])
    a7, a15, a30 = values[:, 0], values[:, 1], values[:, 2]
    with np.errstate(invalid="ignore"):
        return np.isfinite(a7) & np.isfinite(a15) & np.isfinite(a30) & (a7 > a15) & (a15 > a30)


def main() -> None:
    raw = replay.load_raw(ride.SYMBOL, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = ride.SLIP
    times = pd.DatetimeIndex(raw.open_time)
    entries = ride.live_entries(raw)
    bullish = regime_flags(raw)
    emas = {h: pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy() for h in HOURS}
    print(f"{len(entries)} signals, {100 * bullish[entries].mean():.0f}% of them in a clean uptrend", flush=True)

    labels = ["base: give back 12%"]
    labels += [f"EMA{h}h always" for h in HOURS]
    labels += [f"EMA{h}h in uptrend, else 12%" for h in HOURS]
    labels += [f"EMA{h}h when NOT uptrend (control)" for h in HOURS]
    cols = len(labels)
    idx = np.full((len(entries), cols), -1, dtype=np.int64)
    price_table = np.full((len(entries), cols), np.nan)
    code = np.zeros((len(entries), cols), dtype=np.int8)
    for row, entry in enumerate(entries):
        entry = int(entry)
        plain = ride.trade(entry, ride.ACTIVATION_PCT, ride.GIVEBACK_PCT)
        by_hour = {h: ride.trade(entry, ride.ACTIVATION_PCT, ride.GIVEBACK_PCT, ema=emas[h], ema_exit=True)
                   for h in HOURS}
        chosen = [plain]
        chosen += [by_hour[h] for h in HOURS]
        chosen += [by_hour[h] if bullish[entry] else plain for h in HOURS]
        chosen += [plain if bullish[entry] else by_hour[h] for h in HOURS]
        for column, (out, price, reason, _) in enumerate(chosen):
            if out < 0:
                continue
            idx[row, column], price_table[row, column] = out, price
            code[row, column] = 2 if reason == "stop" else 1

    research.TABLE = (idx, price_table, code)
    research.COLS = cols
    research.LOT, research.LOTS, research.INITIAL = 100.0, 3, 300.0
    rows = []
    for fee_bps, fee_name in ((10.0, "USDT"), (7.5, "BNB")):
        grid.FEE = fee_bps / 10_000
        stats = {}
        for name, (start, end) in research.WINDOWS.items():
            mask = (times[entries] >= start) & (times[entries] < end)
            stats[name] = research.simulate(entries[mask], np.flatnonzero(mask))
        for column, label in enumerate(labels):
            full = {key: float(value[column]) for key, value in stats["full"].items()}
            rows.append({"exit": label, "fees": fee_name, "trades": int(full["trades"]),
                         "win_rate": round(100 * full["wins"] / max(full["trades"], 1)),
                         "full": full["profit"], "earlier": float(stats["earlier"]["profit"][column]),
                         "later": float(stats["later"]["profit"][column]),
                         "unseen": float(stats["unseen"]["profit"][column]),
                         "walk_forward": sum(float(stats[w]["profit"][column]) for w in WF),
                         "wf_windows": f"{sum(float(stats[w]['profit'][column]) > 0 for w in WF)}/6",
                         "drawdown": full["dd"]})
    out = pd.DataFrame(rows)
    out.to_csv(grid.ROOT / "results" / "sol_ema_hold_regime.csv", index=False)
    pd.set_option("display.width", 250)
    for fee in ("BNB", "USDT"):
        print(f"\n=== $300 as 3 x $100 lots, {fee} fees")
        print(out[out.fees == fee].drop(columns=["fees"]).set_index("exit").round(2).to_string())


if __name__ == "__main__":
    main()
