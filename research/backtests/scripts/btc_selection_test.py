"""The honest test for BTC: can any of this be chosen in advance?

BTC's grid said its lever is the stop, not a trend line, and its consolidation rule sat on a cliff edge. So
the candidates are the stop and giveback retunes, each with and without Mode C - chosen from the six months
before each test window, never with knowledge of the window being scored.
"""

from __future__ import annotations

import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import three_modes as three

three.COIN = "btc"
BTC_C = dict(chart=10, bars=20, zone=0.3, confirm=1, stop=2.0, arm=1.283, giveback=22.0)
EXITS = [(3.0, 14.0), (4.0, 14.0), (5.0, 14.0), (3.0, 50.0), (4.5, 50.0), (5.0, 50.0)]
TESTS = [f"wf{i}_test" for i in range(len(research.TESTS))]
TRAINS = [f"wf{i}_train" for i in range(len(research.TESTS))]


def main() -> None:
    raw = replay.load_raw("BTCUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    pd.set_option("display.width", 250)

    candidates = {}
    for mode_c in (None, BTC_C):
        tag = "with Mode C" if mode_c else "no Mode C"
        for stop, give in EXITS:
            trades = three.build(raw, bullish, None, set(), mode_c=mode_c, dip_stop=stop, dip_giveback=give)
            candidates[f"stop -{stop:g}/give {give:g}, {tag}"] = {
                name: three.account(trades, *research.WINDOWS[name], 7.5 / 10_000)["profit"]
                for name in (*TRAINS, *TESTS)}
    deployed = "stop -3/give 14, no Mode C"

    picks, rows = [], []
    for index in range(len(TESTS)):
        train, test = TRAINS[index], TESTS[index]
        chosen = max(candidates, key=lambda name: candidates[name][train])
        picks.append(chosen)
        rows.append({"window": research.TESTS[index][0], "chosen on training data": chosen,
                     "it earned": round(candidates[chosen][test], 2),
                     "deployed earned": round(candidates[deployed][test], 2),
                     "deployed + Mode C": round(candidates["stop -3/give 14, with Mode C"][test], 2)})
    print("=== what a rule chosen in advance would have earned, window by window")
    print(pd.DataFrame(rows).to_string(index=False))

    totals = {
        "picked in advance (honest)": sum(candidates[name][test] for name, test in zip(picks, TESTS)),
        "deployed, no choice made": sum(candidates[deployed][test] for test in TESTS),
        "deployed + Mode C, fixed": sum(candidates["stop -3/give 14, with Mode C"][test] for test in TESTS),
        "stop -3/give 50, no Mode C": sum(candidates["stop -3/give 50, no Mode C"][test] for test in TESTS),
        "oracle (hindsight)": sum(max(candidates[name][test] for name in candidates) for test in TESTS),
    }
    print("\n=== totals across the six out-of-sample windows")
    for name, value in totals.items():
        print(f"  {name:<30} ${value:8.2f}")

    print("\n=== does Mode C help BTC, whatever the exit numbers are?")
    rows = []
    for stop, give in EXITS:
        a, b = f"stop -{stop:g}/give {give:g}, with Mode C", f"stop -{stop:g}/give {give:g}, no Mode C"
        wins = sum(candidates[a][test] > candidates[b][test] for test in TESTS)
        rows.append({"exit": f"stop -{stop:g}/give {give:g}", "windows Mode C improved": f"{wins}/6",
                     "total added": round(sum(candidates[a][test] - candidates[b][test] for test in TESTS), 2)})
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
