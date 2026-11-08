"""The honest test for TRX: choose the exit numbers and Mode C from the six months before each test window.

TRX's lever is not a trend line - every EMA made it worse - but the giveback and the arm point. So the
candidate set is the exit retunes its own grid liked, each with and without Mode C. Narrow and reasoned, so
the test measures an idea rather than the noise in 2,000 combinations.
"""

from __future__ import annotations

import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import three_modes as three

three.COIN = "trx"
TRX_C = dict(chart=60, bars=40, zone=2.0, confirm=3, stop=3.0, arm=1.283, giveback=22.0)
EXITS = [(1.245, 10.0), (1.245, 40.0), (1.245, 50.0), (2.5, 40.0), (3.0, 40.0), (3.0, 50.0)]
TESTS = [f"wf{i}_test" for i in range(len(research.TESTS))]
TRAINS = [f"wf{i}_train" for i in range(len(research.TESTS))]


def main() -> None:
    rule = live.load_rule("trx")
    raw = replay.load_raw("TRXUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    pd.set_option("display.width", 250)

    candidates = {}
    for mode_c in (None, TRX_C):
        tag = "with Mode C" if mode_c else "no Mode C"
        for arm, give in EXITS:
            trades = three.build(raw, bullish, None, set(), mode_c=mode_c, dip_stop=rule["stop_pct"],
                                 dip_arm=arm, dip_giveback=give)
            candidates[f"arm {arm:g}/give {give:g}, {tag}"] = {
                name: three.account(trades, *research.WINDOWS[name], 7.5 / 10_000)["profit"]
                for name in (*TRAINS, *TESTS)}
    deployed = "arm 1.245/give 10, no Mode C"
    print(f"{len(candidates)} candidates\n")

    picks, rows = [], []
    for index in range(len(TESTS)):
        train, test = TRAINS[index], TESTS[index]
        chosen = max(candidates, key=lambda name: candidates[name][train])
        picks.append(chosen)
        rows.append({"window": research.TESTS[index][0], "chosen on training data": chosen,
                     "it earned": round(candidates[chosen][test], 2),
                     "deployed earned": round(candidates[deployed][test], 2),
                     "deployed + Mode C": round(candidates["arm 1.245/give 10, with Mode C"][test], 2),
                     "best possible": round(max(candidates[name][test] for name in candidates), 2)})
    print("=== what a rule chosen in advance would have earned, window by window")
    print(pd.DataFrame(rows).to_string(index=False))

    totals = {
        "picked in advance (honest)": sum(candidates[name][test] for name, test in zip(picks, TESTS)),
        "deployed, no choice made": sum(candidates[deployed][test] for test in TESTS),
        "deployed exit + Mode C, fixed": sum(candidates["arm 1.245/give 10, with Mode C"][test] for test in TESTS),
        "best retune + Mode C, fixed": sum(candidates["arm 3/give 50, with Mode C"][test] for test in TESTS),
        "best retune, no Mode C, fixed": sum(candidates["arm 3/give 50, no Mode C"][test] for test in TESTS),
        "oracle (hindsight)": sum(max(candidates[name][test] for name in candidates) for test in TESTS),
    }
    print("\n=== totals across the six out-of-sample windows")
    for name, value in totals.items():
        print(f"  {name:<32} ${value:8.2f}")

    print("\n=== does Mode C help, whatever the exit numbers are?")
    rows = []
    for arm, give in EXITS:
        with_c, without = f"arm {arm:g}/give {give:g}, with Mode C", f"arm {arm:g}/give {give:g}, no Mode C"
        wins = sum(candidates[with_c][test] > candidates[without][test] for test in TESTS)
        rows.append({"exit": f"arm {arm:g}/give {give:g}", "windows Mode C improved": f"{wins}/6",
                     "total added": round(sum(candidates[with_c][test] - candidates[without][test] for test in TESTS), 2)})
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
