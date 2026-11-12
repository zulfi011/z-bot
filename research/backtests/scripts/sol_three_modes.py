"""SOL with all three modes: what Mode A should be, whether Mode B needs changing, and what Mode C adds.

SOL is not ETH. Its own exit grid found that holding to a moving average makes far more money but drops the
win rate to about 53%, which breaks the 75% floor; and no setting at all beat the deployed rule while keeping
75%. So this run asks the question in both forms: the best on profit, and the best that still wins 75% of the
time.
"""

from __future__ import annotations

import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import three_modes as three

three.COIN = "sol"
# SOL's own consolidation grid winner: 1-hour chart, 24-hour zone, 2% wide, no wait, stop -4%.
SOL_MODE_C = dict(chart=60, bars=24, zone=2.0, confirm=0, stop=4.0, arm=1.283, giveback=22.0)


def main() -> None:
    rule = live.load_rule("sol")
    raw = replay.load_raw("SOLUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    pd.set_option("display.width", 260)
    print(f"SOL deployed: stop -{rule['stop_pct']}%, arm +{rule['activation_pct']}%, "
          f"giveback {rule['giveback_pct']}%, {rule['average_days']}-day average, zone +-{rule['zone_pct']}%\n")

    emas = {hours: pd.Series(grid.CLOSE).ewm(span=hours * 60, adjust=False).mean().to_numpy()
            for hours in (4, 8, 12, 16, 24, 36, 48)}

    print("=== Mode A: which trend line, at SOL's deployed stop and arm (dip entry only)")
    rows = [three.evaluate("Mode B only (deployed)", three.build(raw, bullish, emas[16], set(), mode_c=None,
                                                                dip_stop=rule["stop_pct"]))]
    for hours, ema in emas.items():
        rows.append(three.evaluate(f"EMA {hours}h in uptrend",
                                   three.build(raw, bullish, ema, {"dip"}, mode_c=None, dip_stop=rule["stop_pct"])))
    print(pd.DataFrame(rows).set_index("strategy").to_string())

    print("\n=== does Mode B's stop need changing? (EMA 16h in uptrend, dip entry only)")
    rows = []
    for stop in (2.0, 2.5, 3.0, 3.5, 4.0):
        rows.append(three.evaluate(f"stop -{stop}%",
                                   three.build(raw, bullish, emas[16], {"dip"}, mode_c=None, dip_stop=stop)))
    print(pd.DataFrame(rows).set_index("strategy").to_string())

    print("\n=== all three together, at a few Mode A lengths (Mode C = SOL's own grid winner)")
    rows = []
    for hours in (8, 16, 24, 36):
        rows.append(three.evaluate(f"dip + Mode C, EMA {hours}h",
                                   three.build(raw, bullish, emas[hours], {"dip", "breakout"},
                                               mode_c=SOL_MODE_C, dip_stop=rule["stop_pct"])))
    rows.append(three.evaluate("dip + Mode C, no Mode A at all",
                               three.build(raw, bullish, emas[16], set(), mode_c=SOL_MODE_C,
                                           dip_stop=rule["stop_pct"])))
    rows.append(three.evaluate("Mode C alone",
                               [t for t in three.build(raw, bullish, emas[16], {"breakout"}, mode_c=SOL_MODE_C)
                                if t[3] == "breakout"]))
    print(pd.DataFrame(rows).set_index("strategy").to_string())


if __name__ == "__main__":
    main()
