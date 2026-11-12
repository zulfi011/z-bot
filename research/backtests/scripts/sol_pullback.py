"""Does the pullback entry help SOL, and on what settings?

The same third way in that was built for ETH, but tuned from scratch for SOL (never transplant another coin's
numbers): in an uptrend (7d > 15d > 30d), 1-minute closes below an N-hour EMA for at least `dwell` minutes, then
the first close back above it buys at the next minute. SOL's blocked hours (06:00-12:00 UTC) apply.

Everything else is SOL as deployed: dip on 3-minute candles at the 12-day average, Mode C (60-minute chart, 24
bars, <=2.0%, no wait, -4% stop), exits stop -2% / trail +1.251% / giveback 12%, and Mode A on the 8-hour line
for any lot opened in a clean uptrend - pullback lots included.

Measured with the live buying rule (a full lot, or what the wallet has left), hourly windows as everywhere else.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_pullback as pb
import eth_regime as rg

COIN, SYMBOL = "sol", "SOLUSDT"
MODE_C = dict(chart=60, bars=24, zone=2.0, confirm=0, stop=4.0, arm=1.283, giveback=22.0)
EMA_HOURS = 8                      # SOL's deployed Mode A line
HOURS = [4, 8, 12, 24, 36, 48]
DWELL = [15, 60, 180]
FEE, MIN_ORDER = 7.5 / 10_000, 5.0
CORE, PULL = {"dip", "breakout"}, {"pullback"}


def setup():
    raw = replay.load_raw(SYMBOL, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=EMA_HOURS * 60, adjust=False).mean().to_numpy()
    return raw, bullish, ema


def core_trades(raw, bullish, ema):
    """SOL as deployed: the dip and Mode C, both exiting on Mode A when opened in an uptrend."""
    rule = live.load_rule(COIN)
    trades = []
    for entry in live.live_entries(raw, rule):
        entry = int(entry)
        out, price, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"],
                                  ema if bullish[entry] else None)
        trades.append((entry, out, price, "dip"))
    high, low, open_, close, last_minute = v4.bars_for(raw, MODE_C["chart"])
    entries = v4.entries_for(high, low, close, last_minute, MODE_C["bars"], MODE_C["zone"], MODE_C["confirm"],
                             grid.CLOSE, len(raw))
    hours = grid.TIMES[entries].hour
    blocked = rule["blocked"]
    if blocked:
        entries = entries[~((hours >= blocked[0]) & (hours < blocked[1]))]
    for entry in entries:
        entry = int(entry)
        out, price, _ = opt.trade(entry, MODE_C["arm"], MODE_C["giveback"], MODE_C["stop"],
                                  ema if bullish[entry] else None)
        trades.append((entry, out, price, "breakout"))
    return sorted(trades, key=lambda t: t[0])


def pullback_trades(bullish, ema, hours, dwell, stop=None):
    rule = live.load_rule(COIN)
    entries = pb.pullback_entries(grid.CLOSE, bullish, hours, dwell, grid.TIMES, blocked=rule["blocked"])
    out = []
    for entry in entries:
        entry = int(entry)
        o, p, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], stop or rule["stop_pct"],
                            ema if bullish[entry] else None)
        out.append((entry, o, p, "pullback"))
    return out


def simulate(trades, pots, lot, start, end):
    """pots: list of (lots, sources). One shared wallet, the live buying rule."""
    wallet, slots, taken = sum(n for n, _ in pots) * lot, [[] for _ in pots], []
    for entry, exit_index, price, source in trades:
        if not (start <= grid.TIMES[entry] < end):
            continue
        for p in range(len(pots)):
            wallet += sum(s[1] for s in slots[p] if s[0] <= entry)
            slots[p] = [s for s in slots[p] if s[0] > entry]
        if exit_index < 0 or wallet < MIN_ORDER:
            continue
        for p, (lots, sources) in enumerate(pots):
            if source in sources and len(slots[p]) < lots:
                spend = min(lot, np.floor(wallet * 100) / 100)
                fill = grid.OPEN[entry] * (1 + grid.SLIP)
                proceeds = spend / (fill * (1 + FEE)) * price * (1 - grid.SLIP) * (1 - FEE)
                wallet -= spend
                slots[p].append((exit_index, proceeds))
                taken.append({"source": source, "pnl": proceeds - spend})
                break
    for p in range(len(pots)):
        wallet += sum(s[1] for s in slots[p])
    return {"profit": wallet - sum(n for n, _ in pots) * lot, "ledger": pd.DataFrame(taken)}


def score(label, trades, pots, lot=100.0):
    runs = {w: simulate(trades, pots, lot, *research.WINDOWS[w]) for w in ("full", "earlier", "later", "unseen", *rg.TESTS)}
    led = runs["full"]["ledger"]
    wf = [runs[w]["profit"] for w in rg.TESTS]
    pull = led[led.source == "pullback"] if len(led) else led
    return {"setup": label, "money": int(sum(n for n, _ in pots) * lot), "trades": len(led),
            "pullback": len(pull), "pullback_pnl": round(pull.pnl.sum(), 2) if len(pull) else 0.0,
            "win%": round(100 * (led.pnl > 0).mean(), 1) if len(led) else 0.0,
            "profit": round(runs["full"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "windows": f"{sum(x > 0 for x in wf)}/6", "later": round(runs["later"]["profit"], 2),
            "unseen": round(runs["unseen"]["profit"], 2)}


def main() -> None:
    raw, bullish, ema = setup()
    core = core_trades(raw, bullish, ema)
    pd.set_option("display.width", 260)
    book = lambda *parts: sorted([t for p in parts for t in p], key=lambda t: (t[0], rg.PRIORITY[t[3]]))

    print("=== SOL as deployed (dip + Mode C), live buying rule")
    print(pd.DataFrame([score(f"core only, {n} x $100", core, [(n, CORE)]) for n in (1, 3, 5)])
          .set_index("setup").to_string())

    print("\n=== 1. every pullback setting, sharing SOL's 3 lots")
    rows, sets = [], {}
    for hours in HOURS:
        for dwell in DWELL:
            sets[(hours, dwell)] = pullback_trades(bullish, ema, hours, dwell)
            rows.append(score(f"EMA {hours}h, dwell {dwell}m", book(core, sets[(hours, dwell)]), [(3, CORE | PULL)]))
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").to_string())
    best = frame.iloc[0]["setup"]
    key = (int(best.split("EMA ")[1].split("h")[0]), int(best.split("dwell ")[1].rstrip("m")))
    print(f"\n(best on walk-forward: {best})")

    print("\n=== 2. the best setting at different sizes, shared vs its own lots")
    rows = []
    for n in (1, 3, 5):
        rows.append(score(f"core only, {n} x $100", core, [(n, CORE)]))
        rows.append(score(f"shared {n} lots, with pullback", book(core, sets[key]), [(n, CORE | PULL)]))
    for core_n, pull_n in ((3, 1), (3, 2), (5, 1), (5, 2)):
        rows.append(score(f"core {core_n} + pullback {pull_n} (own lots)", book(core, sets[key]),
                          [(core_n, CORE), (pull_n, PULL)]))
        rows.append(score(f"CONTROL core {core_n + pull_n} only", core, [(core_n + pull_n, CORE)]))
    print(pd.DataFrame(rows).set_index("setup").to_string())

    print("\n=== 3. honest test: choose the pullback setting on the six months before each window (3 shared lots)")
    base = {w: simulate(core, [(3, CORE)], 100.0, *research.WINDOWS[w])["profit"]
            for w in (*[f"wf{i}_train" for i in range(6)], *rg.TESTS)}
    scores = {k: {w: simulate(book(core, v), [(3, CORE | PULL)], 100.0, *research.WINDOWS[w])["profit"] - base[w]
                  for w in (*[f"wf{i}_train" for i in range(6)], *rg.TESTS)} for k, v in sets.items()}
    picks, table = [], []
    for i, test in enumerate(rg.TESTS):
        pick = max(scores, key=lambda k: scores[k][f"wf{i}_train"])
        picks.append(pick)
        table.append({"window": research.TESTS[i][0], "chosen": f"EMA {pick[0]}h / {pick[1]}m",
                      "pullback added": round(scores[pick][test], 2)})
    print(pd.DataFrame(table).to_string(index=False))
    honest = sum(scores[k][t] for k, t in zip(picks, rg.TESTS))
    print(f"\n  pullback, picked in advance   ${honest:8.2f}  positive {sum(scores[k][t] > 0 for k, t in zip(picks, rg.TESTS))}/6")
    print(f"  best setting fixed ({key[0]}h/{key[1]}m)  ${sum(scores[key][t] for t in rg.TESTS):8.2f}")


if __name__ == "__main__":
    main()
