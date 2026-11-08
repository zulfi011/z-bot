"""AAVE with all three modes: its own trend line, its own quiet band, and what the three make together."""

from __future__ import annotations

import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import three_modes as three

three.COIN = "aave"
# The two families AAVE's own consolidation grid liked best.
CANDIDATES_C = {
    "60m/12h/2.0%/1m wait": dict(chart=60, bars=12, zone=2.0, confirm=1, stop=3.5, arm=1.283, giveback=22.0),
    "30m/12h/2.0%/60m wait": dict(chart=30, bars=24, zone=2.0, confirm=60, stop=3.5, arm=1.283, giveback=22.0),
    "60m/12h/2.5%/5m wait": dict(chart=60, bars=12, zone=2.5, confirm=5, stop=3.5, arm=1.283, giveback=22.0),
}


def main() -> None:
    rule = live.load_rule("aave")
    raw = replay.load_raw("AAVEUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    pd.set_option("display.width", 250)
    print(f"AAVE deployed: {rule['average_days']}-day average, zone +-{rule['zone_pct']}%, stop -{rule['stop_pct']}%, "
          f"arm +{rule['activation_pct']}%, giveback {rule['giveback_pct']}%\n")
    cols = ["trades", "modeC", "win_rate", "profit", "earlier", "later", "unseen", "walk_forward", "wf_windows", "drawdown"]

    emas = {h: pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy()
            for h in (4, 6, 8, 12, 16, 24, 36, 48)}

    print("=== Mode A: which trend line, at AAVE's deployed stop and arm (dip only)")
    rows = [three.evaluate("Mode B only (deployed)",
                           three.build(raw, bullish, None, set(), mode_c=None, dip_stop=rule["stop_pct"]))]
    for h, ema in emas.items():
        rows.append(three.evaluate(f"EMA {h}h in uptrend",
                                   three.build(raw, bullish, ema, {"dip"}, mode_c=None, dip_stop=rule["stop_pct"])))
    print(pd.DataFrame(rows).set_index("strategy")[cols].to_string())

    best_hours = 12
    print(f"\n=== does Mode B's stop need changing? (EMA {best_hours}h, dip only)")
    rows = []
    for stop in (3.0, 3.5, 4.0, 4.5, 5.0):
        rows.append(three.evaluate(f"stop -{stop}%",
                                   three.build(raw, bullish, emas[best_hours], {"dip"}, mode_c=None, dip_stop=stop)))
    print(pd.DataFrame(rows).set_index("strategy")[cols].to_string())

    print(f"\n=== Mode C: which band (EMA {best_hours}h, with the dip)")
    rows = []
    for label, setting in CANDIDATES_C.items():
        rows.append(three.evaluate(label, three.build(raw, bullish, emas[best_hours], {"dip", "breakout"},
                                                      mode_c=setting, dip_stop=rule["stop_pct"])))
    rows.append(three.evaluate("no Mode C",
                               three.build(raw, bullish, emas[best_hours], {"dip"}, mode_c=None,
                                           dip_stop=rule["stop_pct"])))
    print(pd.DataFrame(rows).set_index("strategy")[cols].to_string())


if __name__ == "__main__":
    main()
