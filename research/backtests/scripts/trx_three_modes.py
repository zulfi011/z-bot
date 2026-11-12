"""TRX with all three modes. Its exit grid said the trend line is useless here and a plain retune wins, so
this asks all three questions again on the same footing: the line, the giveback, and the quiet band."""

from __future__ import annotations

import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import three_modes as three

three.COIN = "trx"
# TRX's own consolidation grid winner: 1-hour chart, 40-hour zone, 2% wide, 3-minute wait, stop -3%.
TRX_C = dict(chart=60, bars=40, zone=2.0, confirm=3, stop=3.0, arm=1.283, giveback=22.0)
COLS = ["trades", "modeC", "win_rate", "avg_win", "avg_loss", "profit", "earlier", "later", "unseen",
        "walk_forward", "wf_windows", "drawdown"]


def main() -> None:
    rule = live.load_rule("trx")
    raw = replay.load_raw("TRXUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    pd.set_option("display.width", 250)
    print(f"TRX deployed: {rule['average_days']}-day average, zone +-{rule['zone_pct']}%, stop -{rule['stop_pct']}%, "
          f"arm +{rule['activation_pct']}%, giveback {rule['giveback_pct']}%, no blocked hours\n")

    emas = {h: pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy()
            for h in (4, 8, 12, 16, 24, 36, 48)}

    print("=== Mode A: does a trend line help TRX at all? (dip only)")
    rows = [three.evaluate("Mode B only (deployed)",
                           three.build(raw, bullish, None, set(), mode_c=None, dip_stop=rule["stop_pct"]))]
    for h, ema in emas.items():
        rows.append(three.evaluate(f"EMA {h}h in uptrend",
                                   three.build(raw, bullish, ema, {"dip"}, mode_c=None, dip_stop=rule["stop_pct"])))
    print(pd.DataFrame(rows).set_index("strategy")[COLS].to_string())

    print("\n=== Mode B: the retune its own exit grid liked (arm and giveback, dip only)")
    rows = []
    for arm, give in ((1.245, 10.0), (1.245, 40.0), (1.245, 50.0), (2.5, 40.0), (3.0, 40.0), (3.0, 50.0)):
        rows.append(three.evaluate(f"arm +{arm}%, give back {give:g}%",
                                   three.build(raw, bullish, None, set(), mode_c=None, dip_stop=rule["stop_pct"],
                                               dip_arm=arm, dip_giveback=give)))
    print(pd.DataFrame(rows).set_index("strategy")[COLS].to_string())

    print("\n=== Mode C, on top of the deployed exit")
    rows = []
    for label, setting in (("60m/40h/2.0%/3m wait (its grid winner)", TRX_C),
                           ("60m/40h/2.0%/1m wait", {**TRX_C, "confirm": 1}),
                           ("60m/20h/2.0%/1m wait", {**TRX_C, "bars": 20, "confirm": 1}),
                           ("60m/48h/2.5%/1m wait", {**TRX_C, "bars": 48, "zone": 2.5, "confirm": 1})):
        rows.append(three.evaluate(label, three.build(raw, bullish, None, set(), mode_c=setting,
                                                      dip_stop=rule["stop_pct"])))
    rows.append(three.evaluate("Mode C alone",
                               [t for t in three.build(raw, bullish, None, set(), mode_c=TRX_C,
                                                       dip_stop=rule["stop_pct"]) if t[3] == "breakout"]))
    print(pd.DataFrame(rows).set_index("strategy")[COLS].to_string())


if __name__ == "__main__":
    main()
