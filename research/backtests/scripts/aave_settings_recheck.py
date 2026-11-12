"""AAVE's own settings, re-checked one at a time against what is deployed.

Deployed: 3-minute signal candles, a 10-day average, a +-0.1% zone touched from below, a green candle within 30
minutes, no entries while the averages are stacked downward, none 06:00-12:00 UTC, Mode C on a 30-minute chart
(24 bars, <=2.0%, a 60-minute re-check, -3.5% stop, arm +1.283%, giveback 22%), exit stop -4%, trail arms
+1.276% and gives back 20%. No trend exit - Mode A was tested and deliberately left out.

Each block changes ONE thing and leaves the rest deployed, on 3 x $100 with the live buying rule. Every block
ends with the honest gate: choose the value on the six months before each test window and see whether choosing
beats leaving it alone. A better number on full history means nothing on its own - that is re-optimising on the
data the settings came from. The last block asks the money question instead: more lots or bigger ones.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_adaptive_average as aa
import eth_regime as rg
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

COIN, SYMBOL = "aave", "AAVEUSDT"
CORE = {"dip", "breakout"}
LOTS = [(3, CORE)]
MODE_C = dict(chart=30, bars=24, zone=2.0, wait=60, stop=3.5, arm=1.283, giveback=22.0)
DEPLOYED = dict(days=10, zone=0.1, minutes=3, stop=4.0, arm=1.276, giveback=20.0, blocked=(6, 12),
                bearish=True, mode_c=MODE_C)


def setup():
    raw = replay.load_raw(SYMBOL, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    return raw, live.regime_flags(raw)


def build(raw, frames, *, days=10, zone=0.1, minutes=3, stop=4.0, arm=1.276, giveback=20.0, blocked=(6, 12),
          bearish=True, mode_c=None):
    """Every AAVE trade for one set of settings: the dip and Mode C, both on the giveback trail."""
    mode_c = mode_c or MODE_C
    rule = {**live.load_rule(COIN), "zone_pct": zone, "minutes": minutes, "blocked": blocked}
    frame = frames[minutes]
    entries = aa.entries_for(raw, rule, frame, aa.average_by_bar(raw, frame, days * 1440))
    if not bearish:                       # aa.entries_for always applies the downtrend filter; undo it by
        rule_open = {**rule}              # rebuilding without it is not possible, so flag it in the label only
    trades = []
    for entry in entries:
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, arm, giveback, stop, None)
        trades.append({"entry": entry, "exit": exit_at, "price": price, "source": "dip", "why": why})
    high, low, open_, close, last_minute = v4.bars_for(raw, mode_c["chart"])
    breaks = v4.entries_for(high, low, close, last_minute, mode_c["bars"], mode_c["zone"], mode_c["wait"],
                            grid.CLOSE, len(raw))
    if blocked and len(breaks):
        hours = grid.TIMES[breaks].hour
        breaks = breaks[~((hours >= blocked[0]) & (hours < blocked[1]))]
    for entry in breaks:
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, mode_c["arm"], mode_c["giveback"], mode_c["stop"], None)
        trades.append({"entry": entry, "exit": exit_at, "price": price, "source": "breakout", "why": why})
    return sorted(trades, key=lambda t: t["entry"])


def block(title, raw, frames, field, values, deployed_value, inner=None):
    rows = []
    for value in values:
        settings = {**DEPLOYED}
        if inner:
            settings["mode_c"] = {**MODE_C, inner: value}
        else:
            settings[field] = value
        tag = " (deployed)" if value == deployed_value else ""
        rows.append(vf.score(f"{field} = {value}{tag}", build(raw, frames, **settings), LOTS))
    print(f"\n=== {title}")
    print(pd.DataFrame(rows).set_index("setup").to_string())


def honest(raw, frames, field, values, deployed_value, label, inner=None):
    windows = (*TRAINS, *rg.TESTS)
    scores = {}
    for value in values:
        settings = {**DEPLOYED}
        if inner:
            settings["mode_c"] = {**MODE_C, inner: value}
        else:
            settings[field] = value
        trades = build(raw, frames, **settings)
        scores[value] = {x: simulate(trades, LOTS, *research.WINDOWS[x])["profit"] for x in windows}
    picks = [max(scores, key=lambda v: scores[v][TRAINS[i]]) for i in range(6)]
    chosen = sum(scores[p][t] for p, t in zip(picks, rg.TESTS))
    left = sum(scores[deployed_value][t] for t in rg.TESTS)
    best = max(values, key=lambda v: sum(scores[v][t] for t in rg.TESTS))
    better = sum(scores[p][t] > scores[deployed_value][t] for p, t in zip(picks, rg.TESTS))
    print(f"  honest: choosing {label} each window earns ${chosen:7.2f} against ${left:7.2f} for leaving it "
          f"deployed ({better}/6 better); it picked {picks}; best fixed value in hindsight {best} "
          f"(${sum(scores[best][t] for t in rg.TESTS):7.2f})")


def main() -> None:
    raw, bullish = setup()
    daily = replay.daily_averages(raw)
    frames = {}
    for minutes in (1, 3, 5, 15):
        frame = grid.signal_frame(raw, daily, minutes)
        for period in (7, 15, 30):
            frame[period] = np.array([np.nan if v is None else float(v) for v in frame[period]])
        frames[minutes] = frame
    pd.set_option("display.width", 250)

    deployed = build(raw, frames)
    live_entries = live.live_entries(raw, live.load_rule(COIN))
    dips = [t for t in deployed if t["source"] == "dip"]
    print(f"deployed dip entries {len(live_entries)}; rebuilt {len(dips)}; "
          f"identical: {np.array_equal(np.asarray(live_entries), np.asarray([t['entry'] for t in dips]))}")
    print(pd.DataFrame([vf.score("AAVE as deployed, 3 x $100", deployed, LOTS)]).set_index("setup").to_string())

    block("1. the signal average", raw, frames, "days", [5, 7, 8, 10, 12, 15, 20], 10)
    honest(raw, frames, "days", [5, 7, 8, 10, 12, 15, 20], 10, "the average length")

    block("2. the touch zone", raw, frames, "zone", [0.05, 0.1, 0.2, 0.3, 0.5], 0.1)
    honest(raw, frames, "zone", [0.05, 0.1, 0.2, 0.3, 0.5], 0.1, "the zone width")

    block("3. the signal candle", raw, frames, "minutes", [1, 3, 5, 15], 3)
    honest(raw, frames, "minutes", [1, 3, 5, 15], 3, "the candle length")

    block("4. the protective stop", raw, frames, "stop", [2.0, 3.0, 4.0, 5.0, 6.0, 8.0], 4.0)
    honest(raw, frames, "stop", [2.0, 3.0, 4.0, 5.0, 6.0, 8.0], 4.0, "the stop")

    block("5. where the trail arms", raw, frames, "arm", [0.8, 1.0, 1.276, 1.5, 2.0, 3.0], 1.276)
    honest(raw, frames, "arm", [0.8, 1.0, 1.276, 1.5, 2.0, 3.0], 1.276, "the arming level")

    block("6. how much it gives back", raw, frames, "giveback", [10.0, 14.0, 20.0, 30.0, 50.0, 70.0], 20.0)
    honest(raw, frames, "giveback", [10.0, 14.0, 20.0, 30.0, 50.0, 70.0], 20.0, "the giveback")

    block("7. Mode C: the wait after the break", raw, frames, "wait", [0, 3, 10, 30, 60, 120], 60, inner="wait")
    honest(raw, frames, "wait", [0, 3, 10, 30, 60, 120], 60, "the Mode C wait", inner="wait")

    block("8. Mode C: the band width", raw, frames, "zone", [1.0, 1.5, 2.0, 2.5, 3.0], 2.0, inner="zone")
    honest(raw, frames, "zone", [1.0, 1.5, 2.0, 2.5, 3.0], 2.0, "the Mode C band width", inner="zone")

    block("9. Mode C: the band length", raw, frames, "bars", [12, 24, 40, 60], 24, inner="bars")
    honest(raw, frames, "bars", [12, 24, 40, 60], 24, "the Mode C band length", inner="bars")

    block("10. Mode C: the chart", raw, frames, "chart", [15, 30, 60, 120], 30, inner="chart")
    honest(raw, frames, "chart", [15, 30, 60, 120], 30, "the Mode C chart", inner="chart")

    print("\n=== 11. the blocked hours")
    print(pd.DataFrame([vf.score("06-12 UTC blocked (deployed)", deployed, LOTS),
                        vf.score("no blocked hours", build(raw, frames, blocked=None), LOTS)]
                       ).set_index("setup").to_string())

    print("\n=== 12. the money question: more lots or bigger ones")
    rows = [vf.score("3 x $100 (deployed)", deployed, LOTS)]
    for n in (4, 5, 6):
        rows.append(vf.score(f"{n} x $100 shared", deployed, [(n, CORE)]))
        w.LOT = n * 100 / 3
        rows.append(vf.score(f"3 x ${n * 100 / 3:.0f}", deployed, LOTS))
        w.LOT = 100.0
    print(pd.DataFrame(rows).set_index("setup").to_string())


if __name__ == "__main__":
    main()
