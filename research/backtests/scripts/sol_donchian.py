"""Does the N-day high breakout (Donchian) help SOL, and on what settings?

Mode C only fires after compression - a band no wider than 2% over 24 hours. A Donchian break asks nothing about
how quiet the market has been: it just wants a new N-day high. So it can fire in a wide, fast market where Mode C
is disqualified. Tuned from scratch for SOL (never another coin's numbers).

  entry    the first 1-minute close above the highest high of the previous N days; only the first break of each
           run counts, the buy lands on the next minute's open, and SOL's blocked hours (06:00-12:00 UTC) apply
  exits    three candidates, since SOL's -2% dip stop is tight for a breakout:
             "dip"    the deployed dip exit: stop -2%, trail +1.251% / giveback 12%, Mode A on the 8-hour line
             "modeC"  what SOL's own breakouts use: stop -4%, trail +1.283% / giveback 22%
             "wide"   the dip's trail with a -4% stop

Everything else is SOL as deployed. Live buying rule (a full lot, or what the wallet has left), BNB fees.
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

DAYS = [3, 5, 7, 10, 20, 30, 55]
EXITS = {"dip": (1.251, 12.0, 2.0), "modeC": (1.283, 22.0, 4.0), "wide": (1.251, 12.0, 4.0)}
CORE, DON = {"dip", "breakout"}, {"donchian"}


def donchian_entries(days: int, blocked) -> np.ndarray:
    window = days * 1440
    channel = pd.Series(grid.HIGH).rolling(window).max().shift(1).to_numpy()
    broke = np.isfinite(channel) & (grid.CLOSE > channel)
    first = broke & ~np.r_[False, broke[:-1]]
    entries = np.flatnonzero(first) + 1
    entries = entries[entries < len(grid.CLOSE) - 1]
    if blocked:
        hour = grid.TIMES[entries].hour
        entries = entries[~((hour >= blocked[0]) & (hour < blocked[1]))]
    return entries.astype(np.int64)


def donchian_trades(entries, bullish, ema, exit_name):
    arm, giveback, stop = EXITS[exit_name]
    out = []
    for entry in entries:
        entry = int(entry)
        o, p, _ = opt.trade(entry, arm, giveback, stop, ema if bullish[entry] else None)
        out.append((entry, o, p, "donchian"))
    return out


def score(label, trades, pots, extra=None):
    runs = {w: sp.simulate(trades, pots, 100.0, *research.WINDOWS[w])
            for w in ("full", "earlier", "later", "unseen", *rg.TESTS)}
    led = runs["full"]["ledger"]
    wf = [runs[w]["profit"] for w in rg.TESTS]
    don = led[led.source == "donchian"] if len(led) else led
    return {"setup": label, "money": int(sum(n for n, _ in pots) * 100), "trades": len(led),
            "donchian": len(don), "donchian_pnl": round(don.pnl.sum(), 2) if len(don) else 0.0,
            "don_win%": round(100 * (don.pnl > 0).mean(), 1) if len(don) else 0.0,
            "profit": round(runs["full"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "windows": f"{sum(x > 0 for x in wf)}/6", "later": round(runs["later"]["profit"], 2),
            "unseen": round(runs["unseen"]["profit"], 2), **(extra or {})}


def main() -> None:
    raw, bullish, ema = sp.setup()
    core = sp.core_trades(raw, bullish, ema)
    rule = live.load_rule("sol")
    pd.set_option("display.width", 260)
    book = lambda *parts: sorted([t for p in parts for t in p], key=lambda t: (t[0], 0 if t[3] != "donchian" else 1))

    print("=== SOL as deployed (dip + Mode C)")
    print(pd.DataFrame([score(f"core only, {n} x $100", core, [(n, CORE)]) for n in (1, 3, 5)])
          .set_index("setup").drop(columns=["donchian", "donchian_pnl", "don_win%"]).to_string())

    print(f"\n=== 1. every channel length x exit, sharing SOL's 3 lots ({len(DAYS) * len(EXITS)} combinations)")
    rows, sets = [], {}
    for days in DAYS:
        entries = donchian_entries(days, rule["blocked"])
        for exit_name in EXITS:
            sets[(days, exit_name)] = donchian_trades(entries, bullish, ema, exit_name)
            rows.append(score(f"{days}-day high, {exit_name} exit", book(core, sets[(days, exit_name)]),
                              [(3, CORE | DON)], {"candidates": len(entries)}))
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup")[["candidates", "donchian", "donchian_pnl", "don_win%", "profit",
                                    "walk_forward", "windows", "later", "unseen"]].to_string())
    best = frame.iloc[0]["setup"]
    key = (int(best.split("-day")[0]), best.split(", ")[1].split(" exit")[0])
    print(f"\n(best on walk-forward: {best})")

    print("\n=== 2. the best setting: shared lots vs its own, against core-only at the same money")
    rows = []
    for n in (1, 3, 5):
        rows.append(score(f"core only, {n} x $100", core, [(n, CORE)]))
        rows.append(score(f"shared {n} lots, with Donchian", book(core, sets[key]), [(n, CORE | DON)]))
    for core_n, don_n in ((3, 1), (3, 2), (5, 1), (5, 2)):
        rows.append(score(f"core {core_n} + Donchian {don_n} (own lots)", book(core, sets[key]),
                          [(core_n, CORE), (don_n, DON)]))
        rows.append(score(f"CONTROL core {core_n + don_n} only", core, [(core_n + don_n, CORE)]))
    print(pd.DataFrame(rows).set_index("setup")[["money", "trades", "donchian", "donchian_pnl", "profit",
                                                 "walk_forward", "windows", "unseen"]].to_string())

    print("\n=== 3. honest test: choose the channel and exit on the six months before each window")
    trains = [f"wf{i}_train" for i in range(6)]
    for lots, pots in ((3, [(3, CORE | DON)]), (1, [(3, CORE), (1, DON)]), (2, [(3, CORE), (2, DON)])):
        base_pots = [(3, CORE)] if lots != 3 else [(3, CORE | DON)]
        base = {w: sp.simulate(core, [(3, CORE)], 100.0, *research.WINDOWS[w])["profit"] for w in (*trains, *rg.TESTS)}
        scores = {k: {w: sp.simulate(book(core, v), pots, 100.0, *research.WINDOWS[w])["profit"] - base[w]
                      for w in (*trains, *rg.TESTS)} for k, v in sets.items()}
        picks = [max(scores, key=lambda k: scores[k][trains[i]]) for i in range(6)]
        honest = sum(scores[p][t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > 0 for p, t in zip(picks, rg.TESTS))
        label = "sharing the 3 lots" if lots == 3 else f"{lots} lot(s) of its own on top of core 3"
        print(f"  {label:<40} honest ${honest:8.2f}  positive {wins}/6")
        if lots == 3:
            for i, t in enumerate(rg.TESTS):
                print(f"      {research.TESTS[i][0]}  chose {picks[i][0]}-day {picks[i][1]}: {scores[picks[i]][t]:+8.2f}")


if __name__ == "__main__":
    main()
