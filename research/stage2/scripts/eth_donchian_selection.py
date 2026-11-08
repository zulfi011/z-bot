"""The honest test for the Donchian entry: choose N using only data from before each window."""

from __future__ import annotations

import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import three_modes as tm
import eth_donchian as dc

TESTS = [f"wf{i}_test" for i in range(len(research.TESTS))]
TRAINS = [f"wf{i}_train" for i in range(len(research.TESTS))]
DEPLOYED = "no Donchian"
FEE = 7.5 / 10_000


def main() -> None:
    raw, bullish, ema, mode_c = dc.setup()
    pd.set_option("display.width", 260)

    candidates, draws = {}, {}

    def score(name, trades):
        candidates[name] = {n: tm.account(trades, *research.WINDOWS[n], FEE)["profit"]
                            for n in (*TRAINS, *TESTS)}
        draws[name] = {n: tm.account(trades, *research.WINDOWS[n], FEE)["dd"] for n in TESTS}

    score(DEPLOYED, dc.build(raw, bullish, ema, mode_c))
    for days in dc.DAYS:
        entries = dc.donchian_entries(grid.HIGH, grid.CLOSE, days, grid.TIMES)
        score(f"{days}-day", dc.build(raw, bullish, ema, mode_c, entries))
    print(f"{len(candidates)} candidates across {len(TRAINS)} training and {len(TESTS)} test windows\n")

    best = "55-day"
    picks, rows = [], []
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
              "deployed, no Donchian": sum(candidates[DEPLOYED][t] for t in TESTS),
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
