"""The honest test for SOL: choose Mode A and Mode C using only data from before each test window.

Each of the six three-month test windows is scored with settings picked from the six months immediately
before it, never with any knowledge of the window being scored. That is the test that flattened ETH's exit
improvement from "+87%" to noise, and it is the one thing standing between "the backtest likes this" and
"we could actually have found this in advance".

The search is deliberately narrow - the EMA length only, with the arm and stop left at their deployed values,
and Mode C on or off. A narrow, reasoned search is the fair version of this test; sweeping thousands of
combinations on six months of trades only ever finds noise.
"""

from __future__ import annotations

import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import three_modes as three

three.COIN = "sol"
SOL_C = dict(chart=60, bars=24, zone=2.0, confirm=0, stop=4.0, arm=1.283, giveback=22.0)
HOURS = [4, 6, 8, 10, 12, 16, 24, 36, 48]
TESTS = [f"wf{i}_test" for i in range(len(research.TESTS))]
TRAINS = [f"wf{i}_train" for i in range(len(research.TESTS))]


def windows_for(trades, fee=7.5 / 10_000):
    """Profit in every window - training ones included - for one set of candidate trades."""
    return {name: three.account(trades, *research.WINDOWS[name], fee)["profit"]
            for name in (*TRAINS, *TESTS, "full")}


def main() -> None:
    rule = live.load_rule("sol")
    raw = replay.load_raw("SOLUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    pd.set_option("display.width", 250)

    # Every candidate, scored in every window once.
    candidates: dict[str, dict] = {}
    for mode_c in (None, SOL_C):
        tag_c = "with Mode C" if mode_c else "no Mode C"
        candidates[f"no Mode A, {tag_c}"] = windows_for(
            three.build(raw, bullish, None, set(), mode_c=mode_c, dip_stop=rule["stop_pct"]))
        for hours in HOURS:
            ema = pd.Series(grid.CLOSE).ewm(span=hours * 60, adjust=False).mean().to_numpy()
            candidates[f"EMA {hours}h, {tag_c}"] = windows_for(
                three.build(raw, bullish, ema, {"dip", "breakout"} if mode_c else {"dip"},
                            mode_c=mode_c, dip_stop=rule["stop_pct"]))
    print(f"{len(candidates)} candidates scored across {len(TRAINS)} training and {len(TESTS)} test windows\n")

    deployed = "no Mode A, no Mode C"
    picks, rows = [], []
    for index in range(len(TESTS)):
        train, test = TRAINS[index], TESTS[index]
        chosen = max(candidates, key=lambda name: candidates[name][train])
        picks.append(chosen)
        rows.append({"window": research.TESTS[index][0],
                     "chosen on training data": chosen,
                     "it earned": round(candidates[chosen][test], 2),
                     "deployed earned": round(candidates[deployed][test], 2),
                     "full ABC earned": round(candidates["EMA 8h, with Mode C"][test], 2),
                     "best possible (hindsight)": round(max(candidates[name][test] for name in candidates), 2)})
    frame = pd.DataFrame(rows)
    print("=== what a rule chosen in advance would have earned, window by window")
    print(frame.to_string(index=False))

    totals = {
        "picked in advance (honest)": sum(candidates[name][test] for name, test in zip(picks, TESTS)),
        "deployed, no choice made": sum(candidates[deployed][test] for test in TESTS),
        "the ABC strategy, fixed": sum(candidates["EMA 8h, with Mode C"][test] for test in TESTS),
        "no Mode A, with Mode C, fixed": sum(candidates["no Mode A, with Mode C"][test] for test in TESTS),
        "oracle (hindsight each window)": sum(max(candidates[name][test] for name in candidates) for test in TESTS),
    }
    print("\n=== totals across the six out-of-sample windows")
    for name, value in totals.items():
        print(f"  {name:<34} ${value:8.2f}")

    print("\n=== how often each candidate was the training-window winner")
    print(pd.Series(picks).value_counts().to_string())

    print("\n=== Mode C on its own: does adding it help in each test window, whatever Mode A does?")
    helped = []
    for name in candidates:
        if "with Mode C" not in name:
            continue
        without = name.replace("with Mode C", "no Mode C")
        wins = sum(candidates[name][test] > candidates[without][test] for test in TESTS)
        helped.append({"Mode A setting": name.replace(", with Mode C", ""),
                       "windows Mode C improved": f"{wins}/6",
                       "total added": round(sum(candidates[name][test] - candidates[without][test] for test in TESTS), 2)})
    print(pd.DataFrame(helped).to_string(index=False))


if __name__ == "__main__":
    main()
