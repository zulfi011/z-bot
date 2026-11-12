"""Every combination of pyramiding on ETH: add lots to a trade that is already winning.

  step     the gain that triggers an add: +1 / +2 / +3 / +4 / +6% from the parent lot's fill
  levels   how many adds one parent may have: 1, 2 or 3 (at step, 2 x step, 3 x step)
  parents  which lots may be added to: trend lots only (bought in an uptrend) or every lot
  exit     the add takes the deployed exit from its OWN fill, or sells WITH its parent
  lots     the adds compete for the book's lots, or they get their own pyramid lots (1, 2 or 3)

An add also requires the price to be above the 16-hour trend line at that minute, and it only exists if its
parent was really bought - a parent skipped for want of a lot has no adds.

Books: ETH live today (1 lot, everything shared) and the plan (core 5 + pullback 2). Live buying rule
(a full lot, or what the wallet has left), BNB fees, the usual windows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import eth_pullback as pb
import eth_regime as rg

STEPS = [1.0, 2.0, 3.0, 4.0, 6.0]
LEVELS = [1, 2, 3]
SCOPES = ["trend lots", "all lots"]
STYLES = ["own exit", "with parent"]
CORE, PULL, PYRA = {"dip", "breakout"}, {"pullback"}, {"pyramid"}
FEE, MIN_ORDER = 7.5 / 10_000, 5.0
LOT = 100.0


def base_book(raw, bullish, ema):
    """The deployed ETH book: dip + Mode C + pullback, each with its key so adds can find their parent."""
    rule = live.load_rule("eth")
    trades = []
    core = pb.build(raw, bullish, ema, pb.mode_c_entries(raw))
    entries = pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES)
    pulls = [t for t in pb.build(raw, bullish, ema, [], entries) if t[3] == "pullback"]
    for key, (entry, out, price, source) in enumerate(sorted(core + pulls, key=lambda t: t[0])):
        trades.append({"entry": entry, "exit": out, "price": price, "source": source, "key": key, "parent": None})
    return trades, rule


def adds_for(parents, bullish, ema, step, levels, scope, style, rule):
    """Add candidates for every parent, at step, 2 x step, ... while price is above the trend line."""
    adds = []
    for parent in parents:
        if parent["exit"] < 0 or (scope == "trend lots" and not bullish[parent["entry"]]):
            continue
        fill = grid.OPEN[parent["entry"]] * (1 + grid.SLIP)
        start, stop_at = parent["entry"] + 1, parent["exit"]
        for level in range(1, levels + 1):
            if start >= stop_at:
                break
            close, line = grid.CLOSE[start:stop_at], ema[start:stop_at]
            hit = np.flatnonzero((close >= fill * (1 + level * step / 100)) & (close > line))
            if not len(hit):
                break
            entry = start + int(hit[0]) + 1
            if entry >= stop_at:
                break
            if style == "with parent":
                out, price = parent["exit"], parent["price"]
            else:
                out, price, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], pb.tm.DIP_STOP,
                                          ema if bullish[entry] else None)
            adds.append({"entry": entry, "exit": out, "price": price, "source": "pyramid",
                         "key": f"a{parent['key']}.{level}", "parent": parent["key"]})
            start = entry
    return adds


def simulate(trades, pots, start, end):
    """One shared wallet, per-pot slots, the live buying rule. An add needs its parent open in this same run."""
    initial = sum(n for n, _ in pots) * LOT
    wallet, slots, taken, live_keys = initial, [[] for _ in pots], [], set()
    for trade in sorted(trades, key=lambda t: (t["entry"], t["parent"] is not None)):
        entry = trade["entry"]
        if not (start <= grid.TIMES[entry] < end):
            continue
        for p in range(len(pots)):
            for slot in [s for s in slots[p] if s[0] <= entry]:
                wallet += slot[1]
                live_keys.discard(slot[2])
            slots[p] = [s for s in slots[p] if s[0] > entry]
        if trade["exit"] < 0 or wallet < MIN_ORDER:
            continue
        if trade["parent"] is not None and trade["parent"] not in live_keys:
            continue
        for p, (lots, sources) in enumerate(pots):
            if trade["source"] in sources and len(slots[p]) < lots:
                spend = min(LOT, np.floor(wallet * 100) / 100)
                fill = grid.OPEN[entry] * (1 + grid.SLIP)
                proceeds = spend / (fill * (1 + FEE)) * trade["price"] * (1 - grid.SLIP) * (1 - FEE)
                wallet -= spend
                slots[p].append((trade["exit"], proceeds, trade["key"]))
                live_keys.add(trade["key"])
                taken.append({"source": trade["source"], "pnl": proceeds - spend})
                break
    for p in range(len(pots)):
        wallet += sum(s[1] for s in slots[p])
    return {"profit": wallet - initial, "ledger": pd.DataFrame(taken)}


def score(label, trades, pots, extra=None):
    runs = {w: simulate(trades, pots, *research.WINDOWS[w]) for w in ("full", "unseen", *rg.TESTS)}
    led = runs["full"]["ledger"]
    wf = [runs[w]["profit"] for w in rg.TESTS]
    adds = led[led.source == "pyramid"] if len(led) else led
    return {"setup": label, "money": int(sum(n for n, _ in pots) * LOT), "trades": len(led), "adds": len(adds),
            "adds_pnl": round(adds.pnl.sum(), 2) if len(adds) else 0.0,
            "add_win%": round(100 * (adds.pnl > 0).mean(), 1) if len(adds) else 0.0,
            "profit": round(runs["full"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "windows": f"{sum(x > 0 for x in wf)}/6", "unseen": round(runs["unseen"]["profit"], 2), **(extra or {})}


def main() -> None:
    raw, bullish, ema, _ = pb.setup()
    parents, rule = base_book(raw, bullish, ema)
    pd.set_option("display.width", 280)
    PLAN = [(5, CORE), (2, PULL)]
    LIVE = [(1, CORE | PULL)]
    base_plan = score("PLAN core 5 + pullback 2, no pyramiding", parents, PLAN)
    base_live = score("LIVE 1 shared lot, no pyramiding", parents, LIVE)
    print("=== the book without pyramiding")
    print(pd.DataFrame([base_plan, base_live]).set_index("setup").to_string())

    print(f"\n=== 1. all {len(STEPS) * len(LEVELS) * len(SCOPES) * len(STYLES)} rule combinations, adds sharing the plan's lots")
    rows, sets = [], {}
    for step in STEPS:
        for levels in LEVELS:
            for scope in SCOPES:
                for style in STYLES:
                    key = (step, levels, scope, style)
                    sets[key] = adds_for(parents, bullish, ema, step, levels, scope, style, rule)
                    rows.append(score(f"+{step:g}% x{levels}, {scope}, {style}", parents + sets[key],
                                      [(5, CORE | PYRA), (2, PULL)]))
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(12).to_string())
    print("... worst three:")
    print(frame.set_index("setup").tail(3).to_string())

    print("\n=== 2. the same rules with their OWN pyramid lots (best six by walk-forward above)")
    rows = [base_plan]
    for key in [tuple(k) for k in list(sets)][:0]:
        pass
    top = [k for k in sets][:0]
    ranked = frame.head(6)["setup"].tolist()
    lookup = {f"+{s:g}% x{l}, {sc}, {st}": (s, l, sc, st) for (s, l, sc, st) in sets}
    for label in ranked:
        key = lookup[label]
        for k in (1, 2, 3):
            rows.append(score(f"{label} — own {k} lot(s)", parents + sets[key], PLAN + [(k, PYRA)]))
    print(pd.DataFrame(rows).set_index("setup").to_string())

    print("\n=== 3. on the live book (1 shared lot) and with one pyramid lot of its own")
    rows = [base_live]
    for label in ranked[:4]:
        key = lookup[label]
        rows.append(score(f"{label} — shared", parents + sets[key], [(1, CORE | PULL | PYRA)]))
        rows.append(score(f"{label} — own 1 lot", parents + sets[key], [(1, CORE | PULL), (1, PYRA)]))
    print(pd.DataFrame(rows).set_index("setup").to_string())

    print("\n=== 4. honest test on the plan's book: choose the pyramid rule on the six months before each window")
    trains = [f"wf{i}_train" for i in range(6)]
    base_w = {w: simulate(parents, PLAN, *research.WINDOWS[w])["profit"] for w in (*trains, *rg.TESTS)}
    scores = {}
    for key, adds in sets.items():
        for k in (0, 1, 2):
            pots = [(5, CORE | PYRA), (2, PULL)] if k == 0 else PLAN + [(k, PYRA)]
            name = (key, "shared" if k == 0 else f"own {k}")
            scores[name] = {w: simulate(parents + adds, pots, *research.WINDOWS[w])["profit"] - base_w[w]
                            for w in (*trains, *rg.TESTS)}
    picks, table = [], []
    for i, test in enumerate(rg.TESTS):
        pick = max(scores, key=lambda n: scores[n][trains[i]])
        picks.append(pick)
        (s, l, sc, st), lots = pick
        table.append({"window": research.TESTS[i][0], "chosen": f"+{s:g}% x{l}, {sc}, {st}, {lots}",
                      "pyramiding added": round(scores[pick][test], 2)})
    print(pd.DataFrame(table).to_string(index=False))
    honest = sum(scores[n][t] for n, t in zip(picks, rg.TESTS))
    print(f"\n  pyramiding, picked in advance  ${honest:8.2f}  positive {sum(scores[n][t] > 0 for n, t in zip(picks, rg.TESTS))}/6")
    print(f"  best single rule in hindsight  ${max(sum(v[t] for t in rg.TESTS) for v in scores.values()):8.2f}")


if __name__ == "__main__":
    main()
