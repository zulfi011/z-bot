"""ETH Mode A: what should switch the line on? Every alternative to borrowing Mode B's +1.315% trail arm.

The complaint this answers, in the owner's words: Mode A exits on the 16-hour line, so why does it wait for
+1.315% - a number tuned for Mode B's giveback trail - before it starts watching that line at all? If the line
is the exit, the trigger should be something the line cares about.

Every trigger, on ETH as deployed otherwise (dip + Mode C + pullback, one shared pool of 3 and 5 x $100, BNB
fees, the live buying rule, the break-even floor now live, the corrected window engine):

  immediate     the line is watched from the buy minute - no arm at all
  profit p%     the deployed idea, swept: 0.19 (costs) / 0.4 / 0.6 / 0.8 / 1.0 / 1.315 (deployed) / 1.6 / 2.0
                / 2.5 / 3.0 / 4.0 / 5.0
  time h        held h hours, at any price: 1 / 2 / 4 / 8 / 12 / 24 / 48 / 72 / 120
  line +g%      the first minute the lot CLOSES above the 16-hour line (plus 0 / 0.25 / 0.5 / 1.0%) - the
                structural trigger: a lot that has never been above the line has no business being sold by it
  p or h        whichever comes first - profit if it runs, time if it stalls
  p and h       both - profit that has also been held a while
  p or line     / p and line - the same two ways with the structural trigger

Mode B lots (opened outside a clean uptrend) are untouched in every variant. The protective -4.5% stop and the
break-even floor are untouched too: the floor lifts the stop to fill + 0.19% the first time the lot trades
there, exactly as the live bot does, independently of when the line switches on.

Judged the honest way: the rule is chosen on the six months before each test window and never with hindsight.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import eth_pullback as pb
import eth_regime as rg
import three_modes as tm
import all_coins_compare as cmp
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE = {"dip", "breakout", "pullback"}
COSTS = 0.19                       # 7.5bps fee + 2bps slippage, both sides - the break-even floor
DEPLOYED_ARM = 1.315
PROFITS = [COSTS, 0.4, 0.6, 0.8, 1.0, DEPLOYED_ARM, 1.6, 2.0, 2.5, 3.0, 4.0, 5.0]
TIMES_H = [1, 2, 4, 8, 12, 24, 48, 72, 120]
GAPS = [0.0, 0.25, 0.5, 1.0]
MIX_P, MIX_H, MIX_G = [COSTS, 0.6, DEPLOYED_ARM, 2.0], [4, 8, 24, 48], [0.0, 0.5]
LINES = [8, 12, 16, 24]


def triggers():
    """Every way of switching the line on, as (label, family, spec)."""
    out = [("immediate (no arm)", "immediate", None)]
    out += [(f"profit +{p}%" + (" (deployed)" if p == DEPLOYED_ARM else ""), "profit", p) for p in PROFITS]
    out += [(f"held {h}h", "time", h) for h in TIMES_H]
    out += [(f"close above line" + (f" +{g}%" if g else ""), "line", g) for g in GAPS]
    out += [(f"profit +{p}% or held {h}h", "or-time", (p, h)) for p in MIX_P for h in MIX_H]
    out += [(f"profit +{p}% and held {h}h", "and-time", (p, h)) for p in MIX_P for h in MIX_H]
    out += [(f"profit +{p}% or above line" + (f" +{g}%" if g else ""), "or-line", (p, g))
            for p in MIX_P for g in MIX_G]
    out += [(f"profit +{p}% and above line" + (f" +{g}%" if g else ""), "and-line", (p, g))
            for p in MIX_P for g in MIX_G]
    return out


def arm_minute(entry, fill, family, spec, line, last):
    """The first minute the lot starts being held against the line, or -1 if that never happens."""
    def by_profit(p):
        return entry if p <= 0 else research.first_hit(entry, fill * (1 + p / 100), True)

    def by_time(h):
        at = entry + h * 60
        return at if at <= last else -1

    def by_line(g):
        above = np.flatnonzero(grid.CLOSE[entry:] >= line[entry:] * (1 + g / 100))
        return entry + int(above[0]) if len(above) else -1

    if family == "immediate":
        return entry
    if family == "profit":
        return by_profit(spec)
    if family == "time":
        return by_time(spec)
    if family == "line":
        return by_line(spec)
    first, second = ((by_profit(spec[0]), by_time(spec[1])) if family.endswith("time")
                     else (by_profit(spec[0]), by_line(spec[1])))
    if family.startswith("or"):
        live_ones = [x for x in (first, second) if x >= 0]
        return min(live_ones) if live_ones else -1
    return max(first, second) if first >= 0 and second >= 0 else -1


def mode_a(entry, family, spec, stop_pct, line, floor=COSTS):
    """One Mode A lot. The floor lifts the stop the first time the lot trades at fill + costs, whenever the
    line is switched on; the line sells it on the first close at or below the line."""
    last = len(grid.OPEN) - 1
    fill = grid.OPEN[entry] * (1 + grid.SLIP)
    stop = fill * (1 - stop_pct / 100)
    armed = arm_minute(entry, fill, family, spec, line, last)
    stopped = research.first_hit(entry, stop, False, None if armed < 0 else armed)
    if stopped >= 0 and (armed < 0 or stopped < armed):
        return stopped, min(stop, float(grid.OPEN[stopped])), 2
    if armed < 0:
        return last, float(grid.CLOSE[last]), 3                    # never armed, never stopped: still open
    start = armed + 1
    if start > last:
        return last, float(grid.CLOSE[last]), 3
    level = np.full(last + 1 - start, stop)
    if floor is not None:
        floor_price = fill * (1 + floor / 100)
        floor_at = research.first_hit(entry, floor_price, True)
        if floor_at >= 0:
            level[max(floor_at, start) - start:] = max(stop, floor_price)
    hit = np.flatnonzero(grid.LOW[start:] <= level)
    lost = np.flatnonzero(grid.CLOSE[start:] <= line[start:])
    first_hit_i = start + int(hit[0]) if len(hit) else last + 1
    first_lost = start + int(lost[0]) if len(lost) else last + 1
    if first_hit_i <= first_lost:
        return ((first_hit_i, min(float(level[first_hit_i - start]), float(grid.OPEN[first_hit_i])), 2)
                if first_hit_i <= last else (last, float(grid.CLOSE[last]), 3))
    out = min(first_lost + 1, last)
    return out, float(grid.OPEN[out]), 1


def book(sources, bullish, line, family, spec):
    """ETH's three ways in. Mode A lots use the trigger under test; Mode B lots are untouched."""
    trades = []
    for entries, source, stop, arm, give in sources:
        for entry in entries:
            entry = int(entry)
            if bullish[entry]:
                exit_at, price, why = mode_a(entry, family, spec, stop, line)
            else:
                exit_at, price, why = w.resolve(entry, arm, give, stop, None)
            trades.append({"entry": entry, "exit": exit_at, "price": price, "source": source, "why": why})
    return sorted(trades, key=lambda t: t["entry"])


