"""The honest test for ETH's ATR stop: choose the multiplier using only data from before each test window.

The full-history table liked stop = 1.0 x ATR and liked 1.5 x ATR's walk-forward even more. This asks the
only question that matters: could we have PICKED the right multiplier in advance? Each three-month test
window is scored with the multiplier that won the six months immediately before it.

The search is deliberately narrow - the stop multiplier only, everything else left exactly as deployed.
"""

from __future__ import annotations

import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import three_modes as tm
import eth_atr_exit as atr_exit

KS = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
TESTS = [f"wf{i}_test" for i in range(len(research.TESTS))]
TRAINS = [f"wf{i}_train" for i in range(len(research.TESTS))]
DEPLOYED = "flat -4.5%"


def windows_for(trades, fee=7.5 / 10_000):
    return {name: tm.account(trades, *research.WINDOWS[name], fee)["profit"]
            for name in (*TRAINS, *TESTS, "full")}


def drawdowns_for(trades, fee=7.5 / 10_000):
    return {name: tm.account(trades, *research.WINDOWS[name], fee)["dd"] for name in TESTS}


def main() -> None:
    raw = replay.load_raw("ETHUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=tm.EMA_HOURS * 60, adjust=False).mean().to_numpy()
    atr = atr_exit.atr_percent(raw)
    entries = atr_exit.mode_c_entries(raw)
    pd.set_option("display.width", 250)

    candidates = {DEPLOYED: windows_for(atr_exit.build(raw, bullish, ema, entries, atr))}
    draw = {DEPLOYED: drawdowns_for(atr_exit.build(raw, bullish, ema, entries, atr))}
    for k in KS:
        trades = atr_exit.build(raw, bullish, ema, entries, atr, stop_k=k)
        candidates[f"{k} x ATR"] = windows_for(trades)
        draw[f"{k} x ATR"] = drawdowns_for(trades)
    print(f"{len(candidates)} candidates scored across {len(TRAINS)} training and {len(TESTS)} test windows\n")

    picks, rows = [], []
    for index, test in enumerate(TESTS):
        train = TRAINS[index]
        chosen = max(candidates, key=lambda name: candidates[name][train])
        picks.append(chosen)
        rows.append({"window": research.TESTS[index][0], "chosen on the 6 months before": chosen,
                     "it earned": round(candidates[chosen][test], 2),
                     "deployed earned": round(candidates[DEPLOYED][test], 2),
                     "1.0 x ATR fixed": round(candidates["1.0 x ATR"][test], 2),
                     "1.5 x ATR fixed": round(candidates["1.5 x ATR"][test], 2),
                     "best in hindsight": round(max(candidates[n][test] for n in candidates), 2)})
    print("=== window by window")
    print(pd.DataFrame(rows).to_string(index=False))

    totals = {"picked in advance (honest)": sum(candidates[n][t] for n, t in zip(picks, TESTS)),
              "deployed flat -4.5%, no choice": sum(candidates[DEPLOYED][t] for t in TESTS),
              "1.0 x ATR, fixed all through": sum(candidates["1.0 x ATR"][t] for t in TESTS),
              "1.5 x ATR, fixed all through": sum(candidates["1.5 x ATR"][t] for t in TESTS),
              "oracle (hindsight each window)": sum(max(candidates[n][t] for n in candidates) for t in TESTS)}
    print("\n=== totals across the six out-of-sample windows")
    for name, value in totals.items():
        print(f"  {name:<34} ${value:8.2f}")

    print("\n=== how often each multiplier won its training window")
    print(pd.Series(picks).value_counts().to_string())

    print("\n=== worst drawdown inside each test window (%)")
    frame = pd.DataFrame({name: draw[name] for name in draw}).round(2)
    frame.index = [research.TESTS[i][0] for i in range(len(TESTS))]
    print(frame.to_string())


if __name__ == "__main__":
    main()
