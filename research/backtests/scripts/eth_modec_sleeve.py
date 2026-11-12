"""Does ETH's Mode C do better with its own lots than sharing the core's with the dip?

Deployed: the dip and Mode C share the core lots, first come first served. Here Mode C gets separate slots it
alone may fill (the dip can no longer use them, and Mode C can no longer crowd the dip). Everything is compared
at EQUAL money - the same number of $100 lots - so the only difference is how the slots are shared out.
One shared wallet, BNB fees, hourly mark-to-market drawdown; nothing is tuned, so walk-forward is honest.
"""
from __future__ import annotations
import pandas as pd
import run_eth_full_research as research, run_sol_stage3_space_grid as grid
import eth_pullback as pb, eth_regime as rg

DIP, MODEC, PULL, CORE = {"dip"}, {"breakout"}, {"pullback"}, {"dip", "breakout"}


def main() -> None:
    raw, bullish, ema, mode_c = pb.setup()
    core = pb.build(raw, bullish, ema, mode_c)
    pull = [t for t in pb.build(raw, bullish, ema, [], pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES))
            if t[3] == "pullback"]
    both = sorted(core + pull, key=lambda t: (t[0], rg.PRIORITY[t[3]]))
    pd.set_option("display.width", 250)

    def row(label, trades, pots, base=None):
        runs = {w: rg.simulate(trades, pots, *research.WINDOWS[w]) for w in ("full", "unseen", *rg.TESTS)}
        led = runs["full"]["ledger"]
        wf = {w: runs[w]["profit"] for w in rg.TESTS}
        out = {"setup": label, "money": int(runs["full"]["capital"]),
               "dip": int((led.source == "dip").sum()), "modeC": int((led.source == "breakout").sum()),
               "modeC_pnl": round(led[led.source == "breakout"].pnl.sum(), 2),
               "pullback": int((led.source == "pullback").sum()),
               "profit": round(runs["full"]["profit"], 2), "walk_forward": round(sum(wf.values()), 2),
               "wf_windows": f"{sum(v > 0 for v in wf.values())}/6", "last_6_weeks": round(runs["unseen"]["profit"], 2),
               "mtm_dd%": round(runs["full"]["dd"], 2)}
        if base is not None:
            out["beats_shared"] = f"{sum(wf[w] > base[w] for w in rg.TESTS)}/6"
        return out, wf

    groups = [
        ("$300", core, [(3, CORE)], [("2 dip + 1 Mode C", [(2, DIP), (1, MODEC)])]),
        ("$400", core, [(4, CORE)], [("3 dip + 1 Mode C", [(3, DIP), (1, MODEC)]),
                                     ("2 dip + 2 Mode C", [(2, DIP), (2, MODEC)])]),
        ("$500", core, [(5, CORE)], [("4 dip + 1 Mode C", [(4, DIP), (1, MODEC)]),
                                     ("3 dip + 2 Mode C", [(3, DIP), (2, MODEC)])]),
        ("$700 plan", both, [(5, CORE), (2, PULL)], [("4 dip + 1 Mode C + 2 pullback", [(4, DIP), (1, MODEC), (2, PULL)]),
                                                     ("5 dip + 1 Mode C + 1 pullback", [(5, DIP), (1, MODEC), (1, PULL)])]),
        ("$800", both, [(5, CORE), (3, PULL)], [("5 dip + 1 Mode C + 2 pullback", [(5, DIP), (1, MODEC), (2, PULL)]),
                                                ("6 shared core + 2 pullback", [(6, CORE), (2, PULL)])]),
    ]
    for title, trades, shared_pots, alternatives in groups:
        shared, base = row(f"SHARED (deployed): {'+'.join(str(n) for n, _ in shared_pots)}", trades, shared_pots)
        rows = [shared] + [row(label, trades, pots, base)[0] for label, pots in alternatives]
        print(f"\n=== {title}")
        print(pd.DataFrame(rows).set_index("setup").fillna("").to_string())


if __name__ == "__main__":
    main()
