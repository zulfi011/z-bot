"""Does SOL's dip entry do better with a different average - or a FASTER one while the market is trending up?

SOL buys a touch of its 12-day average from below. In an uptrend price runs away from a 12-day average and the
entry waits for weeks; in a chop a shorter average would trade far more often. This tries:

  fixed      30d, 20d, 15d, 12d (deployed), 10d, 7d, 5d, 3d, 2d, 1d, 12h, 6h, 3h - a straight swap
  adaptive   the short average while SOL's daily averages are stacked 7 > 15 > 30, the 12-day otherwise
  inverse    the short average while they are NOT stacked up, the 12-day in uptrends (the opposite bet)
  patient    the LONG average (20d / 30d) in uptrends, the 12-day otherwise

and each of those two ways:

  SHARED     SOL's 3 deployed lots use the new average - the dip entry is simply redefined
  SEPARATE   the core keeps its 12-day dip and Mode C untouched, and a sleeve of 1-3 lots of its own trades the
             alternative average as an extra way in, so both run side by side out of one wallet

Averages, both without lookahead: N days from completed UTC daily closes effective the next day (the deployed
definition - 12d here must reproduce live exactly), N hours as the mean of the last N hours of 1-minute closes
as of the minute before the signal candle opens. Everything else is SOL as deployed: 3-minute signal candles,
+-0.5% zone touched from below, a green candle within 30 minutes, no entries 06:00-12:00 UTC, no entries in a
stacked downtrend, stop -2%, trail +1.251% / 12%, Mode A on the 8-hour line when bought in an uptrend.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_regime as rg
import eth_adaptive_average as aa
import sol_pullback as sp
import sol_wide_stop as w
from sol_wide_stop import CORE, TRAINS, simulate

ALT = {"alt dip"}
LENGTHS = [("30d", 30 * 1440), ("20d", 20 * 1440), ("15d", 15 * 1440), ("12d (deployed)", 12 * 1440),
           ("10d", 10 * 1440), ("7d", 7 * 1440), ("5d", 5 * 1440), ("3d", 3 * 1440), ("2d", 2 * 1440),
           ("1d", 1440), ("12h", 720), ("6h", 360), ("3h", 180)]
DEPLOYED = 12 * 1440
SIZES = [1, 2, 3]


def dip_trades(entries, bullish, ema, rule, source="dip"):
    out = []
    for entry in entries:
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"],
                                        ema if bullish[entry] else None)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": source, "why": why})
    return out


def main() -> None:
    raw, bullish, ema = sp.setup()
    rule, dips, breaks = w.signals(raw)
    daily = replay.daily_averages(raw)
    frame = grid.signal_frame(raw, daily, rule["minutes"])
    for period in (7, 15, 30):
        frame[period] = np.array([np.nan if v is None else float(v) for v in frame[period]])
    pd.set_option("display.width", 265)

    deployed = np.asarray(dips)
    rebuilt = aa.entries_for(raw, rule, frame, aa.average_by_bar(raw, frame, DEPLOYED))
    print(f"deployed dip entries {len(deployed)}; rebuilt with the 12-day average {len(rebuilt)}; "
          f"identical: {np.array_equal(deployed, rebuilt)}")

    mode_c = [t for t in w.core_trades(rule, [], breaks, bullish, ema)]
    core = sorted(dip_trades(deployed, bullish, ema, rule) + mode_c, key=lambda t: t["entry"])
    base = w.score("SOL as deployed, 3 x $100", core, [(3, CORE)])
    controls = {n: w.score(f"flat core {n} (control)", core, [(n, CORE)]) for n in (4, 5, 6)}
    print("\n=== the controls")
    print(pd.DataFrame([base, *controls.values()]).set_index("setup").to_string())

    bar_bullish = np.array([bool(v) for v in (frame[7] > frame[15]) & (frame[15] > frame[30])])
    long_average = aa.average_by_bar(raw, frame, DEPLOYED)
    built = {}
    for label, minutes in LENGTHS:
        short = aa.average_by_bar(raw, frame, minutes)
        built[f"fixed {label}"] = aa.entries_for(raw, rule, frame, short)
        if minutes != DEPLOYED:
            built[f"{label} in uptrends"] = aa.entries_for(raw, rule, frame, np.where(bar_bullish, short, long_average))
            built[f"{label} in chop"] = aa.entries_for(raw, rule, frame, np.where(bar_bullish, long_average, short))
    print(f"\n{len(built)} average rules")

    print("\n=== 1. SHARED: the dip entry is redefined, on SOL's 3 deployed lots (with Mode C unchanged)")
    rows = [base]
    for label, entries in built.items():
        book = sorted(dip_trades(entries, bullish, ema, rule) + mode_c, key=lambda t: t["entry"])
        rows.append(w.score(label, book, [(3, CORE)]))
    frame1 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame1.set_index("setup").head(12).to_string())
    print("  worst three:"); print(frame1.set_index("setup").tail(3).to_string())
    print(f"  averages beating the deployed 12-day: "
          f"{int((frame1.walk_forward > base['walk_forward']).sum())}/{len(frame1) - 1} on walk-forward, "
          f"{int((frame1.profit > base['profit']).sum())}/{len(frame1) - 1} on the full window")

    print("\n=== 2. how often each average is touched, and in what market")
    counts = []
    for label, entries in built.items():
        if not label.startswith("fixed"):
            continue
        counts.append({"average": label, "candidate entries": len(entries),
                       "in an uptrend": f"{(bullish[entries].mean() * 100 if len(entries) else 0):.0f}%",
                       "per month": round(len(entries) / 23, 1)})
    print(pd.DataFrame(counts).set_index("average").to_string())

    print("\n=== 3. SEPARATE: the core keeps its 12-day dip, a sleeve trades the other average as an extra way in")
    sleeves = {label: sorted(core + dip_trades(entries, bullish, ema, rule, "alt dip"), key=lambda t: t["entry"])
               for label, entries in built.items() if label != "fixed 12d (deployed)"}
    for size in SIZES:
        control = controls[3 + size]
        rows = [w.score(label, book, [(3, CORE), (size, ALT)]) for label, book in sleeves.items()]
        part = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
        print(f"\n  --- own {size} (${(3 + size) * 100}) against flat core {3 + size} "
              f"(+${control['walk_forward']:.2f}, {control['windows']}, {control['mtm_dd%']}%)")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating that control: {int((part.walk_forward > control['walk_forward']).sum())}/{len(part)} "
              f"on walk-forward, {int((part['mtm_dd%'] > control['mtm_dd%']).sum())}/{len(part)} on drawdown")

    print("\n=== 4. the honest test: the average is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    shared_books = {label: sorted(dip_trades(entries, bullish, ema, rule) + mode_c, key=lambda t: t["entry"])
                    for label, entries in built.items()}
    for label, books, pots, control_pots in (("shared, 3 lots", shared_books, [(3, CORE)], [(3, CORE)]),
                                             ("sleeve of 1", sleeves, [(3, CORE), (1, ALT)], [(4, CORE)]),
                                             ("sleeve of 2", sleeves, [(3, CORE), (2, ALT)], [(5, CORE)]),
                                             ("sleeve of 3", sleeves, [(3, CORE), (3, ALT)], [(6, CORE)])):
        control_w = {x: simulate(core, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        scores = {name: {x: simulate(book, pots, *research.WINDOWS[x])["profit"] for x in windows}
                  for name, book in books.items()}
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
