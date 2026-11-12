"""ETH Mode A, with a gap above the line and an earlier arm - can a lot be stopped from finishing negative?

The complaint this answers: a Mode A lot armed at +1.315%, never pulled away from the 16-hour line, and a small
dip closed below it, so the lot exited at -$0.36. The idea being tested has three parts, all aimed at never
letting an armed lot finish under water:

  arm     the lot starts tracking the line as soon as it has covered its own costs (+0.19% = 7.5bps fee and
          2bps slippage, both sides) rather than waiting for +1.315%
  gap     it sells when a minute CLOSES at or below the line plus a gap, rather than waiting for a close below
          the line itself - so the exit happens on the way down to the line, not after it
  floor   once armed, the protective stop is lifted to the fill plus costs, so an armed lot cannot come back
          and finish negative

Every combination, on ETH as deployed otherwise (dip + Mode C + pullback, 3 and 5 shared lots, BNB fees, the
live buying rule, the corrected window engine):

  line    1 / 2 / 3 / 4 / 6 / 8 / 12 hours, and the deployed 16 for reference
  arm     +1.315% (deployed) or +0.19% (costs only)
  gap     none (deployed) / +0.19% / +0.4% above the line
  floor   none (deployed) / fill + 0.19%

Mode B lots - the ones opened outside a clean uptrend - are left exactly as they are in every variant.
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
COSTS = 0.19                      # 7.5bps fee + 2bps slippage, both sides
HOURS = [1, 2, 3, 4, 6, 8, 12, 16]
ARMS = [("deployed +1.315%", None), ("costs +0.19%", COSTS)]
GAPS = [("no gap", 0.0), ("gap +0.19%", COSTS), ("gap +0.4%", 0.4)]
FLOORS = [("no floor", None), ("floor +0.19%", COSTS)]


def mode_a(entry, arm, stop_pct, line, gap, floor):
    """One Mode A lot under one set of rules. Returns (exit index, price, why)."""
    last = len(grid.OPEN) - 1
    fill = grid.OPEN[entry] * (1 + grid.SLIP)
    stop = fill * (1 - stop_pct / 100)
    armed = research.first_hit(entry, fill * (1 + arm / 100), True)
    stopped = research.first_hit(entry, stop, False, None if armed < 0 else armed)
    if stopped >= 0 and (armed < 0 or stopped <= armed):
        return stopped, min(stop, float(grid.OPEN[stopped])), 2
    if armed < 0:
        return last, float(grid.CLOSE[last]), 3                 # never armed and never stopped: still open
    level = stop if floor is None else max(stop, fill * (1 + floor / 100))
    low, close, above = grid.LOW[armed + 1:], grid.CLOSE[armed + 1:], line[armed + 1:] * (1 + gap / 100)
    hit = np.flatnonzero(low <= level)
    lost = np.flatnonzero(close <= above)
    first_hit_i = armed + 1 + int(hit[0]) if len(hit) else last + 1
    first_lost = armed + 1 + int(lost[0]) if len(lost) else last + 1
    if first_hit_i <= first_lost:
        return ((first_hit_i, min(level, float(grid.OPEN[first_hit_i])), 2) if first_hit_i <= last
                else (last, float(grid.CLOSE[last]), 3))
    out = min(first_lost + 1, last)
    return out, float(grid.OPEN[out]), 1


def book(raw, bullish, rule, line, arm_override, gap, floor):
    """ETH's three ways in. Mode A lots follow the rules under test; Mode B lots are untouched."""
    trades = []
    sources = ((live.live_entries(raw, rule), "dip", tm.DIP_STOP, rule["activation_pct"], rule["giveback_pct"]),
               ([t["entry"] for t in cmp.mode_c(raw, rule, 120, 12, 2.5, 30, 1.283, 22.0, 3.5)],
                "breakout", 3.5, 1.283, 22.0),
               (pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES, blocked=rule["blocked"]),
                "pullback", tm.DIP_STOP, rule["activation_pct"], rule["giveback_pct"]))
    for entries, source, stop, arm, give in sources:
        for entry in entries:
            entry = int(entry)
            if bullish[entry]:
                exit_at, price, why = mode_a(entry, arm if arm_override is None else arm_override,
                                             stop, line, gap, floor)
            else:
                exit_at, price, why = w.resolve(entry, arm, give, stop, None)
            trades.append({"entry": entry, "exit": exit_at, "price": price, "source": source, "why": why})
    return sorted(trades, key=lambda t: t["entry"])


