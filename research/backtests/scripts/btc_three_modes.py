"""BTC with all three modes. Its exit grid said the trend line is useless and the stop is its lever; its
consolidation grid produced a rule that worked but sat on a cliff edge. Both claims get retested here."""

from __future__ import annotations

import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import three_modes as three

three.COIN = "btc"
BTC_C = dict(chart=10, bars=20, zone=0.3, confirm=1, stop=2.0, arm=1.283, giveback=22.0)
COLS = ["trades", "modeC", "win_rate", "avg_win", "avg_loss", "profit", "earlier", "later", "unseen",
        "walk_forward", "wf_windows", "drawdown"]


def main() -> None:
    rule = live.load_rule("btc")
    raw = replay.load_raw("BTCUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    pd.set_option("display.width", 250)
    print(f"BTC deployed: {rule['average_days']}-day average, zone +-{rule['zone_pct']}%, stop -{rule['stop_pct']}%, "
          f"arm +{rule['activation_pct']}%, giveback {rule['giveback_pct']}%\n")

    emas = {h: pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy()
            for h in (4, 8, 12, 16, 24, 36, 48)}

    print("=== Mode A: does a trend line help BTC? (dip only)")
    rows = [three.evaluate("Mode B only (deployed)",
                           three.build(raw, bullish, None, set(), mode_c=None, dip_stop=rule["stop_pct"]))]
    for h, ema in emas.items():
        rows.append(three.evaluate(f"EMA {h}h in uptrend",
                                   three.build(raw, bullish, ema, {"dip"}, mode_c=None, dip_stop=rule["stop_pct"])))
    print(pd.DataFrame(rows).set_index("strategy")[COLS].to_string())

    print("\n=== Mode B: BTC's lever was the stop, and a wider giveback (dip only)")
    rows = []
    for stop, give in ((3.0, 14.0), (4.0, 14.0), (5.0, 14.0), (3.0, 50.0), (4.5, 50.0), (5.0, 50.0)):
        rows.append(three.evaluate(f"stop -{stop:g}%, give back {give:g}%",
                                   three.build(raw, bullish, None, set(), mode_c=None, dip_stop=stop,
                                               dip_giveback=give)))
    print(pd.DataFrame(rows).set_index("strategy")[COLS].to_string())

    print("\n=== Mode C, on top of the deployed exit - and its neighbours, because its grid was a cliff edge")
    rows = []
    for label, setting in (("10m/3.3h/0.3%/1m (its grid winner)", BTC_C),
                           ("10m/3.3h/0.3%/3m", {**BTC_C, "confirm": 3}),
                           ("10m/2h/0.3%/1m", {**BTC_C, "bars": 12}),
                           ("10m/3.3h/0.5%/1m", {**BTC_C, "zone": 0.5}),
                           ("5m/3.3h/0.3%/1m", {**BTC_C, "chart": 5, "bars": 40}),
                           ("15m/5h/0.3%/1m", {**BTC_C, "chart": 15})):
        rows.append(three.evaluate(label, three.build(raw, bullish, None, set(), mode_c=setting,
                                                      dip_stop=rule["stop_pct"])))
    rows.append(three.evaluate("Mode C alone",
                               [t for t in three.build(raw, bullish, None, set(), mode_c=BTC_C,
                                                       dip_stop=rule["stop_pct"]) if t[3] == "breakout"]))
    print(pd.DataFrame(rows).set_index("strategy")[COLS].to_string())


if __name__ == "__main__":
    main()
