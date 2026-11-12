"""SOL's own settings, re-checked one at a time against what is deployed.

Deployed: 3-minute candles, 12-day average, +-0.5% zone, no entries 06:00-12:00 UTC, Mode C on a 60-minute chart
(24 bars, <=2.0%, no wait, -4% stop), exit stop -2%, trail +1.251% / giveback 12%, Mode A on the 8-hour line.

Each block changes ONE thing and leaves the rest deployed, at SOL's saturation point of 3 x $100 with the live
buying rule. Every block ends with the honest gate: choose the value on the six months before each test window
and see whether choosing beats leaving it alone. A better number on full history means nothing on its own - this
is re-optimising on the same data the settings were first picked from.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_adaptive_average as ad
import eth_regime as rg
import sol_pullback as sp

CORE = {"dip", "breakout"}
LOTS = [(3, CORE)]
DEPLOYED = dict(hours=8, stop=2.0, arm=1.251, giveback=12.0, days=12, blocked=(6, 12),
                mode_c=dict(chart=60, bars=24, zone=2.0, confirm=0, stop=4.0, arm=1.283, giveback=22.0))
TRAINS = [f"wf{i}_train" for i in range(6)]


def build(raw, frame, bullish, emas, *, hours=8, stop=2.0, arm=1.251, giveback=12.0, days=12, blocked=(6, 12),
          mode_c=None):
    """Every SOL trade for one set of settings, exits included."""
    mode_c = mode_c or DEPLOYED["mode_c"]
    rule = {**live.load_rule("sol"), "blocked": blocked}
    ema = emas.get(hours)
    trades = []
    for entry in ad.entries_for(raw, rule, frame, ad.average_by_bar(raw, frame, days * 1440)):
        entry = int(entry)
        out, price, _ = opt.trade(entry, arm, giveback, stop, ema if (ema is not None and bullish[entry]) else None)
        trades.append((entry, out, price, "dip"))
    high, low, open_, close, last_minute = v4.bars_for(raw, mode_c["chart"])
    entries = v4.entries_for(high, low, close, last_minute, mode_c["bars"], mode_c["zone"], mode_c["confirm"],
                             grid.CLOSE, len(raw))
    if blocked:
        hour = grid.TIMES[entries].hour
        entries = entries[~((hour >= blocked[0]) & (hour < blocked[1]))]
    for entry in entries:
        entry = int(entry)
        out, price, _ = opt.trade(entry, mode_c["arm"], mode_c["giveback"], mode_c["stop"],
                                  ema if (ema is not None and bullish[entry]) else None)
        trades.append((entry, out, price, "breakout"))
    return sorted(trades, key=lambda t: t[0])


def windows_for(trades):
    return {w: sp.simulate(trades, LOTS, 100.0, *research.WINDOWS[w])["profit"]
            for w in (*TRAINS, *rg.TESTS, "full", "unseen")}


def report(title, variants, base_key, raw, frame, bullish, emas):
    """Score every variant, print the table, then the honest gate against what is deployed."""
    scored = {name: windows_for(build(raw, frame, bullish, emas, **settings)) for name, settings in variants.items()}
    rows = []
    for name, runs in scored.items():
        wf = [runs[w] for w in rg.TESTS]
        rows.append({"setting": name + (" (deployed)" if name == base_key else ""), "profit": round(runs["full"], 2),
                     "walk_forward": round(sum(wf), 2), "windows": f"{sum(v > 0 for v in wf)}/6",
                     "unseen": round(runs["unseen"], 2)})
    frame_out = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(f"\n=== {title}")
    print(frame_out.set_index("setting").to_string())
    base = scored[base_key]
    picks = [max(scored, key=lambda n: scored[n][TRAINS[i]]) for i in range(6)]
    honest = sum(scored[p][t] for p, t in zip(picks, rg.TESTS))
    deployed = sum(base[t] for t in rg.TESTS)
    chosen = ", ".join(sorted({p for p in picks}))
    print(f"  honest (chosen in advance) ${honest:8.2f}   deployed, no choice ${deployed:8.2f}"
          f"   {'CHOOSING WINS' if honest > deployed else 'leaving it alone wins'}")
    print(f"  training picked: {chosen}")


def main() -> None:
    raw, bullish, _ = sp.setup()
    rule = live.load_rule("sol")
    frame = grid.signal_frame(raw, replay.daily_averages(raw), rule["minutes"])
    for period in (7, 15, 30):
        frame[period] = np.array([np.nan if v is None else float(v) for v in frame[period]])
    emas = {h: pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy()
            for h in (2, 4, 6, 8, 12, 16, 24, 36, 48)}
    pd.set_option("display.width", 220)

    deployed = windows_for(build(raw, frame, bullish, emas))
    print("SOL as deployed, 3 x $100: "
          f"profit ${deployed['full']:.2f}, walk-forward ${sum(deployed[t] for t in rg.TESTS):.2f}")

    report("1. the Mode A trend line", {"no Mode A": dict(hours=0),
                                        **{f"{h}h": dict(hours=h) for h in (2, 4, 6, 8, 12, 16, 24, 36, 48)}},
           "8h", raw, frame, bullish, emas)

    report("2. the dip exit: stop and giveback",
           {f"stop -{s:g}%, giveback {g:g}%": dict(stop=s, giveback=g)
            for s in (1.5, 2.0, 2.5, 3.0, 4.0) for g in (8.0, 12.0, 16.0, 20.0, 30.0)},
           "stop -2%, giveback 12%", raw, frame, bullish, emas)

    report("3. the average the dip buys into", {f"{d}-day": dict(days=d) for d in (7, 10, 12, 15, 20)},
           "12-day", raw, frame, bullish, emas)

    report("4. the hours entries are skipped",
           {"none": dict(blocked=None), "06-12 UTC": dict(blocked=(6, 12)), "00-06 UTC": dict(blocked=(0, 6)),
            "12-18 UTC": dict(blocked=(12, 18)), "18-24 UTC": dict(blocked=(18, 24))},
           "06-12 UTC", raw, frame, bullish, emas)

    band = {}
    for chart in (30, 60, 120):
        for bars in (12, 24, 36):
            for zone in (1.5, 2.0, 2.5):
                band[f"{chart}m x {bars} bars ({chart * bars // 60}h), <={zone}%"] = dict(
                    mode_c={**DEPLOYED["mode_c"], "chart": chart, "bars": bars, "zone": zone})
    report("5. the Mode C quiet band", band, "60m x 24 bars (24h), <=2.0%", raw, frame, bullish, emas)


if __name__ == "__main__":
    main()
