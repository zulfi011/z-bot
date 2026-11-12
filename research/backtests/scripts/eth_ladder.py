"""ETH dip ladder: buy the dislocation itself, in steps, below the 7-day average.

  average   the core's own 7-day average (completed UTC days, effective the next day)
  rungs     one lot each time a 1-minute close first reaches -a%, -b%, -c% below the average;
            buy at the next minute's open. Each rung fires once per dip.
  reset     a dip ends when a close gets back to the average; only then can the rungs fire again
  exits     "average"  every rung lot sells at the next minute's open after the close is back at the average -
                       the reversion the ladder is betting on - with a hard ladder stop S% below the average
                       measured when the first rung filled (S = 15 or 20)
            "dip"      each rung lot takes the deployed dip exit from its own fill (-4.5% stop, trail)

No downtrend filter: deep dips happen when the averages are stacked downward, which is the point.
Measured beside the plan (core 5 + pullback 2): one shared wallet, hourly mark-to-market drawdown - essential here,
because a ladder can sit underwater for weeks before it is sold.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_pullback as pb
import eth_catchup as cu

LOT, FEE = 100.0, 7.5 / 10_000
TESTS, TRAINS = cu.TESTS, cu.TRAINS
CORE, PULL, LAD = {"dip", "breakout"}, {"pullback"}, {"ladder"}
PRIORITY = {"dip": 0, "breakout": 0, "pullback": 1, "ladder": 2}
RUNGS = [(4.0, 7.0, 10.0), (5.0, 8.0, 11.0), (6.0, 9.0, 12.0)]
EXITS = [("average", 15.0), ("average", 20.0), ("dip", None)]


def average_7d(raw):
    table = replay.daily_average_n(raw, 7)
    day = raw.open_time.dt.floor("D")
    return day.map({d: float(v) for d, v in table.items() if v is not None}).to_numpy(float)


def dips(avg):
    """(start, end) minute ranges where the close is below the 7-day average; end = first close back at it."""
    below = np.isfinite(avg) & (grid.CLOSE < avg)
    change = np.flatnonzero(np.diff(below.astype(np.int8))) + 1
    starts = change[below[change]]
    ends = change[~below[change]]
    runs = []
    for s in starts:
        later = ends[ends > s]
        runs.append((int(s), int(later[0]) if len(later) else -1))
    return runs


def build(avg, runs, bullish, ema, rungs, exit_style, stop):
    rule = live.load_rule("eth")
    dev = grid.CLOSE / avg - 1
    trades = []
    for start, end in runs:
        stop_level = None
        for rung in rungs:
            hit = np.flatnonzero(dev[start:end if end > 0 else len(dev)] <= -rung / 100)
            if not len(hit):
                break                                            # deeper rungs need this one first
            entry = start + int(hit[0]) + 1
            if entry >= len(grid.OPEN) - 1 or (end > 0 and entry > end):
                break
            if exit_style == "dip":
                line = ema if bullish[entry] else None
                out, price, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], 4.5, line)
            else:
                if stop_level is None:                           # fixed when the first rung fills
                    stop_level = avg[entry] * (1 - stop / 100)
                out = end + 1 if end > 0 and end + 1 < len(grid.OPEN) else -1
                price = grid.OPEN[out] if out >= 0 else np.nan
                limit = out if out >= 0 else len(grid.LOW)
                crash = np.flatnonzero(grid.LOW[entry:limit] <= stop_level)
                if len(crash):
                    out = entry + int(crash[0])
                    price = min(stop_level, grid.OPEN[out])
            trades.append((int(entry), int(out), float(price), "ladder"))
    return trades


def simulate(trades, pots, start, end, idle_only=False):
    initial = sum(n for n, _ in pots) * LOT
    wallet, slots, taken = initial, [[] for _ in pots], []
    for entry, exit_index, price, source in trades:
        if not (start <= grid.TIMES[entry] < end):
            continue
        for p in range(len(pots)):
            wallet += sum(s[1] for s in slots[p] if s[0] <= entry)
            slots[p] = [s for s in slots[p] if s[0] > entry]
        if exit_index < 0 or (idle_only and source in LAD and any(slots[:-1])):
            continue
        for p, (lots, sources) in enumerate(pots):
            if source in sources and len(slots[p]) < lots and wallet >= LOT:
                fill = grid.OPEN[entry] * (1 + grid.SLIP)
                qty = LOT / (fill * (1 + FEE))
                proceeds = qty * price * (1 - grid.SLIP) * (1 - FEE)
                wallet -= LOT
                slots[p].append((exit_index, proceeds))
                taken.append((entry, exit_index, qty, proceeds, source))
                break
    return cu._finish(taken, wallet, slots, pots, initial, start, end)


def evaluate(label, trades, pots, idle_only=False):
    runs = {n: simulate(trades, pots, *research.WINDOWS[n], idle_only) for n in ("full", "earlier", "later", "unseen", *TESTS)}
    full, ledger = runs["full"], runs["full"]["ledger"]
    wf = [runs[w]["profit"] for w in TESTS]
    sub = ledger[ledger.source.isin(LAD)] if len(ledger) else ledger
    return {"design": label, "capital": int(full["capital"]),
            "core": int(ledger.source.isin(CORE).sum()) if len(ledger) else 0,
            "pull": int(ledger.source.isin(PULL).sum()) if len(ledger) else 0,
            "ladder": len(sub), "ladder_pnl": round(sub.pnl.sum(), 2) if len(sub) else 0.0,
            "ladder_win%": round(100 * (sub.pnl > 0).mean(), 1) if len(sub) else 0.0,
            "worst_lot": round(sub.pnl.min(), 2) if len(sub) else 0.0,
            "profit": round(full["profit"], 2), "earlier": round(runs["earlier"]["profit"], 2),
            "later": round(runs["later"]["profit"], 2), "unseen": round(runs["unseen"]["profit"], 2),
            "walk_forward": round(sum(wf), 2), "wf_windows": f"{sum(x > 0 for x in wf)}/6",
            "mtm_dd%": round(full["dd"], 2), "mtm_dd$": round(full["dd_usd"], 2)}


def main() -> None:
    raw, bullish, ema, mode_c = pb.setup()
    avg = average_7d(raw)
    runs = dips(avg)
    core = pb.build(raw, bullish, ema, mode_c)
    pull = [t for t in pb.build(raw, bullish, ema, [], pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES))
            if t[3] == "pullback"]
    key = lambda t: (t[0], PRIORITY[t[3]])
    book = lambda *parts: sorted([t for part in parts for t in part], key=key)
    plan, base = book(core, pull), [(5, CORE), (2, PULL)]
    plan_row = evaluate("plan", plan, base)
    pd.set_option("display.width", 340)

    full = research.WINDOWS["full"]
    dev = grid.CLOSE / avg - 1
    inside = [(s, e) for s, e in runs if full[0] <= grid.TIMES[s] < full[1]]
    depth = pd.Series([-100 * np.nanmin(dev[s:e if e > 0 else len(dev)]) for s, e in inside])
    print(f"dips below the 7-day average in the full window: {len(inside)}")
    for r in (4, 5, 6, 8, 10, 12, 15, 20):
        print(f"   reached -{r:>2}%: {(depth >= r).sum():3d}")

    print("\n=== 1. the ladder on its own 3 lots, beside the plan (is it any good?)")
    rows = []
    for rungs in RUNGS:
        for exit_style, stop in EXITS:
            tag = f"stop -{stop:g}%" if stop else "per-lot -4.5%"
            r = evaluate(f"rungs {'/'.join(f'-{x:g}' for x in rungs)}, {exit_style} exit, {tag}",
                         book(core, pull, build(avg, runs, bullish, ema, rungs, exit_style, stop)), base + [(3, LAD)])
            r["adds_profit"] = round(r["profit"] - plan_row["profit"], 2)
            r["adds_wf"] = round(r["walk_forward"] - plan_row["walk_forward"], 2)
            rows.append(r)
    frame = pd.DataFrame(rows).set_index("design")
    print(frame[["ladder", "ladder_pnl", "ladder_win%", "worst_lot", "adds_profit", "adds_wf", "wf_windows",
                 "earlier", "later", "unseen", "mtm_dd$"]].to_string())

    best = frame.adds_wf.idxmax()
    choice = [(r, e, s) for r in RUNGS for e, s in EXITS][list(frame.index).index(best)]
    trades = build(avg, runs, bullish, ema, *choice)
    print(f"\n(hindsight best on walk-forward: {best} - used below only to compare the ways of organising it)")

    print("\n=== 2. every way to organise it beside the plan (core 5 + pullback 2)")
    rows = [evaluate("PLAN core 5 + pullback 2", plan, base)]
    for k in (1, 2, 3):
        rows.append(evaluate(f"CONTROL +{k} pullback lots", plan, [(5, CORE), (2 + k, PULL)]))
    for k in (1, 2, 3):
        rows.append(evaluate(f"+ ladder sleeve {k} x $100 (first {k} rung{'s' if k > 1 else ''})",
                             book(core, pull, trades), base + [(k, LAD)]))
    rows.append(evaluate("ladder SHARES the core's 5 lots", book(core, pull, trades), [(5, CORE | LAD), (2, PULL)]))
    rows.append(evaluate("ladder SHARES the pullback's 2 lots", book(core, pull, trades), [(5, CORE), (2, PULL | LAD)]))
    rows.append(evaluate("+ ladder 3 x $100, only when core + pullback idle", book(core, pull, trades),
                         base + [(3, LAD)], idle_only=True))
    print(pd.DataFrame(rows).set_index("design").to_string())

    print("\n=== 3. honest selection test: pick rungs / exit on the 6 months before each window")
    settings = {(r, e, s): build(avg, runs, bullish, ema, r, e, s) for r in RUNGS for e, s in EXITS}
    plan_w = {w: simulate(plan, base, *research.WINDOWS[w])["profit"] for w in (*TRAINS, *TESTS)}
    for k in (1, 2, 3):
        score = {s: {w: simulate(book(core, pull, v), base + [(k, LAD)], *research.WINDOWS[w])["profit"] - plan_w[w]
                     for w in (*TRAINS, *TESTS)} for s, v in settings.items()}
        control = {w: simulate(plan, [(5, CORE), (2 + k, PULL)], *research.WINDOWS[w])["profit"] - plan_w[w] for w in TESTS}
        table, picks = [], []
        for i, test in enumerate(TESTS):
            pick = max(score, key=lambda s: score[s][TRAINS[i]])
            picks.append(pick)
            table.append({"window": research.TESTS[i][0],
                          "chosen": f"-{'/-'.join(f'{x:g}' for x in pick[0])} {pick[1]}{f' {pick[2]:g}%' if pick[2] else ''}",
                          "ladder added": round(score[pick][test], 2),
                          f"+{k} pullback lot(s) added": round(control[test], 2)})
        honest = sum(score[s][t] for s, t in zip(picks, TESTS))
        print(f"\n--- ladder sleeve of {k} x $100")
        print(pd.DataFrame(table).to_string(index=False))
        print(f"  ladder, picked in advance     ${honest:8.2f}  positive {sum(score[s][t] > 0 for s, t in zip(picks, TESTS))}/6")
        print(f"  +{k} pullback lot(s) instead   ${sum(control.values()):8.2f}  positive {sum(v > 0 for v in control.values())}/6")


if __name__ == "__main__":
    main()
