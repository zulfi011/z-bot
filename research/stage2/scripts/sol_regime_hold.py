"""Regime hold for SOL: buy when the daily averages stack 7d > 15d > 30d, and hold until the stack breaks.

No entry timing, no trail, no target - just "own SOL while the trend is officially up". SOL's averages come from
completed UTC days only and take effect the next day, so the stack is known before the minute it is acted on.

Every combination:
  enter    the minute after the stack first forms; optionally only if SOL is also above its 30-day average;
           optionally allowed to re-enter later in the same regime after being stopped out
  hold     until the minute after the stack breaks (7 > 15 > 30 no longer true), or the faster 7d < 15d, or
           until SOL closes below its 30-day average, whichever the variant says
  stop     none, or -4 / -6 / -8 / -12% from the fill
  lots     1, 2 or 3 lots per regime
  money    SHARED - the regime lots compete for SOL's deployed 3 core lots
           SEPARATE - the core carries on untouched and the regime holds 1-3 lots of its own

Judged with the corrected window engine: every lot is marked, and one still open when a window ends is closed at
that window's last price - which matters more here than anywhere, because these lots are held for weeks.
Drawdown is hourly mark to market.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import eth_regime as rg
import sol_pullback as sp
import sol_wide_stop as w
from sol_wide_stop import CORE, TRAINS, simulate

REGIME = {"regime"}
STOPS = [None, 4.0, 6.0, 8.0, 12.0]
COPIES = [1, 2, 3]
ENTERS = ["on the stack", "stack + above 30d"]
HOLDS = ["stack breaks", "7d < 15d", "close below 30d"]
REENTER = [False, True]


def daily_flags(raw: pd.DataFrame):
    """Per-minute booleans for the stack, the faster 7d<15d break, and price against the 30-day average."""
    day = raw.open_time.dt.floor("D")
    grouped = raw.groupby(day).agg(close=("close", "last"), n=("close", "size"))
    closes = grouped[grouped.n == 1440].close
    a7, a15, a30 = (closes.rolling(n).mean() for n in (7, 15, 30))
    frame = pd.DataFrame({"stacked": (a7 > a15) & (a15 > a30), "fast": a7 > a15, "avg30": a30}).dropna()
    frame.index = frame.index + pd.Timedelta(days=1)                     # effective the next UTC day
    stacked = day.map(frame.stacked).fillna(False).to_numpy(bool)
    fast = day.map(frame.fast).fillna(False).to_numpy(bool)
    average30 = day.map(frame.avg30).to_numpy(float)
    above30 = np.where(np.isfinite(average30), w.grid.CLOSE > average30, False)
    return stacked, fast, above30


def regime_trades(stacked, fast, above30, enter, hold, stop, copies, reenter):
    """One entry per regime (or per re-entry), sold the minute after the hold condition fails."""
    starts = np.flatnonzero(stacked[1:] & ~stacked[:-1]) + 1
    if stacked[0]:
        starts = np.r_[0, starts]
    holding = {"stack breaks": stacked, "7d < 15d": fast, "close below 30d": above30}[hold]
    last = len(w.grid.OPEN) - 1
    trades, info = [], []
    for start in starts:
        ends = np.flatnonzero(~holding[start + 1:])
        finish = start + 1 + int(ends[0]) if len(ends) else last        # the minute the hold condition fails
        entry = start + 1
        while entry < min(finish, last):
            if enter == "stack + above 30d":
                ready = np.flatnonzero(above30[entry:finish])
                if not len(ready):
                    break
                entry += int(ready[0])
            exit_at, price = min(finish + 1, last), float(w.grid.OPEN[min(finish + 1, last)])
            fill = w.grid.OPEN[entry] * (1 + w.grid.SLIP)
            if stop is not None:
                level = fill * (1 - stop / 100)
                hit = np.flatnonzero(w.grid.LOW[entry:exit_at] <= level)
                if len(hit):
                    exit_at = entry + int(hit[0])
                    price = min(level, float(w.grid.OPEN[exit_at]))
            info.append({"start": w.grid.TIMES[entry], "days": (exit_at - entry) / 1440,
                         "move%": 100 * (price / fill - 1)})
            trades += [{"entry": int(entry), "exit": int(exit_at), "price": price, "source": "regime",
                        "why": 5}] * copies
            if not (reenter and stop is not None and exit_at < finish):
                break
            entry = exit_at + 1                                          # stopped out, the regime is still on
    return trades, pd.DataFrame(info)


def name_of(key):
    enter, hold, stop, reenter = key
    return (f"{enter}, hold till {hold}, {'no stop' if stop is None else f'stop -{stop:g}%'}"
            f"{', re-enter' if reenter else ''}")


def main() -> None:
    raw, bullish, ema = sp.setup()
    rule, dips, breaks = w.signals(raw)
    core = w.core_trades(rule, dips, breaks, bullish, ema)
    stacked, fast, above30 = daily_flags(raw)
    pd.set_option("display.width", 265)

    print("=== 0. what SOL's regimes look like (pure hold, no stop, inside the full window)")
    _, info = regime_trades(stacked, fast, above30, "on the stack", "stack breaks", None, 1, False)
    inside = info[(info.start >= research.WINDOWS["full"][0]) & (info.start < research.WINDOWS["full"][1])]
    print(f"  {len(inside)} regimes, held {inside.days.mean():.1f} days on average (median "
          f"{inside.days.median():.1f}), {100 * (inside['move%'] > 0).mean():.0f}% of them ended higher")
    print(inside.assign(start=inside.start.dt.date).round(2).to_string(index=False))

    base = w.score("SOL as deployed, 3 x $100", core, [(3, CORE)])
    controls = {n: w.score(f"flat core {n} (control)", core, [(n, CORE)]) for n in (4, 5, 6)}
    print("\n=== the controls")
    print(pd.DataFrame([base, *controls.values()]).set_index("setup").to_string())

    keys = [(e, h, s, r) for e in ENTERS for h in HOLDS for s in STOPS for r in REENTER
            if not (r and s is None)]
    sets = {key: regime_trades(stacked, fast, above30, key[0], key[1], key[2], 1, key[3])[0] for key in keys}
    print(f"\n{len(sets)} regime rules x {len(COPIES)} lot counts")

    print("\n=== 1. regime hold ALONE, on its own lots (best 10 by walk-forward)")
    rows = []
    for key, trades in sets.items():
        for k in COPIES:
            copied = [t for t in trades for _ in range(k)]
            rows.append(w.score(f"{name_of(key)} — {k} x $100 alone", copied, [(k, REGIME)]))
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())

    print("\n=== 2. SHARED: the regime competes for SOL's 3 deployed lots")
    rows = [base]
    for key, trades in sets.items():
        rows.append(w.score(f"{name_of(key)} — shares the 3 lots",
                            sorted(core + trades, key=lambda t: t["entry"]), [(3, CORE | REGIME)]))
    frame2 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame2.set_index("setup").head(8).to_string())
    print(f"  beating no regime: {int((frame2.walk_forward > base['walk_forward']).sum())}/{len(frame2) - 1} on "
          f"walk-forward, {int((frame2.profit > base['profit']).sum())}/{len(frame2) - 1} on the full window")

    print("\n=== 3. SEPARATE: the core carries on, the regime holds lots of its own")
    rows = [base]
    for k in COPIES:
        rows.append(controls[3 + k])
        for key, trades in sets.items():
            copied = [t for t in trades for _ in range(k)]
            rows.append(w.score(f"{name_of(key)} — own {k}",
                                sorted(core + copied, key=lambda t: t["entry"]), [(3, CORE), (k, REGIME)]))
    frame3 = pd.DataFrame(rows)
    for k in COPIES:
        part = frame3[frame3.setup.str.endswith(f"own {k}")].sort_values("walk_forward", ascending=False)
        control = controls[3 + k]
        print(f"\n  --- own {k} (${(3 + k) * 100}) against flat core {3 + k} "
              f"(+${control['walk_forward']:.2f}, {control['windows']}, {control['mtm_dd%']}%)")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating that control: {int((part.walk_forward > control['walk_forward']).sum())}/{len(part)} "
              f"on walk-forward, {int((part['mtm_dd%'] > control['mtm_dd%']).sum())}/{len(part)} on drawdown")

    print("\n=== 4. the honest test: the regime rule is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for label, pots, control_pots, copies in (("shared, 3 lots", [(3, CORE | REGIME)], [(3, CORE)], 1),
                                              ("own 1", [(3, CORE), (1, REGIME)], [(4, CORE)], 1),
                                              ("own 2", [(3, CORE), (2, REGIME)], [(5, CORE)], 2),
                                              ("own 3", [(3, CORE), (3, REGIME)], [(6, CORE)], 3)):
        control_w = {x: simulate(core, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        scores = {}
        for key, trades in sets.items():
            copied = [t for t in trades for _ in range(copies)]
            book = sorted(core + copied, key=lambda t: t["entry"])
            scores[key] = {x: simulate(book, pots, *research.WINDOWS[x])["profit"] for x in windows}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(sets, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        pure = ("on the stack", "stack breaks", None, False)
        print(f"\n  --- {label}")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    plain regime hold, no choice at all: "
              f"${sum(scores[pure][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[pure][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")
        print(f"    best fixed rule in hindsight {name_of(best)}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}")


if __name__ == "__main__":
    main()
