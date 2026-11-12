"""BTC's own settings, re-checked one at a time against what is deployed.

Deployed: 5-minute signal candles, a 5-day average, a +-0.2% zone touched from below, a green candle within 30
minutes, the confirming close must be above the 30-day average, no entries 06:00-12:00 UTC, exit stop -3%,
trail arms +1.257% and gives back 14%. No Mode C, no trend exit.

BTC's own provenance calls this fragile - "only the 5-day average and +-0.2% zone work (neighbours lose)" - and
its walk-forward was -$19.80 in the original research, so this asks whether the deployed point is still the right
one, and how sharp the cliff around it is.

Each block changes ONE thing and leaves the rest deployed, on 3 x $100 with the live buying rule. Every block
ends with the honest gate: choose the value on the six months before each test window and see whether choosing
beats leaving it alone. A better number on full history means nothing on its own - that is re-optimising on the
data the settings came from.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_adaptive_average as ad
import eth_regime as rg
import btc_pullback as bp
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE = {"dip"}
LOTS = [(3, CORE)]
DEPLOYED = dict(days=5, zone=0.2, minutes=5, stop=3.0, arm=1.257, giveback=14.0, blocked=(6, 12),
                above_30d=True, max_above=None)


def build(raw, frames, bullish, *, days=5, zone=0.2, minutes=5, stop=3.0, arm=1.257, giveback=14.0,
          blocked=(6, 12), above_30d=True, max_above=None):
    """Every BTC trade for one set of settings."""
    rule = {**live.load_rule("btc"), "zone_pct": zone, "minutes": minutes, "blocked": blocked,
            "above_30d": above_30d, "max_above_30d": max_above}
    frame = frames[minutes]
    entries = ad.entries_for(raw, rule, frame, ad.average_by_bar(raw, frame, days * 1440))
    if above_30d:                       # ad.entries_for does not apply the 30-day filter; do it here
        index = (entries - frame["first_raw"]) // minutes - 1
        a30, close = frame[30], frame["close"]
        ceiling = a30[index] * (1 + (max_above or 1e9) / 100)
        with np.errstate(invalid="ignore"):
            entries = entries[(close[index] > a30[index]) & (close[index] <= ceiling)]
    out = []
    for entry in entries:
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, arm, giveback, stop, None)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": "dip", "why": why})
    return out


def block(title, raw, frames, bullish, field, values, deployed_value):
    rows = []
    for value in values:
        trades = build(raw, frames, bullish, **{**{k: v for k, v in DEPLOYED.items()}, field: value})
        tag = " (deployed)" if value == deployed_value else ""
        rows.append({**vf.score(f"{field} = {value}{tag}", trades, LOTS), "value": str(value)})
    print(f"\n=== {title}")
    print(pd.DataFrame(rows).drop(columns=["value"]).set_index("setup").to_string())
    return {row["value"]: row for row in rows}


def honest(raw, frames, bullish, field, values, deployed_value, label):
    """Choose this setting on the six months before each window; compare with leaving it deployed."""
    windows = (*TRAINS, *rg.TESTS)
    scores = {}
    for value in values:
        trades = build(raw, frames, bullish, **{**DEPLOYED, field: value})
        scores[value] = {x: simulate(trades, LOTS, *research.WINDOWS[x])["profit"] for x in windows}
    picks = [max(scores, key=lambda v: scores[v][TRAINS[i]]) for i in range(6)]
    chosen = sum(scores[p][t] for p, t in zip(picks, rg.TESTS))
    left = sum(scores[deployed_value][t] for t in rg.TESTS)
    best = max(values, key=lambda v: sum(scores[v][t] for t in rg.TESTS))
    print(f"  honest: choosing {label} each window earns ${chosen:7.2f} against ${left:7.2f} for leaving it "
          f"deployed ({sum(scores[p][t] > scores[deployed_value][t] for p, t in zip(picks, rg.TESTS))}/6 better)")
    print(f"          it picked {picks}; best fixed value in hindsight {best} "
          f"(${sum(scores[best][t] for t in rg.TESTS):7.2f})")


def main() -> None:
    raw, bullish = bp.setup()
    daily = replay.daily_averages(raw)
    frames = {}
    for minutes in (1, 3, 5, 15):
        frame = grid.signal_frame(raw, daily, minutes)
        for period in (7, 15, 30):
            frame[period] = np.array([np.nan if v is None else float(v) for v in frame[period]])
        frames[minutes] = frame
    pd.set_option("display.width", 250)

    deployed = build(raw, frames, bullish)
    live_entries = live.live_entries(raw, live.load_rule("btc"))
    print(f"deployed dip entries {len(live_entries)}; rebuilt {len(deployed)}; "
          f"identical: {len(live_entries) == len(deployed)}")
    print(pd.DataFrame([vf.score("BTC as deployed, 3 x $100", deployed, LOTS)]).set_index("setup").to_string())

    block("1. the signal average", raw, frames, bullish, "days", [3, 4, 5, 6, 7, 8, 10, 12], 5)
    honest(raw, frames, bullish, "days", [3, 4, 5, 6, 7, 8, 10, 12], 5, "the average length")

    block("2. the touch zone", raw, frames, bullish, "zone", [0.1, 0.15, 0.2, 0.3, 0.5, 0.75], 0.2)
    honest(raw, frames, bullish, "zone", [0.1, 0.15, 0.2, 0.3, 0.5, 0.75], 0.2, "the zone width")

    block("3. the signal candle", raw, frames, bullish, "minutes", [1, 3, 5, 15], 5)
    honest(raw, frames, bullish, "minutes", [1, 3, 5, 15], 5, "the candle length")

    block("4. the protective stop", raw, frames, bullish, "stop", [2.0, 2.5, 3.0, 4.0, 5.0, 6.0], 3.0)
    honest(raw, frames, bullish, "stop", [2.0, 2.5, 3.0, 4.0, 5.0, 6.0], 3.0, "the stop")

    block("5. where the trail arms", raw, frames, bullish, "arm", [0.8, 1.0, 1.257, 1.5, 2.0, 3.0], 1.257)
    honest(raw, frames, bullish, "arm", [0.8, 1.0, 1.257, 1.5, 2.0, 3.0], 1.257, "the arming level")

    block("6. how much it gives back", raw, frames, bullish, "giveback", [8.0, 10.0, 14.0, 20.0, 30.0, 50.0], 14.0)
    honest(raw, frames, bullish, "giveback", [8.0, 10.0, 14.0, 20.0, 30.0, 50.0], 14.0, "the giveback")

    print("\n=== 7. the filters (each changed on its own)")
    rows = [vf.score("everything deployed", deployed, LOTS)]
    rows.append(vf.score("no 30-day filter", build(raw, frames, bullish, above_30d=False), LOTS))
    for cap in (5.0, 10.0, 20.0):
        rows.append(vf.score(f"30-day filter capped at +{cap:g}%", build(raw, frames, bullish, max_above=cap), LOTS))
    rows.append(vf.score("no blocked hours", build(raw, frames, bullish, blocked=None), LOTS))
    print(pd.DataFrame(rows).set_index("setup").to_string())


if __name__ == "__main__":
    main()
