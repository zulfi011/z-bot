"""Follow-up: the bucket table leaned the WRONG way, so test the opposite filter honestly."""
from __future__ import annotations
import numpy as np, pandas as pd
from scipy import stats
import live_ema_hold_all as live, run_eth_full_research as research
import run_sol_stage3_space_grid as grid, three_modes as tm, eth_volume_filter as vf


def main() -> None:
    raw = vf.load_raw_volume()
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=tm.EMA_HOURS * 60, adjust=False).mean().to_numpy()
    pd.set_option("display.width", 280)

    mc = tm.MODE_C
    high, low, open_, close, last_minute, measures = vf.bars_with_volume(raw, mc["chart"])
    entries, ratios = vf.breakouts_with_ratio(high, low, close, last_minute, mc["bars"], mc["zone"],
                                              mc["confirm"], grid.CLOSE, len(raw), measures)
    blocked = live.load_rule("eth")["blocked"]
    hours = grid.TIMES[entries].hour
    keep = ~((hours >= blocked[0]) & (hours < blocked[1]))
    entries, ratios = entries[keep], {k: v[keep] for k, v in ratios.items()}

    alone = [t for t in vf.build(raw, bullish, ema, entries) if t[3] == "breakout"]
    ledger = tm.account(alone, *research.WINDOWS["full"], 7.5 / 10_000)["ledger"]
    ledger = ledger.assign(ratio=ledger.entry.map(pd.Series(ratios["volume"], index=entries)))
    rho, p = stats.spearmanr(ledger.ratio, ledger.pnl)
    print(f"Mode C trades in the full window: {len(ledger)}")
    print(f"rank correlation between volume ratio and P&L: rho={rho:+.3f}, p={p:.3f}  "
          f"({'no relationship' if p > 0.05 else 'significant'})")

    print("\n=== the INVERSE filter: only take the QUIETER breaks")
    rows = [tm.evaluate("no filter (deployed today)", vf.build(raw, bullish, ema, entries))]
    for cap in (1.5, 2.0, 2.5, 3.0):
        kept = entries[ratios["volume"] <= cap]
        rows.append(tm.evaluate(f"volume ratio <= {cap}  ({len(kept)} candidates)",
                                vf.build(raw, bullish, ema, kept)))
    print(pd.DataFrame(rows).set_index("strategy").to_string())


if __name__ == "__main__":
    main()