def main() -> None:
    raw, bullish = cmp.load("ETHUSDT")
    rule = live.load_rule("eth")
    lines = {h: pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy() for h in HOURS}
    pd.set_option("display.width", 250)

    deployed = book(raw, bullish, rule, lines[16], None, 0.0, None)
    base = {lots: vf.score(f"DEPLOYED 16h line — {lots} x $100", deployed, [(lots, CORE)]) for lots in (3, 5)}
    print("=== the control (as live today)")
    print(pd.DataFrame(base.values()).set_index("setup").to_string())

    rows, books = [], {}
    for hours in HOURS:
        for arm_label, arm in ARMS:
            for gap_label, gap in GAPS:
                for floor_label, floor in FLOORS:
                    key = (hours, arm_label, gap_label, floor_label)
                    trades = book(raw, bullish, rule, lines[hours], arm, gap, floor)
                    books[key] = trades
                    for lots in (3, 5):
                        r = vf.score(f"{hours}h, {arm_label}, {gap_label}, {floor_label} — {lots} x $100",
                                     trades, [(lots, CORE)])
                        led = simulate(trades, [(lots, CORE)], *research.WINDOWS["full"])["ledger"]
                        rows.append({**r, "lots": lots, "hours": hours, "arm": arm_label, "gap": gap_label,
                                     "floor": floor_label,
                                     "losers": int((led.pnl <= 0).sum()) if len(led) else 0,
                                     "best": round(led.pnl.max(), 2) if len(led) else 0.0,
                                     "avg win": round(led[led.pnl > 0].pnl.mean(), 2) if len(led) else 0.0,
                                     "avg loss": round(led[led.pnl <= 0].pnl.mean(), 2) if len(led) else 0.0})
    frame = pd.DataFrame(rows)
    show = ["trades", "win%", "losers", "avg win", "avg loss", "best", "profit", "walk_forward", "windows",
            "mtm_dd%"]

    for lots in (3, 5):
        part = frame[frame.lots == lots].sort_values("walk_forward", ascending=False)
        print(f"\n=== best 10 of {len(part)} at {lots} x $100 (control: ${base[lots]['walk_forward']:.2f}, "
              f"{base[lots]['win%']}% win, {base[lots]['mtm_dd%']}%)")
        print(part.set_index("setup").head(10)[show].to_string())
        print(f"  beating the control on walk-forward: {int((part.walk_forward > base[lots]['walk_forward']).sum())}"
              f"/{len(part)}; on win rate: {int((part['win%'] > base[lots]['win%']).sum())}/{len(part)}")

    print("\n=== does the line length matter? (arm deployed, no gap, no floor - just the line)")
    plain = frame[(frame.arm == "deployed +1.315%") & (frame.gap == "no gap") & (frame.floor == "no floor")]
    print(plain.pivot_table(index="hours", columns="lots", values="walk_forward").round(2).to_string())

    print("\n=== the three parts, one at a time, on the deployed 16-hour line")
    for lots in (3, 5):
        part = frame[(frame.lots == lots) & (frame.hours == 16)].sort_values("walk_forward", ascending=False)
        print(f"\n  --- {lots} x $100")
        print(part.set_index("setup")[show].to_string())

    print("\n=== the honest test: the whole rule is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for lots in (3, 5):
        control = {x: simulate(deployed, [(lots, CORE)], *research.WINDOWS[x])["profit"] for x in windows}
        scores = {k: {x: simulate(v, [(lots, CORE)], *research.WINDOWS[x])["profit"] for x in windows}
                  for k, v in books.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]]) for i in range(6)]
        chosen = sum(scores[p][t] for p, t in zip(picks, rg.TESTS))
        best = max(scores, key=lambda k: sum(scores[k][t] for t in rg.TESTS))
        print(f"\n  --- {lots} x $100")
        print(f"    choosing each window ${chosen:8.2f} against ${sum(control[t] for t in rg.TESTS):8.2f} deployed")
        print(f"    best fixed rule in hindsight {best}: ${sum(scores[best][t] for t in rg.TESTS):8.2f}, "
              f"window by window {', '.join(f'{scores[best][t] - control[t]:+.2f}' for t in rg.TESTS)}")
        keep = (16, "deployed +1.315%", "gap +0.19%", "floor +0.19%")
        print(f"    the idea as asked for {keep}: "
              f"${sum(scores[keep][t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[keep][t] - control[t]:+.2f}' for t in rg.TESTS)}")


if __name__ == "__main__":
    main()
