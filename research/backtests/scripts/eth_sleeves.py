"""ETH sleeves: does a separate pullback-to-trend book earn its money, and what is the best way to run it?

Core      the deployed ETH strategy (dip + Mode C), untouched
Pullback  in an uptrend (7d>15d>30d), a 1-minute close below the N-hour EMA for >= `dwell` minutes, then
          the first close back above it -> buy next minute. Deployed dip exit (Mode A by construction).

A "design" says how lots are organised:
  pots        each pot has its own lots and its own cash; a trade goes to the first pot that accepts its source
  idle_only   the pullback may only buy while NO lot is open anywhere in the book

The fairness control: an extra $100 in a pullback sleeve is only worth it if it beats the same $100 added to
the core as a 4th lot. Everything is marked the same way as three_modes.account (lots at cost), so the
deployed core reproduces $271.15 / -4.94% exactly. Drawdown is also given in dollars, because a bigger book
shows a smaller percentage for the same loss.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import eth_pullback as pb

LOT = 100.0
FEE = 7.5 / 10_000
TESTS = [f"wf{i}_test" for i in range(len(research.TESTS))]
TRAINS = [f"wf{i}_train" for i in range(len(research.TESTS))]
CORE = {"dip", "breakout"}
PULL = {"pullback"}


def simulate(trades, pots, start, end, idle_only=False):
    """pots: list of (lots, sources). ONE shared wallet, as on Binance: each pot only limits how many lots
    its sources may hold at once. Returns profit, drawdown %, drawdown $, ledger, lot-minutes held."""
    initial = sum(lots for lots, _ in pots) * LOT
    wallet = initial
    slots = [[] for _ in pots]
    peak, worst_pct, worst_usd, held, taken = initial, 0.0, 0.0, 0, []
    for entry, exit_index, price, source in trades:
        if not (start <= grid.TIMES[entry] < end):
            continue
        for p in range(len(pots)):
            for out, proceeds in [s for s in slots[p] if s[0] <= entry]:
                wallet += proceeds
            slots[p] = [s for s in slots[p] if s[0] > entry]
        equity = wallet + LOT * sum(len(s) for s in slots)
        peak = max(peak, equity)
        worst_pct = min(worst_pct, equity / peak - 1)
        worst_usd = min(worst_usd, equity - peak)
        if exit_index < 0:
            continue
        if idle_only and source in PULL and any(slots):
            continue
        for p, (lots, sources) in enumerate(pots):
            if source in sources and len(slots[p]) < lots and wallet >= LOT:
                fill = grid.OPEN[entry] * (1 + grid.SLIP)
                proceeds = LOT / (fill * (1 + FEE)) * price * (1 - grid.SLIP) * (1 - FEE)
                wallet -= LOT
                slots[p].append((exit_index, proceeds))
                held += exit_index - entry
                taken.append({"source": source, "pnl": proceeds - LOT})
                break
    for p in range(len(pots)):
        wallet += sum(proceeds for _, proceeds in slots[p])
    return {"profit": wallet - initial, "dd": worst_pct * 100, "dd_usd": worst_usd,
            "ledger": pd.DataFrame(taken), "held": held, "capital": initial}


def evaluate(label, trades, pots, idle_only=False):
    periods = {n: simulate(trades, pots, *research.WINDOWS[n], idle_only) for n in ("full", "earlier", "later", "unseen", *TESTS)}
    full = periods["full"]
    ledger = full["ledger"]
    minutes = (research.WINDOWS["full"][1] - research.WINDOWS["full"][0]).total_seconds() / 60
    lots = sum(n for n, _ in pots)
    wf = [periods[w]["profit"] for w in TESTS]
    by = ledger.groupby("source").pnl.agg(["count", "sum"]) if len(ledger) else pd.DataFrame()
    return {"design": label, "capital": int(full["capital"]),
            "core_trades": int(by.loc[list(CORE & set(by.index)), "count"].sum()) if len(by) else 0,
            "pullback_trades": int(by.loc["pullback", "count"]) if "pullback" in by.index else 0,
            "pullback_pnl": round(by.loc["pullback", "sum"], 2) if "pullback" in by.index else 0.0,
            "profit": round(full["profit"], 2), "return%": round(100 * full["profit"] / full["capital"], 1),
            "earlier": round(periods["earlier"]["profit"], 2), "later": round(periods["later"]["profit"], 2),
            "unseen": round(periods["unseen"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "wf_windows": f"{sum(x > 0 for x in wf)}/6", "drawdown%": round(full["dd"], 2),
            "drawdown$": round(full["dd_usd"], 2), "money_busy%": round(100 * full["held"] / (lots * minutes), 1)}


def main() -> None:
    raw, bullish, ema, mode_c = pb.setup()
    core = [t for t in pb.build(raw, bullish, ema, mode_c)]
    pd.set_option("display.width", 320)

    def pull(hours, dwell):
        entries = pb.pullback_entries(grid.CLOSE, bullish, hours, dwell, grid.TIMES)
        return [t for t in pb.build(raw, bullish, ema, [], entries) if t[3] == "pullback"]

    chosen = pull(24, 180)
    both = sorted(core + chosen, key=lambda t: (t[0], t[3] == "pullback"))

    print("=== 1. the pullback rule ALONE, on its own lots (EMA 24h, dwell 180m)")
    rows = [evaluate(f"pullback alone, {n} x $100", chosen, [(n, PULL)]) for n in (1, 2, 3)]
    print(pd.DataFrame(rows).set_index("design").drop(columns=["core_trades"]).to_string())

    print("\n=== 2. every way to organise the lots, with the fairness controls")
    designs = [
        ("core 3 x $100 (deployed today)", core, [(3, CORE)], False),
        ("CONTROL core 4 x $100 (extra $100 to the core)", core, [(4, CORE)], False),
        ("CONTROL core 5 x $100 (extra $200 to the core)", core, [(5, CORE)], False),
        ("core 3 + pullback sleeve 1 x $100", both, [(3, CORE), (1, PULL)], False),
        ("core 3 + pullback sleeve 2 x $100", both, [(3, CORE), (2, PULL)], False),
        ("core 3 + pullback sleeve 3 x $100", both, [(3, CORE), (3, PULL)], False),
        ("shared 3, pullback only when idle", both, [(3, CORE | PULL)], True),
        ("shared 4, pullback only when idle", both, [(4, CORE | PULL)], True),
        ("shared 4, all compete freely", both, [(4, CORE | PULL)], False),
        ("core 2 + pullback 1 reserved (same $300)", both, [(2, CORE), (1, PULL)], False),
    ]
    rows = [evaluate(name, trades, pots, idle) for name, trades, pots, idle in designs]
    print(pd.DataFrame(rows).set_index("design").to_string())

    print("\n=== 3. honest selection test for the sleeve: pick the pullback setting on the 6 months before")
    settings = {(h, d): pull(h, d) for h in pb.HOURS for d in pb.DWELL}
    for lots in (1, 2, 3):
        alone = {w: simulate(core, [(3, CORE)], *research.WINDOWS[w])["profit"] for w in (*TRAINS, *TESTS)}
        score = {}
        for k, v in settings.items():
            merged = sorted(core + v, key=lambda t: (t[0], t[3] == "pullback"))
            score[k] = {w: simulate(merged, [(3, CORE), (lots, PULL)], *research.WINDOWS[w])["profit"] - alone[w]
                        for w in (*TRAINS, *TESTS)}
        extra = {w: simulate(core, [(3 + lots, CORE)], *research.WINDOWS[w])["profit"] - alone[w] for w in TESTS}
        table, picks = [], []
        for i, test in enumerate(TESTS):
            pick = max(score, key=lambda k: score[k][TRAINS[i]])
            picks.append(pick)
            table.append({"window": research.TESTS[i][0], "setting chosen": f"EMA {pick[0]}h / {pick[1]}m",
                          "sleeve earned": round(score[pick][test], 2),
                          "24h/180m fixed": round(score[(24, 180)][test], 2),
                          f"same ${int(lots*LOT)} in core": round(extra[test], 2)})
        print(f"\n--- sleeve of {lots} x $100")
        print(pd.DataFrame(table).to_string(index=False))
        honest = sum(score[k][t] for k, t in zip(picks, TESTS))
        fixed = sum(score[(24, 180)][t] for t in TESTS)
        control = sum(extra.values())
        print(f"  sleeve, setting picked in advance (honest)  ${honest:8.2f}   positive windows "
              f"{sum(score[k][t] > 0 for k, t in zip(picks, TESTS))}/6")
        print(f"  sleeve, 24h/180m fixed (hindsight pick)      ${fixed:8.2f}")
        print(f"  same money as extra core lots (no choice)    ${control:8.2f}")


if __name__ == "__main__":
    main()
