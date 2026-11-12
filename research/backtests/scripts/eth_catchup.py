"""ETH catch-up to BTC: buy ETH when BTC is trending up but ETH has fallen behind it.

The BTC-relative GATE failed because ETH's best trades begin while ETH is still LAGGING BTC - requiring ETH
to be strong made it buy late. This flips that finding into an entry.

  BTC trend   BTC's daily averages stacked 7d > 15d > 30d (completed days, effective the next UTC day)
  ETH lag     the hourly ETH/BTC ratio sits at least X% below its own N-day average
  ETH health  ETH's own averages are NOT stacked downward (7d < 15d < 30d) - lagging, not breaking down
  buy         the first hour the three hold together; next minute's open
  exits       "dip"    the deployed dip exit (stop -4.5%, trail +1.315% / 30%, Mode A in ETH uptrends)
              "revert" sell once the ratio is back at its average (the catch-up is complete); stop -4.5%

No blocked hours: those were fitted to the dip entry, and a new rule should not inherit another rule's fit.
Measured alone and beside the planned book (core 5 + pullback 2), one shared wallet, hourly mark-to-market.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_pullback as pb
import eth_regime as rg

LOT, FEE = 100.0, 7.5 / 10_000
TESTS = [f"wf{i}_test" for i in range(len(research.TESTS))]
TRAINS = [f"wf{i}_train" for i in range(len(research.TESTS))]
CORE, PULL, CATCH = {"dip", "breakout"}, {"pullback"}, {"catchup"}
PRIORITY = {"dip": 0, "breakout": 0, "pullback": 1, "catchup": 2}
LOOKBACK, LAG = [7, 14, 30], [2.0, 3.0, 5.0]


def daily_stack(raw, bearish=False):
    """Per-day flag, effective the day after the last completed day it uses."""
    day = raw.open_time.dt.floor("D")
    g = raw.groupby(day).agg(close=("close", "last"), n=("close", "size"))
    close = g[g.n == 1440].close
    a7, a15, a30 = (close.rolling(n).mean() for n in (7, 15, 30))
    flag = (a7 < a15) & (a15 < a30) if bearish else (a7 > a15) & (a15 > a30)
    flag = flag[a30.notna()]
    flag.index = flag.index + pd.Timedelta(days=1)
    return flag


class Signals:
    def __init__(self, raw, btc):
        eth_h = raw.set_index("open_time").close.resample("1h").last()
        btc_h = btc.set_index("open_time").close.resample("1h").last()
        frame = pd.concat({"eth": eth_h, "btc": btc_h}, axis=1).dropna()
        frame["ratio"] = frame.eth / frame.btc
        days = frame.index.floor("D")
        frame["btc_up"] = days.map(daily_stack(btc)).fillna(False).astype(bool).to_numpy()
        frame["eth_down"] = days.map(daily_stack(raw, bearish=True)).fillna(True).astype(bool).to_numpy()
        self.frame = frame
        # the minute index where each hour's signal can be acted on: the first minute of the next hour
        self.act = np.searchsorted(grid.TIMES, frame.index + pd.Timedelta(hours=1))

    def deviation(self, days):
        mean = self.frame.ratio.rolling(days * 24).mean().shift(1)
        return (self.frame.ratio / mean - 1).to_numpy()

    def entries(self, days, lag):
        dev = self.deviation(days)
        on = (dev <= -lag / 100) & self.frame.btc_up.to_numpy() & ~self.frame.eth_down.to_numpy()
        first = on & ~np.r_[False, on[:-1]]
        where = np.flatnonzero(first)
        where = where[self.act[where] < len(grid.OPEN) - 1]
        return where


def build(sig, bullish, ema, days, lag, exit_style, copies=1):
    rule = live.load_rule("eth")
    dev = sig.deviation(days)
    trades = []
    for hour in sig.entries(days, lag):
        entry = int(sig.act[hour])
        if exit_style == "dip":
            line = ema if bullish[entry] else None
            out, price, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], 4.5, line)
        else:
            back = np.flatnonzero(dev[hour + 1:] >= 0)
            out = int(sig.act[hour + 1 + back[0]]) if len(back) else -1
            if out >= len(grid.OPEN):
                out = -1
            price = grid.OPEN[out] if out >= 0 else np.nan
            level = grid.OPEN[entry] * (1 + grid.SLIP) * (1 - 0.045)
            end = out if out >= 0 else len(grid.LOW)
            hit = np.flatnonzero(grid.LOW[entry:end] <= level)
            if len(hit):
                out = entry + int(hit[0])
                price = min(level, grid.OPEN[out])
        trades += [(entry, int(out), float(price), "catchup")] * copies
    return trades


def simulate(trades, pots, start, end, idle_only=False):
    """rg.simulate with the idle-only rule applied to the catch-up source."""
    if not idle_only:
        return rg.simulate(trades, pots, start, end)
    kept, busy_until = [], []
    for t in trades:           # pre-pass is not exact under slot limits, so do it inside a copy of the loop
        kept.append(t)
    initial = sum(n for n, _ in pots) * LOT
    wallet, slots, taken = initial, [[] for _ in pots], []
    for entry, exit_index, price, source in trades:
        if not (start <= grid.TIMES[entry] < end):
            continue
        for p in range(len(pots)):
            wallet += sum(s[1] for s in slots[p] if s[0] <= entry)
            slots[p] = [s for s in slots[p] if s[0] > entry]
        if exit_index < 0 or (source in CATCH and any(slots)):
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
    # reuse rg's mark-to-market by replaying exactly the taken trades with unlimited slots
    replay_trades = sorted([(e, o, (p / (q * (1 - grid.SLIP) * (1 - FEE))), s) for e, o, q, p, s in taken])
    return rg.simulate(replay_trades, [(len(taken) or 1, CORE | PULL | CATCH)], start, end) | {"capital": initial} \
        if False else _finish(taken, wallet, slots, pots, initial, start, end)


def _finish(taken, wallet, slots, pots, initial, start, end):
    for p in range(len(pots)):
        wallet += sum(s[1] for s in slots[p])
    hours = np.arange(np.searchsorted(grid.TIMES, start), np.searchsorted(grid.TIMES, end), 60)
    equity = np.full(len(hours), initial, dtype=float)
    for entry, out, qty, proceeds, _ in taken:
        b = np.searchsorted(hours, out)
        equity[b:] += proceeds - LOT
        a = np.searchsorted(hours, entry)
        if b > a:
            equity[a:b] += qty * grid.CLOSE[hours[a:b]] * (1 - grid.SLIP) * (1 - FEE) - LOT
    peak = np.maximum.accumulate(equity)
    ledger = pd.DataFrame([{"source": s, "pnl": p - LOT} for e, o, q, p, s in taken])
    return {"profit": wallet - initial, "dd": 100 * (equity / peak - 1).min(), "dd_usd": (equity - peak).min(),
            "ledger": ledger, "capital": initial}


def evaluate(label, trades, pots, idle_only=False):
    runs = {n: simulate(trades, pots, *research.WINDOWS[n], idle_only) for n in ("full", "earlier", "later", "unseen", *TESTS)}
    full, ledger = runs["full"], runs["full"]["ledger"]
    wf = [runs[w]["profit"] for w in TESTS]
    sub = ledger[ledger.source.isin(CATCH)] if len(ledger) else ledger
    return {"design": label, "capital": int(full["capital"]),
            "core": int(ledger.source.isin(CORE).sum()) if len(ledger) else 0,
            "pull": int(ledger.source.isin(PULL).sum()) if len(ledger) else 0,
            "catchup": len(sub), "catchup_pnl": round(sub.pnl.sum(), 2) if len(sub) else 0.0,
            "catchup_win%": round(100 * (sub.pnl > 0).mean(), 1) if len(sub) else 0.0,
            "profit": round(full["profit"], 2), "earlier": round(runs["earlier"]["profit"], 2),
            "later": round(runs["later"]["profit"], 2), "unseen": round(runs["unseen"]["profit"], 2),
            "walk_forward": round(sum(wf), 2), "wf_windows": f"{sum(x > 0 for x in wf)}/6",
            "mtm_dd%": round(full["dd"], 2), "mtm_dd$": round(full["dd_usd"], 2)}


def main() -> None:
    raw, bullish, ema, mode_c = pb.setup()
    btc = replay.load_raw("BTCUSDT", include_holdout=True)
    btc = btc[btc.open_time < research.T("2026-09-11")].reset_index(drop=True)
    sig = Signals(raw, btc)
    core = pb.build(raw, bullish, ema, mode_c)
    pull = [t for t in pb.build(raw, bullish, ema, [], pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES))
            if t[3] == "pullback"]
    key = lambda t: (t[0], PRIORITY[t[3]])
    book = lambda *parts: sorted([t for part in parts for t in part], key=key)
    plan, base = book(core, pull), [(5, CORE), (2, PULL)]
    pd.set_option("display.width", 340)
    window = (sig.frame.index >= research.WINDOWS["full"][0]) & (sig.frame.index < research.WINDOWS["full"][1])
    print(f"BTC stacked upward {100 * sig.frame.btc_up[window].mean():.1f}% of hours; "
          f"ETH stacked downward {100 * sig.frame.eth_down[window].mean():.1f}% of hours")

    print("\n=== 1. catch-up measured inside the plan's shared wallet, on its own 3 lots (is the rule any good?)")
    rows = []
    for exit_style in ("dip", "revert"):
        for days in LOOKBACK:
            for lag in LAG:
                trades = build(sig, bullish, ema, days, lag, exit_style)
                r = evaluate(f"{exit_style} exit, ratio {days}d, lag {lag:g}%", book(core, pull, trades), base + [(3, CATCH)])
                p = evaluate("plan", plan, base)
                r["adds_profit"] = round(r["profit"] - p["profit"], 2)
                r["adds_wf"] = round(r["walk_forward"] - p["walk_forward"], 2)
                rows.append(r)
    frame = pd.DataFrame(rows).set_index("design")
    print(frame[["catchup", "catchup_pnl", "catchup_win%", "adds_profit", "adds_wf", "wf_windows", "earlier",
                 "later", "unseen", "mtm_dd$"]].to_string())

    best = frame.adds_wf.idxmax()
    exit_style, rest = best.split(" exit, ratio ")
    days = int(rest.split("d,")[0])
    lag = float(rest.split("lag ")[1].rstrip("%"))
    print(f"\n(hindsight best on walk-forward: {best} - used below only to show the organisation options)")

    print("\n=== 2. every way to organise it beside the plan (core 5 + pullback 2)")
    rows = [evaluate("PLAN core 5 + pullback 2", plan, base)]
    for k in (1, 2, 3):
        rows.append(evaluate(f"CONTROL +{k} pullback lots", plan, [(5, CORE), (2 + k, PULL)]))
    for k in (1, 2, 3):
        rows.append(evaluate(f"+ catch-up sleeve {k} x $100", book(core, pull, build(sig, bullish, ema, days, lag, exit_style)),
                             base + [(k, CATCH)]))
    two = build(sig, bullish, ema, days, lag, exit_style)
    rows.append(evaluate("catch-up SHARES the core's 5 lots", book(core, pull, two), [(5, CORE | CATCH), (2, PULL)]))
    rows.append(evaluate("catch-up SHARES the pullback's 2 lots", book(core, pull, two), [(5, CORE), (2, PULL | CATCH)]))
    rows.append(evaluate("+ catch-up 2 x $100, only when book is idle", book(core, pull, two), base + [(2, CATCH)], idle_only=True))
    print(pd.DataFrame(rows).set_index("design").to_string())

    print("\n=== 3. honest selection test: pick exit / lookback / lag on the 6 months before each window")
    settings = {(e, d, l): build(sig, bullish, ema, d, l, e) for e in ("dip", "revert") for d in LOOKBACK for l in LAG}
    plan_w = {w: rg.simulate(plan, base, *research.WINDOWS[w])["profit"] for w in (*TRAINS, *TESTS)}
    for k in (1, 2, 3):
        score = {s: {w: rg.simulate(book(core, pull, v), base + [(k, CATCH)],
                                    *research.WINDOWS[w])["profit"] - plan_w[w] for w in (*TRAINS, *TESTS)}
                 for s, v in settings.items()}
        control = {w: rg.simulate(plan, [(5, CORE), (2 + k, PULL)], *research.WINDOWS[w])["profit"] - plan_w[w] for w in TESTS}
        table, picks = [], []
        for i, test in enumerate(TESTS):
            pick = max(score, key=lambda s: score[s][TRAINS[i]])
            picks.append(pick)
            table.append({"window": research.TESTS[i][0], "chosen": f"{pick[0]} / {pick[1]}d / {pick[2]:g}%",
                          "catch-up added": round(score[pick][test], 2),
                          f"+{k} pullback lot(s) added": round(control[test], 2)})
        honest = sum(score[s][t] for s, t in zip(picks, TESTS))
        print(f"\n--- catch-up sleeve of {k} x $100")
        print(pd.DataFrame(table).to_string(index=False))
        print(f"  catch-up, picked in advance  ${honest:8.2f}  positive {sum(score[s][t] > 0 for s, t in zip(picks, TESTS))}/6")
        print(f"  +{k} pullback lot(s) instead  ${sum(control.values()):8.2f}  positive {sum(v > 0 for v in control.values())}/6"
              f"  (pullback setting is a hindsight pick; honest 3rd lot was about $37)")


if __name__ == "__main__":
    main()
