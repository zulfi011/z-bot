"""Does pyramiding help SOL - adding lots to a lot that is already winning?

Tuned from scratch for SOL, whose trades are smaller than ETH's (it arms its trail at +1.251% and gives back 12%),
so the steps tested start well below ETH's +1%.

  step     the gain that triggers an add: +0.5 / 0.75 / 1 / 1.5 / 2 / 3% above the parent's fill
  levels   1, 2 or 3 adds per parent, in order
  parents  every open lot, or only those bought in a clean uptrend (Mode A lots)
  exit     the add takes SOL's dip exit from its own fill (Mode A on the 8-hour line when bought in an uptrend),
           always Mode A, always Mode B (giveback 12%), or it sells with its parent
  lots     the adds share SOL's 3 lots, or hold 1-3 lots of their own on top of them

An add also needs the price above the 8-hour line, obeys SOL's blocked hours, and only exists while its parent is
open. A pyramid lot is never itself a parent. Live buying rule, BNB fees, hourly windows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import eth_regime as rg
import sol_pullback as sp

STEPS = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
LEVELS = [1, 2, 3]
SCOPES = ["all lots", "trend lots"]
EXITS = ["deployed", "mode a", "mode b", "with parent"]
CORE, PYRA = {"dip", "breakout"}, {"pyramid"}
FEE, MIN_ORDER, LOT = 7.5 / 10_000, 5.0, 100.0
TRAINS = [f"wf{i}_train" for i in range(6)]


def parents_of(raw, bullish, ema):
    return [{"entry": entry, "exit": out, "price": price, "source": source, "key": index, "parent": None}
            for index, (entry, out, price, source) in enumerate(sp.core_trades(raw, bullish, ema))]


def adds_for(parents, bullish, ema, step, levels, scope, exit_mode, rule, blocked=(6, 12)):
    out = []
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
            hour = grid.TIMES[entry].hour
            if not (blocked and blocked[0] <= hour < blocked[1]):
                if exit_mode == "with parent":
                    o, p = parent["exit"], parent["price"]
                else:
                    use = None if exit_mode == "mode b" else ema if (exit_mode == "mode a" or bullish[entry]) else None
                    o, p, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"], use)
                out.append({"entry": entry, "exit": o, "price": p, "source": "pyramid",
                            "key": f"a{parent['key']}.{level}", "parent": parent["key"]})
            start = entry
    return out


def simulate(trades, pots, start, end):
    """One shared wallet, per-pot slots, the live buying rule; an add needs its parent open in this same run."""
    initial = sum(n for n, _ in pots) * LOT
    wallet, slots, taken, alive = initial, [[] for _ in pots], [], set()
    for trade in sorted(trades, key=lambda t: (t["entry"], t["parent"] is not None)):
        entry = trade["entry"]
        if not (start <= grid.TIMES[entry] < end):
            continue
        for p in range(len(pots)):
            for slot in [s for s in slots[p] if s[0] <= entry]:
                wallet += slot[1]
                alive.discard(slot[2])
            slots[p] = [s for s in slots[p] if s[0] > entry]
        if trade["exit"] < 0 or wallet < MIN_ORDER:
            continue
        if trade["parent"] is not None and trade["parent"] not in alive:
            continue
        for p, (lots, sources) in enumerate(pots):
            if trade["source"] in sources and len(slots[p]) < lots:
                spend = min(LOT, np.floor(wallet * 100) / 100)
                fill = grid.OPEN[entry] * (1 + grid.SLIP)
                proceeds = spend / (fill * (1 + FEE)) * trade["price"] * (1 - grid.SLIP) * (1 - FEE)
                wallet -= spend
                slots[p].append((trade["exit"], proceeds, trade["key"]))
                alive.add(trade["key"])
                taken.append({"source": trade["source"], "pnl": proceeds - spend})
                break
    for p in range(len(pots)):
        wallet += sum(s[1] for s in slots[p])
    return {"profit": wallet - initial, "ledger": pd.DataFrame(taken)}


def score(label, trades, pots):
    runs = {w: simulate(trades, pots, *research.WINDOWS[w]) for w in ("full", "unseen", *rg.TESTS)}
    led = runs["full"]["ledger"]
    wf = [runs[w]["profit"] for w in rg.TESTS]
    adds = led[led.source == "pyramid"] if len(led) else led
    return {"setup": label, "money": int(sum(n for n, _ in pots) * LOT), "trades": len(led), "adds": len(adds),
            "adds_pnl": round(adds.pnl.sum(), 2) if len(adds) else 0.0,
            "add_win%": round(100 * (adds.pnl > 0).mean(), 1) if len(adds) else 0.0,
            "profit": round(runs["full"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "windows": f"{sum(x > 0 for x in wf)}/6", "unseen": round(runs["unseen"]["profit"], 2)}


def main() -> None:
    raw, bullish, ema = sp.setup()
    rule = live.load_rule("sol")
    parents = parents_of(raw, bullish, ema)
    pd.set_option("display.width", 250)
    base = score("SOL core only, 3 x $100", parents, [(3, CORE)])
    print("=== SOL as deployed")
    print(pd.DataFrame([base, score("core only, 4 x $100", parents, [(4, CORE)]),
                        score("core only, 5 x $100", parents, [(5, CORE)])]).set_index("setup").to_string())

    sets = {(s, l, sc, e): adds_for(parents, bullish, ema, s, l, sc, e, rule)
            for s in STEPS for l in LEVELS for sc in SCOPES for e in EXITS}
    print(f"\n=== 1. all {len(sets)} rule combinations, adds sharing SOL's 3 lots (best 12 by walk-forward)")
    rows = [score(f"+{s:g}% x{l}, {sc}, {e}", parents + adds, [(3, CORE | PYRA)]) for (s, l, sc, e), adds in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(12).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())

    ranked = [key for key, _ in sorted(sets.items(), key=lambda item: -dict(
        zip([f"+{s:g}% x{l}, {sc}, {e}" for (s, l, sc, e) in sets], frame.set_index("setup")["walk_forward"].reindex(
            [f"+{s:g}% x{l}, {sc}, {e}" for (s, l, sc, e) in sets]).tolist()))[f"+{item[0][0]:g}% x{item[0][1]}, {item[0][2]}, {item[0][3]}"])][:4]
    print("\n=== 2. the best four rules with lots of their own, against core-only at the same money")
    rows = [base]
    for key in ranked:
        s, l, sc, e = key
        for k in (1, 2, 3):
            rows.append(score(f"+{s:g}% x{l}, {sc}, {e} — own {k}", parents + sets[key], [(3, CORE), (k, PYRA)]))
    for extra in (1, 2, 3):
        rows.append(score(f"CONTROL core {3 + extra} only", parents, [(3 + extra, CORE)]))
    print(pd.DataFrame(rows).set_index("setup").to_string())

    print("\n=== 3. honest test: choose the pyramid rule on the six months before each window")
    for label, pots in (("sharing the 3 lots", [(3, CORE | PYRA)]), ("1 lot of its own", [(3, CORE), (1, PYRA)]),
                        ("2 lots of its own", [(3, CORE), (2, PYRA)]), ("3 lots of its own", [(3, CORE), (3, PYRA)])):
        base_w = {w: simulate(parents, [(3, CORE)], *research.WINDOWS[w])["profit"] for w in (*TRAINS, *rg.TESTS)}
        scores = {k: {w: simulate(parents + v, pots, *research.WINDOWS[w])["profit"] - base_w[w]
                      for w in (*TRAINS, *rg.TESTS)} for k, v in sets.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > 0 for p, t in zip(picks, rg.TESTS))
        best = max(sets, key=lambda k: sum(scores[k][t] for t in rg.TESTS))
        print(f"  {label:<22} honest ${honest:8.2f} ({wins}/6) | best fixed rule "
              f"+{best[0]:g}% x{best[1]}, {best[2]}, {best[3]}: ${sum(scores[best][t] for t in rg.TESTS):8.2f}")


if __name__ == "__main__":
    main()
