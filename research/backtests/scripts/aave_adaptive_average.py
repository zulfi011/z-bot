"""Does AAVE's dip entry do better with a different average - or a faster one while the market is trending up?

AAVE buys a touch of its 10-day average from below, inside a +-0.1% zone. This tries fixed alternatives from 3
hours to 30 days, and adaptive rules that switch between a short average and the deployed 10-day.

  fixed      30d / 20d / 15d / 12d / 10d (deployed) / 7d / 5d / 3d / 2d / 1d / 12h / 6h / 3h
  adaptive   the other average while AAVE's daily averages are stacked 7 > 15 > 30, the 10-day otherwise
  inverse    the other average while they are NOT stacked up, the 10-day in uptrends
  lots       SHARED (the dip redefined on the 3 deployed lots, Mode C untouched) or SEPARATE (the 10-day dip
             kept and the alternative run as an extra way in on 1-3 lots of its own)

Everything else stays deployed, including the +-0.1% zone, the downtrend filter and the 06-12 blocked window.
Separate versions are judged against more shared lots AND 3 bigger lots. This is the last idea on the last coin.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_adaptive_average as ad
import eth_regime as rg
import aave_settings_recheck as a
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE, ALT = {"dip", "breakout"}, {"alt dip"}
LENGTHS = [("30d", 30 * 1440), ("20d", 20 * 1440), ("15d", 15 * 1440), ("12d", 12 * 1440),
           ("10d (deployed)", 10 * 1440), ("7d", 7 * 1440), ("5d", 5 * 1440), ("3d", 3 * 1440),
           ("2d", 2 * 1440), ("1d", 1440), ("12h", 720), ("6h", 360), ("3h", 180)]
DEPLOYED = 10 * 1440
SIZES = [1, 2, 3]


def dip_trades(entries, rule, source="dip"):
    out = []
    for entry in entries:
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"], None)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": source, "why": why})
    return out


def mode_c_trades(raw, rule):
    high, low, open_, close, last_minute = v4.bars_for(raw, a.MODE_C["chart"])
    entries = v4.entries_for(high, low, close, last_minute, a.MODE_C["bars"], a.MODE_C["zone"], a.MODE_C["wait"],
                             grid.CLOSE, len(raw))
    if rule["blocked"] and len(entries):
        hours = grid.TIMES[entries].hour
        entries = entries[~((hours >= rule["blocked"][0]) & (hours < rule["blocked"][1]))]
    out = []
    for entry in entries:
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, a.MODE_C["arm"], a.MODE_C["giveback"], a.MODE_C["stop"], None)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": "breakout", "why": why})
    return out


def main() -> None:
    raw, bullish = a.setup()
    rule = live.load_rule(a.COIN)
    daily = replay.daily_averages(raw)
    frame = grid.signal_frame(raw, daily, rule["minutes"])
    for period in (7, 15, 30):
        frame[period] = np.array([np.nan if v is None else float(v) for v in frame[period]])
    mode_c = mode_c_trades(raw, rule)
    deployed_entries = ad.entries_for(raw, rule, frame, ad.average_by_bar(raw, frame, DEPLOYED))
    core = sorted(dip_trades(deployed_entries, rule) + mode_c, key=lambda t: t["entry"])
    pd.set_option("display.width", 270)

    live_entries = live.live_entries(raw, rule)
    print(f"deployed dip entries {len(live_entries)}; rebuilt with the 10-day average {len(deployed_entries)}; "
          f"identical: {np.array_equal(np.asarray(live_entries), deployed_entries)}")

    base = vf.score("AAVE as deployed, 3 x $100", core, [(3, CORE)])
    controls = {"base": base}
    for n in (4, 5, 6):
        controls[f"{n} shared"] = vf.score(f"{n} x $100 shared (control)", core, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger {n}"] = vf.score(f"3 x ${n * 100 / 3:.0f} (control)", core, [(3, CORE)])
        w.LOT = 100.0
    print("\n=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    bar_bullish = np.array([bool(v) for v in (frame[7] > frame[15]) & (frame[15] > frame[30])])
    long_average = ad.average_by_bar(raw, frame, DEPLOYED)
    built = {}
    for label, minutes in LENGTHS:
        short = ad.average_by_bar(raw, frame, minutes)
        built[f"fixed {label}"] = ad.entries_for(raw, rule, frame, short)
        if minutes != DEPLOYED:
            built[f"{label} in uptrends"] = ad.entries_for(raw, rule, frame, np.where(bar_bullish, short, long_average))
            built[f"{label} in chop"] = ad.entries_for(raw, rule, frame, np.where(bar_bullish, long_average, short))
    print(f"\n{len(built)} average rules")

    print("\n=== 1. SHARED: the dip entry redefined on AAVE's 3 deployed lots (Mode C unchanged, best 10)")
    rows = [base] + [vf.score(label, sorted(dip_trades(entries, rule) + mode_c, key=lambda t: t["entry"]),
                              [(3, CORE)]) for label, entries in built.items()]
    frame1 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame1.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame1.set_index("setup").tail(3).to_string())
    print(f"  beating the deployed 10-day: {int((frame1.walk_forward > base['walk_forward']).sum())}/{len(frame1) - 1}"
          f" on walk-forward, {int((frame1.profit > base['profit']).sum())}/{len(frame1) - 1} on the full window")

    print("\n=== 2. how often each average is touched, and in what market")
    counts = [{"average": label, "candidate entries": len(entries),
               "in an uptrend": f"{(bullish[entries].mean() * 100 if len(entries) else 0):.0f}%",
               "per month": round(len(entries) / 23, 1)}
              for label, entries in built.items() if label.startswith("fixed")]
    print(pd.DataFrame(counts).set_index("average").to_string())

    print("\n=== 3. SEPARATE: the 10-day dip stays, the alternative runs as an extra way in on its own lots")
    sleeves = {label: sorted(core + dip_trades(entries, rule, "alt dip"), key=lambda t: t["entry"])
               for label, entries in built.items() if label != "fixed 10d (deployed)"}
    for size in SIZES:
        more, bigger = controls[f"{3 + size} shared"], controls[f"3 bigger {3 + size}"]
        rows3 = [vf.score(label, book, [(3, CORE), (size, ALT)]) for label, book in sleeves.items()]
        part = pd.DataFrame(rows3).sort_values("walk_forward", ascending=False)
        print(f"\n  --- own {size} (${(3 + size) * 100}) against {3 + size} shared lots "
              f"(+${more['walk_forward']:.2f}) and 3 bigger lots (+${bigger['walk_forward']:.2f})")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating more lots: {int((part.walk_forward > more['walk_forward']).sum())}/{len(part)}; "
              f"beating bigger lots: {int((part.walk_forward > bigger['walk_forward']).sum())}/{len(part)}")

    print("\n=== 4. the honest test: the average is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    shared_books = {label: sorted(dip_trades(entries, rule) + mode_c, key=lambda t: t["entry"])
                    for label, entries in built.items()}
    for label, books, pots, control_pots, control_lot in (
            ("shared, 3 lots", shared_books, [(3, CORE)], [(3, CORE)], 100.0),
            ("own 2 vs more lots", sleeves, [(3, CORE), (2, ALT)], [(5, CORE)], 100.0),
            ("own 2 vs bigger lots", sleeves, [(3, CORE), (2, ALT)], [(3, CORE)], 500 / 3)):
        w.LOT = control_lot
        control_w = {x: simulate(core, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        w.LOT = 100.0
        scores = {k: {x: simulate(v, pots, *research.WINDOWS[x])["profit"] for x in windows} for k, v in books.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(books, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        print(f"\n  --- {label}")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    best fixed choice in hindsight {best}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")
        print(f"    it picked: {'; '.join(picks)}")


if __name__ == "__main__":
    main()
