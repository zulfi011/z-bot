"""Does BTC's dip entry do better with a different average - or a faster one while the market is trending up?

BTC buys a touch of its 5-day average from below, inside a +-0.2% zone, when the confirming close is above the
30-day average. Its own recheck showed the 5-day is a spike rather than a plateau, so this asks the wider
question: fixed alternatives all the way from 3 hours to 30 days, and adaptive rules that switch between a short
average and the deployed 5-day depending on the market.

  fixed      30d / 20d / 15d / 12d / 10d / 7d / 5d (deployed) / 3d / 2d / 1d / 12h / 6h / 3h
  adaptive   the other average while BTC's daily averages are stacked 7 > 15 > 30, the 5-day otherwise
  inverse    the other average while they are NOT stacked up, the 5-day in uptrends
  lots       SHARED (the dip redefined on the 3 deployed lots) or SEPARATE (the 5-day dip kept and the
             alternative run as an extra way in on 1-3 lots of its own)

Everything else stays deployed, including the 30-day filter, the +-0.2% zone and the 06-12 blocked window.
Averages carry no lookahead. Separate versions are judged against more shared lots AND 3 bigger lots.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_adaptive_average as aa
import eth_regime as rg
import btc_pullback as bp
import sol_wide_stop as w
import trx_adaptive_average as ta
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE, ALT = {"dip"}, {"alt dip"}
LENGTHS = [("30d", 30 * 1440), ("20d", 20 * 1440), ("15d", 15 * 1440), ("12d", 12 * 1440), ("10d", 10 * 1440),
           ("7d", 7 * 1440), ("5d (deployed)", 5 * 1440), ("3d", 3 * 1440), ("2d", 2 * 1440), ("1d", 1440),
           ("12h", 720), ("6h", 360), ("3h", 180)]
DEPLOYED = 5 * 1440
SIZES = [1, 2, 3]


def main() -> None:
    raw, bullish = bp.setup()
    rule = live.load_rule(bp.COIN)
    core = bp.dip_trades(raw, rule)
    daily = replay.daily_averages(raw)
    frame = grid.signal_frame(raw, daily, rule["minutes"])
    for period in (7, 15, 30):
        frame[period] = np.array([np.nan if v is None else float(v) for v in frame[period]])
    pd.set_option("display.width", 270)

    rebuilt = ta.entries_for(raw, rule, frame, aa.average_by_bar(raw, frame, DEPLOYED))
    deployed_entries = np.asarray([t["entry"] for t in core])
    print(f"deployed dip entries {len(deployed_entries)}; rebuilt with the 5-day average {len(rebuilt)}; "
          f"identical: {np.array_equal(deployed_entries, rebuilt)}")

    base = vf.score("BTC as deployed, 3 x $100", core, [(3, CORE)])
    controls = {"base": base}
    for n in (4, 5, 6):
        controls[f"{n} shared"] = vf.score(f"{n} x $100 shared (control)", core, [(n, CORE)])
        w.LOT = n * 100 / 3
        controls[f"3 bigger {n}"] = vf.score(f"3 x ${n * 100 / 3:.0f} (control)", core, [(3, CORE)])
        w.LOT = 100.0
    print("\n=== the controls")
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    bar_bullish = np.array([bool(v) for v in (frame[7] > frame[15]) & (frame[15] > frame[30])])
    long_average = aa.average_by_bar(raw, frame, DEPLOYED)
    built = {}
    for label, minutes in LENGTHS:
        short = aa.average_by_bar(raw, frame, minutes)
        built[f"fixed {label}"] = ta.entries_for(raw, rule, frame, short)
        if minutes != DEPLOYED:
            built[f"{label} in uptrends"] = ta.entries_for(raw, rule, frame, np.where(bar_bullish, short, long_average))
            built[f"{label} in chop"] = ta.entries_for(raw, rule, frame, np.where(bar_bullish, long_average, short))
    print(f"\n{len(built)} average rules")

    print("\n=== 1. SHARED: the dip entry redefined on BTC's 3 deployed lots (best 10 by walk-forward)")
    rows = [base] + [vf.score(label, bp.dip_trades(raw, rule, entries), [(3, CORE)])
                     for label, entries in built.items()]
    frame1 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame1.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame1.set_index("setup").tail(3).to_string())
    print(f"  beating the deployed 5-day: {int((frame1.walk_forward > base['walk_forward']).sum())}/{len(frame1) - 1}"
          f" on walk-forward, {int((frame1.profit > base['profit']).sum())}/{len(frame1) - 1} on the full window, "
          f"{int((frame1.unseen > base['unseen']).sum())}/{len(frame1) - 1} on the unseen holdout")

    print("\n=== 2. how often each average is touched, and in what market")
    counts = [{"average": label, "candidate entries": len(entries),
               "in an uptrend": f"{(bullish[entries].mean() * 100 if len(entries) else 0):.0f}%",
               "per month": round(len(entries) / 23, 1)}
              for label, entries in built.items() if label.startswith("fixed")]
    print(pd.DataFrame(counts).set_index("average").to_string())

    print("\n=== 3. SEPARATE: the 5-day dip stays, the alternative runs as an extra way in on its own lots")
    sleeves = {label: sorted(core + bp.dip_trades(raw, rule, entries, "alt dip"), key=lambda t: t["entry"])
               for label, entries in built.items() if label != "fixed 5d (deployed)"}
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
    shared_books = {label: bp.dip_trades(raw, rule, entries) for label, entries in built.items()}
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
