"""Sensitivity of the combined ETH strategy: EMA length, dip stop, and always-vs-uptrend."""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay


def main() -> None:
    rule = live.load_rule("eth")
    raw = replay.load_raw("ETHUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    times = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    dip = live.live_entries(raw, rule)
    c = opt.CONSOL
    high, low, open_, close, last_minute = v4.bars_for(raw, c["chart"])
    brk = v4.entries_for(high, low, close, last_minute, c["bars"], c["zone"], c["confirm"], grid.CLOSE, len(raw))
    brk = brk[~np.isin(brk, dip)]
    both = np.concatenate([dip, brk])
    rows = []
    for hours in (8, 12, 16, 24, 36):
        ema = pd.Series(grid.CLOSE).ewm(span=hours * 60, adjust=False).mean().to_numpy()
        for switch in ("uptrend", "always"):
            for dip_stop in (3.5, 4.0, 4.5, 5.0):
                def use(e):
                    return ema if (switch == "always" or bullish[e]) else None
                exits = [opt.trade(int(e), rule["activation_pct"], rule["giveback_pct"], dip_stop, use(int(e)))
                         for e in dip]
                exits += [opt.trade(int(e), c["arm"], c["giveback"], c["stop"], use(int(e))) for e in brk]
                row = opt.evaluate(f"EMA{hours}h {switch}, dip stop -{dip_stop:g}%", both, exits, times)
                rows.append(row)
    frame = pd.DataFrame(rows).set_index("strategy")
    frame.to_csv(grid.ROOT / "results" / "eth_optimal_tune.csv")
    pd.set_option("display.width", 250)
    ok = frame[frame.win_rate >= 75]
    print("=== combined ETH strategy, sorted by profit (only those keeping a 75%+ win rate)")
    print(ok.sort_values("profit", ascending=False).round(2).to_string())
    print(f"\n{len(frame) - len(ok)} of {len(frame)} variants fell below a 75% win rate")


if __name__ == "__main__":
    main()
