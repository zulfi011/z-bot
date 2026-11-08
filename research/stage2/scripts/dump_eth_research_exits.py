"""Research side of the parity diff: every ETH entry with the exit eth_optimal.py would take.

Written to a CSV so the live-engine side can compare in a separate process (the two import different
copies of `app.domain`).
"""

from __future__ import annotations

import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

EMA_HOURS, STOP = 16, 4.5
OUT = grid.ROOT / "results" / "eth_research_exits.csv"


def main() -> None:
    rule = live.load_rule("eth")
    raw = replay.load_raw("ETHUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    times = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=EMA_HOURS * 60, adjust=False).mean().to_numpy()
    rows = []
    for entry in live.live_entries(raw, rule):
        entry = int(entry)
        mode_a = bool(bullish[entry])
        out, price, code = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], STOP,
                                     ema if mode_a else None)
        rows.append({"entry_index": entry, "entry_time": times[entry], "mode": "A" if mode_a else "B",
                     "exit_index": out, "exit_price": price, "reason": code,
                     "ema_at_exit": ema[out] if out >= 0 else float("nan")})
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT, index=False)
    print(f"{len(frame)} entries -> {OUT}")
    print(frame["mode"].value_counts().to_dict(), frame.reason.value_counts().to_dict())


if __name__ == "__main__":
    main()
