"""The honest test for the pullback entry: choose its settings using only data from before each window.

One combination of fifteen beat the deployed system on full history. One in fifteen is roughly what
chance delivers, and that winner also carried a -8.53% drawdown against -4.94%. This asks whether the
setting could have been PICKED in advance, and what the risk looked like out of sample.
"""

from __future__ import annotations

import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import three_modes as tm
import eth_pullback as pb

TESTS = [f"wf{i}_test" for i in range(len(research.TESTS))]
TRAINS = [f"wf{i}_train" for i in range(len(research.TESTS))]
DEPLOYED = "no pullback"


def main() -> None:
    raw, bullish, ema, mode_c = pb.setup()
    pd.set_option("display.width", 260)

    candidates, draws = {}, {}
    trades = pb.build(raw, bullish, ema, mode_c)
    candidates[DEPLOYED] = {n: tm.account(trades, *research.WINDOWS[n], 7.5 / 10_000)["profit"]
                            for n in (*TRAINS, *TESTS)}
    draws[DEPLOYED] = {n: tm.account(trades, *research.WINDOWS[n], 7.5 / 10_000)["dd"] for n in TESTS}
    for hours in pb.HOURS:
        for dwell in pb.DWELL:
            entries = pb.pullback_entries(grid.CLOSE, bullish, hours, dwell, grid.TIMES)
            trades = pb.build(raw, bullish, ema, mode_c, entries)
            name = f"EMA {hours}h / dwell {dwell}m"
            candidates[name] = {n: tm.account(trades, *research.WINDOWS[n], 7.5 / 10_000)["profit"]
                                for n in (*TRAINS, *TESTS)}
            draws[name] = {n: tm.account(trades, *research.WINDOWS[n], 7.5 / 10_000)["dd"] for n in TESTS}
    print(f"{len(candidates)} candidates across {len(TRAINS)} training and {len(TESTS)} test windows\n")

    picks, rows = [], []
    best = "EMA 4h / dwell 180m"
    for index, test in enumerate(TESTS):
        chosen = max(candidates, key=lambda n: candidates[n][TRAINS[index]])
        picks.append(chosen)
        rows.append({"window": research.TESTS[index][0], "chosen on the 6 months before": chosen,
                     "it earned": round(candidates[chosen][test], 2),
                     "deployed earned": round(candidates[DEPLOYED][test], 2),
                     f"{best} fixed": round(candidates[best][test], 2),
                     "its drawdown": round(draws[best][test], 2),
                     "deployed drawdown": round(draws[DEPLOYED][test], 2)})
    print("=== window by window")
    print(pd.DataFrame(rows).to_string(index=False))

    totals = {"picked in advance (honest)": sum(candidates[n][t] for n, t in zip(picks, TESTS)),
              "deployed, no pullback": sum(candidates[DEPLOYED][t] for t in TESTS),
              f"{best}, fixed all through": sum(candidates[best][t] for t in TESTS),
              "oracle (hindsight each window)": sum(max(candidates[n][t] for n in candidates) for t in TESTS)}
    print("\n=== totals across the six out-of-sample windows")
    for name, value in totals.items():
        print(f"  {name:<34} ${value:8.2f}")

    print("\n=== how often each setting won its training window")
    print(pd.Series(picks).value_counts().to_string())

    beat = sum(candidates[best][t] > candidates[DEPLOYED][t] for t in TESTS)
    print(f"\n{best} beat the deployed system in {beat}/6 test windows")


if __name__ == "__main__":
    main()
