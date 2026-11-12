"""Who earns what in the combined ETH system, and how sensitive Mode C's zone really is."""

from __future__ import annotations

import pandas as pd

import eth_three_modes as three
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay


def main() -> None:
    raw = replay.load_raw("ETHUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=three.EMA_HOURS * 60, adjust=False).mean().to_numpy()
    pd.set_option("display.width", 260)

    print("=== zone sensitivity, wider than before (wait 30m, everything else as deployed)")
    rows = []
    for zone in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
        setting = {**three.MODE_C, "zone": zone}
        rows.append({**three.evaluate(f"{zone}%", three.build(raw, bullish, ema, {"dip", "breakout"}, mode_c=setting))})
    print(pd.DataFrame(rows).set_index("strategy").to_string())

    print("\n=== who earns what, inside the combined system (zone 2.5% and 3.0%)")
    for zone in (2.5, 3.0):
        trades = three.build(raw, bullish, ema, {"dip", "breakout"}, mode_c={**three.MODE_C, "zone": zone})
        result = three.account(trades, *research.WINDOWS["full"], 7.5 / 10_000)
        ledger = result["ledger"]
        ledger = ledger.assign(mode=["A" if bullish[int(row.entry)] else "B" for row in ledger.itertuples()])
        summary = ledger.groupby(["source", "mode"]).agg(
            trades=("pnl", "size"), won=("pnl", lambda s: int((s > 0).sum())),
            profit=("pnl", "sum"), best=("pnl", "max"), worst=("pnl", "min"),
            avg_hours=("hours", "median")).round(2)
        print(f"-- Mode C zone {zone}%  (total {result['profit']:.2f})")
        print(summary.to_string())

    print("\n=== how often does Mode C fire, and does it steal the dip's lots?")
    for zone in (2.5, 3.0):
        setting = {**three.MODE_C, "zone": zone}
        high, low, open_, close, last_minute = v4.bars_for(raw, setting["chart"])
        signals = v4.entries_for(high, low, close, last_minute, setting["bars"], setting["zone"],
                                 setting["confirm"], grid.CLOSE, len(raw))
        alone = three.evaluate("x", three.build(raw, bullish, ema, {"dip"}, mode_c=None))
        both = three.evaluate("y", three.build(raw, bullish, ema, {"dip", "breakout"}, mode_c=setting))
        print(f"  zone {zone}%: {len(signals)} Mode C signals, {both['modeC']} taken; "
              f"dip trades {alone['trades']} alone -> {both['dip']} together "
              f"({alone['trades'] - both['dip']} crowded out); profit {alone['profit']} -> {both['profit']}")


if __name__ == "__main__":
    main()