def detail(trades, pots):
    led = simulate(trades, pots, *research.WINDOWS["full"])["ledger"]
    if not len(led):
        return {}
    return {"losers": int((led.pnl <= 0).sum()), "avg win": round(led[led.pnl > 0].pnl.mean(), 2),
            "avg loss": round(led[led.pnl <= 0].pnl.mean(), 2),
            "median hours": round(float((led.exit - led.entry).median()) / 60, 1)}


def main() -> None:
    raw, bullish = cmp.load("ETHUSDT")
    rule = live.load_rule("eth")
    sources = ((live.live_entries(raw, rule), "dip", tm.DIP_STOP, rule["activation_pct"], rule["giveback_pct"]),
               ([t["entry"] for t in cmp.mode_c(raw, rule, 120, 12, 2.5, 30, 1.283, 22.0, 3.5)],
                "breakout", 3.5, 1.283, 22.0),
               (pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES, blocked=rule["blocked"]),
                "pullback", tm.DIP_STOP, rule["activation_pct"], rule["giveback_pct"]))
    lines = {h: pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy() for h in LINES}
    pd.set_option("display.width", 260)

    deployed = book(sources, bullish, lines[16], "profit", DEPLOYED_ARM)
    base = {lots: {**vf.score(f"DEPLOYED: 16h line, arm +1.315%, floor on — {lots} x $100", deployed,
                              [(lots, CORE)]), **detail(deployed, [(lots, CORE)])} for lots in (3, 5)}
    print("=== the control (ETH as it stands today, floor included)")
    print(pd.DataFrame(base.values()).set_index("setup").to_string())

    rows, books = [], {}
    for label, family, spec in triggers():
        trades = book(sources, bullish, lines[16], family, spec)
        books[(16, label)] = trades
        for lots in (3, 5):
            pots = [(lots, CORE)]
            rows.append({**vf.score(f"{label} — {lots} x $100", trades, pots), **detail(trades, pots),
                         "lots": lots, "family": family, "trigger": label, "line": 16})
    frame = pd.DataFrame(rows)
    show = ["trades", "win%", "losers", "avg win", "avg loss", "median hours", "profit", "walk_forward",
            "windows", "unseen", "mtm_dd%"]

    for lots in (3, 5):
        part = frame[frame.lots == lots].sort_values("walk_forward", ascending=False)
        b = base[lots]
        print(f"\n=== all {len(part)} triggers at {lots} x $100, best first "
              f"(control: ${b['walk_forward']:.2f} walk-forward, {b['win%']}% win, {b['mtm_dd%']}% drawdown)")
        print(part.set_index("setup")[show].to_string())
        print(f"  beating the control on walk-forward: {int((part.walk_forward > b['walk_forward']).sum())}"
              f"/{len(part)}; on full-history profit: {int((part.profit > b['profit']).sum())}/{len(part)}; "
              f"on win rate: {int((part['win%'] > b['win%']).sum())}/{len(part)}")

    print("\n=== family by family (5 x $100, walk-forward)")
    print(frame[frame.lots == 5].groupby("family").walk_forward.agg(["count", "min", "median", "max"])
          .round(2).to_string())

    print("\n=== does the profit arm matter at all? (5 x $100)")
    sweep = frame[(frame.lots == 5) & (frame.family.isin(("profit", "immediate")))]
    print(sweep.set_index("trigger")[["win%", "losers", "avg win", "avg loss", "profit", "walk_forward",
                                      "windows", "mtm_dd%"]].to_string())

    print("\n=== the top triggers against other line lengths (5 x $100, walk-forward)")
    tops = [t for t in triggers()
            if t[0] in list(frame[frame.lots == 5].sort_values("walk_forward", ascending=False).trigger[:6])
            or t[2] == DEPLOYED_ARM]
    cross = []
    for hours in LINES:
        for label, family, spec in tops:
            trades = books.get((hours, label)) or book(sources, bullish, lines[hours], family, spec)
            books[(hours, label)] = trades
            r = vf.score(f"{label} on the {hours}h line", trades, [(5, CORE)])
            cross.append({"trigger": label, "line": hours, "walk_forward": r["walk_forward"],
                          "win%": r["win%"], "profit": r["profit"]})
    print(pd.DataFrame(cross).pivot_table(index="trigger", columns="line", values="walk_forward")
          .round(2).to_string())

    print("\n=== the honest test: the trigger is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for lots in (3, 5):
        control = {x: simulate(deployed, [(lots, CORE)], *research.WINDOWS[x])["profit"] for x in windows}
        scores = {k: {x: simulate(v, [(lots, CORE)], *research.WINDOWS[x])["profit"] for x in windows}
                  for k, v in books.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]]) for i in range(6)]
        chosen = sum(scores[p][t] for p, t in zip(picks, rg.TESTS))
        live_sum = sum(control[t] for t in rg.TESTS)
        best = max(scores, key=lambda k: sum(scores[k][t] for t in rg.TESTS))
        print(f"\n  --- {lots} x $100")
        print(f"    choosing honestly ${chosen:8.2f} against ${live_sum:8.2f} deployed "
              f"({chosen - live_sum:+.2f})")
        print(f"    what it picked: {[p[1] for p in picks]}")
        print(f"    best in hindsight {best}: ${sum(scores[best][t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control[t]:+.2f}' for t in rg.TESTS)}")
        for key in [(16, "immediate (no arm)"), (16, "close above line"), (16, "held 8h"), (16, "held 24h"),
                    (16, "profit +0.19% or held 24h")]:
            diffs = [scores[key][t] - control[t] for t in rg.TESTS]
            print(f"    {key[1]:<32} ${sum(scores[key][t] for t in rg.TESTS):8.2f} "
                  f"({sum(d > 0 for d in diffs)}/6 windows: "
                  f"{', '.join(f'{d:+.2f}' for d in diffs)})")


if __name__ == "__main__":
    main()
