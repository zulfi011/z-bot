"""The decisive sleeve test: with the core already at its 5-lot saturation point, does a pullback sleeve beat
simply adding more core lots (which by then earn almost nothing)? Shared wallet, as on Binance."""
from __future__ import annotations
import pandas as pd
import run_eth_full_research as research, run_sol_stage3_space_grid as grid
import eth_pullback as pb, eth_sleeves as sl

raw, bullish, ema, mode_c = pb.setup()
core = pb.build(raw, bullish, ema, mode_c)
pd.set_option("display.width", 320)
BASE = 5


def pull(hours, dwell):
    entries = pb.pullback_entries(grid.CLOSE, bullish, hours, dwell, grid.TIMES)
    return [t for t in pb.build(raw, bullish, ema, [], entries) if t[3] == "pullback"]


def merged(extra):
    return sorted(core + extra, key=lambda t: (t[0], t[3] == "pullback"))


fixed = pull(24, 180)
rows = [sl.evaluate(f"core {BASE} x $100 (saturated core)", core, [(BASE, sl.CORE)])]
for n in (1, 2, 3):
    rows.append(sl.evaluate(f"CONTROL core {BASE + n} x $100", core, [(BASE + n, sl.CORE)]))
    rows.append(sl.evaluate(f"core {BASE} + pullback sleeve {n} x $100", merged(fixed), [(BASE, sl.CORE), (n, sl.PULL)]))
print(f"=== full history, pullback EMA 24h / dwell 180m (the hindsight pick)")
print(pd.DataFrame(rows).set_index("design").to_string())

settings = {(h, d): pull(h, d) for h in pb.HOURS for d in pb.DWELL}
alone = {w: sl.simulate(core, [(BASE, sl.CORE)], *research.WINDOWS[w])["profit"] for w in (*sl.TRAINS, *sl.TESTS)}
for n in (1, 2, 3):
    score = {k: {w: sl.simulate(merged(v), [(BASE, sl.CORE), (n, sl.PULL)], *research.WINDOWS[w])["profit"] - alone[w]
                 for w in (*sl.TRAINS, *sl.TESTS)} for k, v in settings.items()}
    control = {w: sl.simulate(core, [(BASE + n, sl.CORE)], *research.WINDOWS[w])["profit"] - alone[w] for w in sl.TESTS}
    table, picks = [], []
    for i, test in enumerate(sl.TESTS):
        pick = max(score, key=lambda k: score[k][sl.TRAINS[i]])
        picks.append(pick)
        table.append({"window": research.TESTS[i][0], "setting chosen": f"EMA {pick[0]}h / {pick[1]}m",
                      "sleeve added": round(score[pick][test], 2),
                      f"{n} more core lot(s) added": round(control[test], 2),
                      "sleeve better?": "yes" if score[pick][test] > control[test] else "no"})
    honest = sum(score[k][t] for k, t in zip(picks, sl.TESTS))
    beat = sum(score[k][t] > control[t] for k, t in zip(picks, sl.TESTS))
    positive = sum(score[k][t] > 0 for k, t in zip(picks, sl.TESTS))
    print(f"\n--- on top of core {BASE}: sleeve of {n} x $100, honest selection")
    print(pd.DataFrame(table).to_string(index=False))
    print(f"  sleeve, picked in advance   ${honest:8.2f}   positive {positive}/6, beat the control {beat}/6")
    print(f"  sleeve, 24h/180m fixed      ${sum(score[(24, 180)][t] for t in sl.TESTS):8.2f}")
    print(f"  {n} more core lot(s)         ${sum(control.values()):8.2f}")
