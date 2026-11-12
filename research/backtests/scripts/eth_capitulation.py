"""ETH capitulation reversal: buy when a sharp sell-off's forced selling runs out.

Hourly bars, built from 1-minute data (volume and taker-buy volume from Binance; taker SELL = volume - taker buy):

  drop      the hour's close is at least D% below the highest high of the previous 24 hours
  climax    that hour's aggressive selling (taker-sell volume) is at least M x its 7-day hourly average
  turn      the NEXT hour closes green (close > open) with taker selling below half the climax hour's
  buy       the first minute after the turn hour closes; at most one entry per 24 hours
  exits     "dip"   the deployed dip exit: stop -4.5%, trail arms +1.315%, gives back 30%, Mode A in uptrends
            "wide"  the same trail with a -8% stop - capitulation bounces are violent and a tight stop may be
                    hit by the last flush

No downtrend filter and no blocked hours: a capitulation happens BECAUSE the market is breaking down, and the
core's filters were fitted to a different rule. Measured beside the plan (core 5 + pullback 2): one shared
wallet, hourly mark-to-market drawdown - the same machinery as the regime and catch-up tests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import eth_pullback as pb
import eth_regime as rg
import eth_catchup as cu
import eth_volume_filter as vf

LOT, FEE = 100.0, 7.5 / 10_000
TESTS, TRAINS = cu.TESTS, cu.TRAINS
CORE, PULL, CAP = {"dip", "breakout"}, {"pullback"}, {"capitulation"}
PRIORITY = {"dip": 0, "breakout": 0, "pullback": 1, "capitulation": 2}
DROPS, CLIMAX = [5.0, 7.0, 9.0], [3.0, 5.0]


class Events:
    def __init__(self, vol):
        v = vol.set_index("open_time")
        h = pd.DataFrame({"open": v.open.resample("1h").first(), "high": v.high.resample("1h").max(),
                          "low": v.low.resample("1h").min(), "close": v.close.resample("1h").last(),
                          "volume": v.volume.resample("1h").sum(),
                          "taker_buy": v.taker_buy_base_volume.resample("1h").sum(),
                          "n": v.close.resample("1h").size()})
        h = h[h.n == 60]
        h["sell"] = h.volume - h.taker_buy
        h["prior_high"] = h.high.rolling(24).max().shift(1)
        h["sell_avg"] = h.sell.rolling(24 * 7).mean().shift(1)
        self.h = h
        self.act = np.searchsorted(grid.TIMES, h.index + pd.Timedelta(hours=1))   # first minute after each hour

    def signals(self, drop, climax):
        h = self.h
        down = (h.close / h.prior_high - 1 <= -drop / 100).to_numpy()
        spike = (h.sell >= climax * h.sell_avg).to_numpy()
        green_next = np.r_[(h.close > h.open).to_numpy()[1:], False]
        calm_next = np.r_[h.sell.to_numpy()[1:] < 0.5 * h.sell.to_numpy()[:-1], False]
        turn = np.flatnonzero(down & spike & green_next & calm_next) + 1          # the turn hour
        kept, last = [], -10**9
        for t in turn:
            if t < len(self.act) and self.act[t] < len(grid.OPEN) - 1 and t - last >= 24:
                kept.append(t)
                last = t
        return np.asarray(kept, dtype=np.int64)


def build(events, bullish, ema, drop, climax, exit_style):
    rule = live.load_rule("eth")
    stop = 4.5 if exit_style == "dip" else 8.0
    trades = []
    for turn in events.signals(drop, climax):
        entry = int(events.act[turn])
        line = ema if bullish[entry] else None
        out, price, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], stop, line)
        trades.append((entry, int(out), float(price), "capitulation"))
    return trades


def simulate(trades, pots, start, end, idle_only=False):
    initial = sum(n for n, _ in pots) * LOT
    wallet, slots, taken = initial, [[] for _ in pots], []
    for entry, exit_index, price, source in trades:
        if not (start <= grid.TIMES[entry] < end):
            continue
        for p in range(len(pots)):
            wallet += sum(s[1] for s in slots[p] if s[0] <= entry)
            slots[p] = [s for s in slots[p] if s[0] > entry]
        if exit_index < 0 or (idle_only and source in CAP and any(slots)):
            continue
        for p, (lots, sources) in enumerate(pots):
            if source in sources and len(slots[p]) < lots and wallet >= LOT:
                fill = grid.OPEN[entry] * (1 + grid.SLIP)
                qty = LOT / (fill * (1 + FEE))
                proceeds = qty * price * (1 - grid.SLIP) * (1 - FEE)
                wallet -= LOT
                slots[p].append((exit_index, proceeds))
                taken.append((entry, exit_index, qty, proceeds, source))
                break
    return cu._finish(taken, wallet, slots, pots, initial, start, end)


def evaluate(label, trades, pots, idle_only=False):
    runs = {n: simulate(trades, pots, *research.WINDOWS[n], idle_only) for n in ("full", "earlier", "later", "unseen", *TESTS)}
    full, ledger = runs["full"], runs["full"]["ledger"]
    wf = [runs[w]["profit"] for w in TESTS]
    sub = ledger[ledger.source.isin(CAP)] if len(ledger) else ledger
    return {"design": label, "capital": int(full["capital"]),
            "core": int(ledger.source.isin(CORE).sum()) if len(ledger) else 0,
            "pull": int(ledger.source.isin(PULL).sum()) if len(ledger) else 0,
            "capit": len(sub), "capit_pnl": round(sub.pnl.sum(), 2) if len(sub) else 0.0,
            "capit_win%": round(100 * (sub.pnl > 0).mean(), 1) if len(sub) else 0.0,
            "profit": round(full["profit"], 2), "earlier": round(runs["earlier"]["profit"], 2),
            "later": round(runs["later"]["profit"], 2), "unseen": round(runs["unseen"]["profit"], 2),
            "walk_forward": round(sum(wf), 2), "wf_windows": f"{sum(x > 0 for x in wf)}/6",
            "mtm_dd%": round(full["dd"], 2), "mtm_dd$": round(full["dd_usd"], 2)}


def main() -> None:
    raw, bullish, ema, mode_c = pb.setup()
    vol = vf.load_raw_volume()
    vol = vol[vol.open_time < research.T("2026-09-11")].reset_index(drop=True)
    assert len(vol) == len(raw) and (vol.open_time.values == raw.open_time.values).all(), "volume rows misaligned"
    events = Events(vol)
    core = pb.build(raw, bullish, ema, mode_c)
    pull = [t for t in pb.build(raw, bullish, ema, [], pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES))
            if t[3] == "pullback"]
    key = lambda t: (t[0], PRIORITY[t[3]])
    book = lambda *parts: sorted([t for part in parts for t in part], key=key)
    plan, base = book(core, pull), [(5, CORE), (2, PULL)]
    plan_row = evaluate("plan", plan, base)
    pd.set_option("display.width", 340)

    print("=== how many capitulation events each setting finds (full window)")
    inside = lambda idx: int(((events.h.index[idx] >= research.WINDOWS["full"][0]) &
                              (events.h.index[idx] < research.WINDOWS["full"][1])).sum())
    print(pd.DataFrame([{"drop": d, "climax x": m, "events": inside(events.signals(d, m))}
                        for d in DROPS for m in CLIMAX]).to_string(index=False))

    print("\n=== 1. the rule on its own 3 lots, beside the plan (is it any good?)")
    rows = []
    for exit_style in ("dip", "wide"):
        for d in DROPS:
            for m in CLIMAX:
                r = evaluate(f"{exit_style} exit, drop {d:g}%, climax {m:g}x",
                             book(core, pull, build(events, bullish, ema, d, m, exit_style)), base + [(3, CAP)])
                r["adds_profit"] = round(r["profit"] - plan_row["profit"], 2)
                r["adds_wf"] = round(r["walk_forward"] - plan_row["walk_forward"], 2)
                rows.append(r)
    frame = pd.DataFrame(rows).set_index("design")
    print(frame[["capit", "capit_pnl", "capit_win%", "adds_profit", "adds_wf", "wf_windows", "earlier",
                 "later", "unseen", "mtm_dd$"]].to_string())

    best = frame.adds_wf.idxmax()
    exit_style = best.split(" exit")[0]
    d = float(best.split("drop ")[1].split("%")[0])
    m = float(best.split("climax ")[1].rstrip("x"))
    trades = build(events, bullish, ema, d, m, exit_style)
    print(f"\n(hindsight best on walk-forward: {best} - used below only to compare the ways of organising it)")

    print("\n=== 2. every way to organise it beside the plan (core 5 + pullback 2)")
    rows = [evaluate("PLAN core 5 + pullback 2", plan, base)]
    for k in (1, 2, 3):
        rows.append(evaluate(f"CONTROL +{k} pullback lots", plan, [(5, CORE), (2 + k, PULL)]))
    for k in (1, 2, 3):
        rows.append(evaluate(f"+ capitulation sleeve {k} x $100", book(core, pull, trades), base + [(k, CAP)]))
    rows.append(evaluate("capitulation SHARES the core's 5 lots", book(core, pull, trades), [(5, CORE | CAP), (2, PULL)]))
    rows.append(evaluate("capitulation SHARES the pullback's 2 lots", book(core, pull, trades), [(5, CORE), (2, PULL | CAP)]))
    rows.append(evaluate("+ capitulation 2 x $100, only when book is idle", book(core, pull, trades), base + [(2, CAP)], True))
    print(pd.DataFrame(rows).set_index("design").to_string())

    print("\n=== 3. honest selection test: pick exit / drop / climax on the 6 months before each window")
    settings = {(e, dd, mm): build(events, bullish, ema, dd, mm, e) for e in ("dip", "wide") for dd in DROPS for mm in CLIMAX}
    plan_w = {w: simulate(plan, base, *research.WINDOWS[w])["profit"] for w in (*TRAINS, *TESTS)}
    for k in (1, 2, 3):
        score = {s: {w: simulate(book(core, pull, v), base + [(k, CAP)], *research.WINDOWS[w])["profit"] - plan_w[w]
                     for w in (*TRAINS, *TESTS)} for s, v in settings.items()}
        control = {w: simulate(plan, [(5, CORE), (2 + k, PULL)], *research.WINDOWS[w])["profit"] - plan_w[w] for w in TESTS}
        table, picks = [], []
        for i, test in enumerate(TESTS):
            pick = max(score, key=lambda s: score[s][TRAINS[i]])
            picks.append(pick)
            table.append({"window": research.TESTS[i][0], "chosen": f"{pick[0]} / {pick[1]:g}% / {pick[2]:g}x",
                          "capitulation added": round(score[pick][test], 2),
                          f"+{k} pullback lot(s) added": round(control[test], 2)})
        honest = sum(score[s][t] for s, t in zip(picks, TESTS))
        print(f"\n--- capitulation sleeve of {k} x $100")
        print(pd.DataFrame(table).to_string(index=False))
        print(f"  capitulation, picked in advance  ${honest:8.2f}  positive {sum(score[s][t] > 0 for s, t in zip(picks, TESTS))}/6")
        print(f"  +{k} pullback lot(s) instead      ${sum(control.values()):8.2f}  positive {sum(v > 0 for v in control.values())}/6")


if __name__ == "__main__":
    main()
