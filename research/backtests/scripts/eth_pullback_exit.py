"""Which exit suits ETH's pullback lots? Only the pullback lots' exit changes; the core and everything else stay
exactly as deployed (core 5 + pullback 2 x $100, shared wallet, BNB fees, hourly mark-to-market).

Deployed pullback exit (borrowed from the dip): stop -4.5%, trail arms +1.315%, then held against the 16-hour EMA
(Mode A, since every pullback lot is bought in an uptrend).

Tested: the trend line 8 / 12 / 16 / 24 / 36 / 48 hours, the stop 3 / 4.5 / 6%, and the plain 30% giveback trail
(Mode B) instead of any line. Then the honest test: choose the exit on the six months before each window.
"""
from __future__ import annotations
import pandas as pd
import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research, run_sol_stage3_space_grid as grid
import eth_pullback as pb, eth_regime as rg

HOURS = [8, 12, 16, 24, 36, 48]
STOPS = [3.0, 4.5, 6.0]
DEPLOYED = ("EMA 16h", 4.5)
BASE = [(5, rg.CORE), (2, rg.PULL)]


def main() -> None:
    raw, bullish, ema16, mode_c = pb.setup()
    core = pb.build(raw, bullish, ema16, mode_c)
    rule = live.load_rule("eth")
    entries = pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES)
    lines = {h: pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy() for h in HOURS}

    def pullback_trades(exit_name, stop):
        line = None if exit_name == "giveback 30%" else lines[int(exit_name.split()[1].rstrip("h"))]
        out = []
        for entry in entries:
            entry = int(entry)
            use = line if bullish[entry] else None
            o, p, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], stop, use)
            out.append((entry, o, p, "pullback"))
        return sorted(core + out, key=lambda t: (t[0], rg.PRIORITY[t[3]]))

    settings = {(f"EMA {h}h", s): pullback_trades(f"EMA {h}h", s) for h in HOURS for s in STOPS}
    settings.update({("giveback 30%", s): pullback_trades("giveback 30%", s) for s in STOPS})
    windows = ("full", "unseen", *rg.TESTS, *[f"wf{i}_train" for i in range(6)])
    runs = {k: {w: rg.simulate(v, BASE, *research.WINDOWS[w]) for w in windows} for k, v in settings.items()}
    base = runs[DEPLOYED]

    rows = []
    for key, r in runs.items():
        led = r["full"]["ledger"]
        pl = led[led.source == "pullback"]
        wins, losses = pl[pl.pnl > 0], pl[pl.pnl <= 0]
        wf = {w: r[w]["profit"] for w in rg.TESTS}
        rows.append({"exit": key[0], "stop": key[1], "pull_trades": len(pl),
                     "pull_win%": round(100 * (pl.pnl > 0).mean(), 1), "pull_avg_win": round(wins.pnl.mean(), 2),
                     "pull_avg_loss": round(losses.pnl.mean(), 2), "pull_pnl": round(pl.pnl.sum(), 2),
                     "plan_profit": round(r["full"]["profit"], 2), "walk_forward": round(sum(wf.values()), 2),
                     "wf_windows": f"{sum(v > 0 for v in wf.values())}/6",
                     "beats_deployed": f"{sum(wf[w] > base[w]['profit'] for w in rg.TESTS)}/6",
                     "unseen": round(r["unseen"]["profit"], 2), "mtm_dd%": round(r["full"]["dd"], 2)})
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    pd.set_option("display.width", 260)
    print("=== every pullback exit, inside the plan (deployed = EMA 16h, stop 4.5)")
    print(frame.to_string(index=False))

    print("\n=== honest test: choose the pullback exit on the six months before each window")
    picks, table = [], []
    for i, test in enumerate(rg.TESTS):
        train = f"wf{i}_train"
        pick = max(runs, key=lambda k: runs[k][train]["profit"])
        picks.append(pick)
        table.append({"window": research.TESTS[i][0], "chosen": f"{pick[0]}, stop {pick[1]:g}%",
                      "it earned": round(runs[pick][test]["profit"], 2), "deployed earned": round(base[test]["profit"], 2)})
    print(pd.DataFrame(table).to_string(index=False))
    honest = sum(runs[k][t]["profit"] for k, t in zip(picks, rg.TESTS))
    deployed = sum(base[t]["profit"] for t in rg.TESTS)
    print(f"\n  picked in advance (honest)  ${honest:8.2f}")
    print(f"  deployed exit, no choice    ${deployed:8.2f}")
    print(f"  oracle (hindsight)          ${sum(max(runs[k][t]['profit'] for k in runs) for t in rg.TESTS):8.2f}")


if __name__ == "__main__":
    main()
