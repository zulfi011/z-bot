"""Regime hold for ETH: buy when the daily averages first stack 7d > 15d > 30d, hold until the stack breaks.

  signal    the stack forms at a UTC midnight (averages come from completed days only)
  buy       the next minute's open after the stack is first seen; one signal per regime
  sell      the next minute's open after the stack is first NOT seen
  variants  pure (no stop), or a protective stop -8% / -12% from the fill

Pure regime hold has no tuned setting at all, so its walk-forward windows are already honest.

Tested alone and alongside the planned book (core 5 lots + pullback sleeve 2 lots, shared wallet):
separate sleeve of k lots, sharing the core's lots, sharing the pullback's lots, idle-only.

Drawdown is MARKED TO MARKET hourly. Regime lots are held for weeks, and the at-cost drawdown used
before would hide a lot sitting -15% until it is sold.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import eth_pullback as pb

LOT, FEE = 100.0, 7.5 / 10_000
TESTS = [f"wf{i}_test" for i in range(len(research.TESTS))]
CORE, PULL, REG = {"dip", "breakout"}, {"pullback"}, {"regime"}
PRIORITY = {"dip": 0, "breakout": 0, "pullback": 1, "regime": 2}


def regime_trades(bullish, stop=None, copies=1):
    flips = np.flatnonzero(bullish[1:] & ~bullish[:-1]) + 1
    ends = np.flatnonzero(~bullish[1:] & bullish[:-1]) + 1
    trades, info = [], []
    for start in flips:
        entry = start + 1
        later = ends[ends > start]
        if not len(later) or later[0] + 1 >= len(grid.OPEN) or entry >= len(grid.OPEN):
            continue
        out = int(later[0]) + 1
        price = grid.OPEN[out]
        if stop is not None:
            level = grid.OPEN[entry] * (1 + grid.SLIP) * (1 - stop / 100)
            hit = np.flatnonzero(grid.LOW[entry:out] <= level)
            if len(hit):
                out = entry + int(hit[0])
                price = min(level, grid.OPEN[out])
        info.append({"start": grid.TIMES[entry], "days": (out - entry) / 1440,
                     "move%": 100 * (price / (grid.OPEN[entry] * (1 + grid.SLIP)) - 1)})
        trades += [(int(entry), int(out), float(price), "regime")] * copies
    return trades, pd.DataFrame(info)


def simulate(trades, pots, start, end, idle_only=False):
    """One shared wallet, per-pot slot limits. Also returns hourly mark-to-market drawdown."""
    initial = sum(n for n, _ in pots) * LOT
    wallet, slots, taken = initial, [[] for _ in pots], []
    for entry, exit_index, price, source in trades:
        if not (start <= grid.TIMES[entry] < end):
            continue
        for p in range(len(pots)):
            wallet += sum(s[1] for s in slots[p] if s[0] <= entry)
            slots[p] = [s for s in slots[p] if s[0] > entry]
        if exit_index < 0:
            continue
        if idle_only and source in REG and any(slots):
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
    for p in range(len(pots)):
        wallet += sum(s[1] for s in slots[p])
    # hourly mark-to-market equity
    hours = np.arange(np.searchsorted(grid.TIMES, start), np.searchsorted(grid.TIMES, end), 60)
    equity = np.full(len(hours), initial, dtype=float)
    for entry, out, qty, proceeds, _ in taken:
        realised_from = np.searchsorted(hours, out)
        equity[realised_from:] += proceeds - LOT
        a, b = np.searchsorted(hours, entry), realised_from
        if b > a:
            equity[a:b] += qty * grid.CLOSE[hours[a:b]] * (1 - grid.SLIP) * (1 - FEE) - LOT
    peak = np.maximum.accumulate(equity)
    ledger = pd.DataFrame([{"source": s, "pnl": p - LOT, "minutes": o - e} for e, o, q, p, s in taken])
    return {"profit": wallet - initial, "dd": 100 * (equity / peak - 1).min() if len(equity) else 0.0,
            "dd_usd": (equity - peak).min() if len(equity) else 0.0, "ledger": ledger, "capital": initial}


def evaluate(label, trades, pots, idle_only=False):
    runs = {n: simulate(trades, pots, *research.WINDOWS[n], idle_only) for n in ("full", "earlier", "later", "unseen", *TESTS)}
    full, ledger = runs["full"], runs["full"]["ledger"]
    wf = [runs[w]["profit"] for w in TESTS]
    count = lambda group: int(ledger.source.isin(group).sum()) if len(ledger) else 0
    pnl = lambda group: round(ledger[ledger.source.isin(group)].pnl.sum(), 2) if len(ledger) else 0.0
    return {"design": label, "capital": int(full["capital"]), "core": count(CORE), "pull": count(PULL),
            "regime": count(REG), "regime_pnl": pnl(REG), "profit": round(full["profit"], 2),
            "earlier": round(runs["earlier"]["profit"], 2), "later": round(runs["later"]["profit"], 2),
            "unseen": round(runs["unseen"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "wf_windows": f"{sum(x > 0 for x in wf)}/6", "mtm_dd%": round(full["dd"], 2),
            "mtm_dd$": round(full["dd_usd"], 2)}


def main() -> None:
    raw, bullish, ema, mode_c = pb.setup()
    core = pb.build(raw, bullish, ema, mode_c)
    entries = pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES)
    pull = [t for t in pb.build(raw, bullish, ema, [], entries) if t[3] == "pullback"]
    pd.set_option("display.width", 320)

    def book(*parts):
        return sorted([t for part in parts for t in part], key=lambda t: (t[0], PRIORITY[t[3]]))

    print("=== what the regimes look like (pure hold, full data)")
    _, info = regime_trades(bullish)
    window = info[(info.start >= research.WINDOWS["full"][0]) & (info.start < research.WINDOWS["full"][1])]
    print(f"regimes in the full window: {len(window)}; held {window.days.mean():.1f} days on average "
          f"(median {window.days.median():.1f}); winners {100 * (window['move%'] > 0).mean():.0f}%")
    print(window.assign(start=window.start.dt.date).round(2).to_string(index=False))

    print("\n=== 1. regime hold ALONE, on its own lots")
    rows = []
    for stop in (None, 8.0, 12.0):
        for k in (1, 2, 3):
            trades, _ = regime_trades(bullish, stop, copies=k)
            tag = "pure" if stop is None else f"stop -{stop:g}%"
            rows.append(evaluate(f"regime alone, {tag}, {k} x $100", trades, [(k, REG)]))
    print(pd.DataFrame(rows).set_index("design").drop(columns=["core", "pull"]).to_string())

    print("\n=== 2. added to the planned book (core 5 + pullback 2), every way to organise it")
    plan = book(core, pull)
    base = [(5, CORE), (2, PULL)]
    rows = [evaluate("PLAN core 5 + pullback 2 (no regime)", plan, base)]
    for k in (1, 2, 3):
        rows.append(evaluate(f"CONTROL +{k} core lots (core {5 + k})", plan, [(5 + k, CORE), (2, PULL)]))
        rows.append(evaluate(f"CONTROL +{k} pullback lots (pullback {2 + k})", plan, [(5, CORE), (2 + k, PULL)]))
    for stop in (None, 8.0):
        tag = "pure" if stop is None else "stop -8%"
        for k in (1, 2, 3):
            trades, _ = regime_trades(bullish, stop, copies=k)
            rows.append(evaluate(f"+ regime sleeve {k} x $100, {tag}", book(core, pull, trades), base + [(k, REG)]))
        trades, _ = regime_trades(bullish, stop, copies=2)
        rows.append(evaluate(f"regime SHARES the core's 5 lots, {tag}", book(core, pull, trades),
                             [(5, CORE | REG), (2, PULL)]))
        rows.append(evaluate(f"regime SHARES the pullback's 2 lots, {tag}", book(core, pull, trades),
                             [(5, CORE), (2, PULL | REG)]))
        rows.append(evaluate(f"+ regime 2 x $100, only when book is idle, {tag}", book(core, pull, trades),
                             base + [(2, REG)], idle_only=True))
    print(pd.DataFrame(rows).set_index("design").to_string())


if __name__ == "__main__":
    main()
