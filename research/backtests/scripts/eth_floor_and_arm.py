"""ETH Mode A: where should the floor sit, when should it attach, and is +1.315% really the right arm?

Three questions, swept together, on ETH without the pyramid (dip + Mode C + pullback, 5 and 3 x $100 shared,
BNB fees, the live buying rule, the corrected window engine):

  where   the floor sits at the BUY PRICE + 0.19% (deployed - a fixed level, guarantees a lot cannot finish
          negative once it has armed), or 0.19% ABOVE THE 16-HOUR LINE (a moving level that rides up with the
          line and sells on the way down to it rather than after a close below it), or BOTH - whichever of the
          two is higher at the time. Plus "no floor at all" for reference.

  when    the floor only attaches once the lot ARMS (deployed), or it attaches as soon as the lot has traded
          at buy + 0.19% at all, armed or not. The second is the answer to "what about the lots that never
          reach the arm?" - they get the protection too, which also makes their effective stop far tighter.

  arm     +0.1% to +3.0% in 0.1% steps, plus the deployed +1.315%. The arm still controls one thing only: when
          the 16-hour line is allowed to sell the lot.

0.19% = 7.5bps Binance fee and 2bps slippage, both sides - what a round trip costs, so a lot sold there is
exactly level. Judged walk-forward: the rule is chosen on the six months before each window, never in hindsight.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import eth_pullback as pb
import eth_regime as rg
import three_modes as tm
import all_coins_compare as cmp
import sol_wide_stop as w
import trx_volume_filter as vf
from sol_wide_stop import TRAINS, simulate

CORE = {"dip", "breakout", "pullback"}
COSTS = 0.19
DEPLOYED_ARM = 1.315
ARMS = sorted({round(x, 3) for x in np.arange(0.1, 3.01, 0.1)} | {DEPLOYED_ARM})
WHERE = ["buy price", "above the line", "the higher of the two"]
WHEN = ["on arming", "as soon as it covers costs"]
CHUNK = 4096
LINE_FLOOR = None                 # set in main(): the 16-hour line lifted by the cost of a round trip


def scan(start, end, level_of):
    """First minute in [start, end) whose LOW touches the level, scanning in chunks so long waits are cheap."""
    at = start
    while at < end:
        stop_at = min(at + CHUNK, end)
        level = level_of(at, stop_at)
        hits = np.flatnonzero(grid.LOW[at:stop_at] <= level)
        if len(hits):
            index = at + int(hits[0])
            value = level if np.isscalar(level) else float(level[hits[0]])
            return index, float(value)
        at = stop_at
    return -1, 0.0


def scan_line(start, end, line):
    at = start
    while at < end:
        stop_at = min(at + CHUNK, end)
        hits = np.flatnonzero(grid.CLOSE[at:stop_at] <= line[at:stop_at])
        if len(hits):
            return at + int(hits[0])
        at = stop_at
    return -1


def mode_a(entry, arm, stop_pct, line, where, when):
    """One Mode A lot. The line may only sell it once it has armed; the floor follows the rules under test."""
    last = len(grid.OPEN) - 1
    fill = grid.OPEN[entry] * (1 + grid.SLIP)
    stop = fill * (1 - stop_pct / 100)
    armed = research.first_hit(entry, fill * (1 + arm / 100), True)
    fill_floor = fill * (1 + COSTS / 100)

    # The bot only learns a lot has armed at that minute's close, so the new stop reaches Binance on the
    # NEXT minute. A big candle that arms and dips through the floor in the same minute is not a floor exit.
    if where is None:
        attached = last + 1
    elif when == "on arming":
        attached = last + 1 if armed < 0 else armed + 1
    else:
        touched = research.first_hit(entry, fill_floor, True)
        attached = last + 1 if touched < 0 else touched + 1

    def level_of(a, b):
        if a >= attached and where == "buy price":
            return max(stop, fill_floor)
        if a >= attached and where == "above the line":
            return np.maximum(stop, LINE_FLOOR[a:b])
        if a >= attached and where == "the higher of the two":
            return np.maximum(max(stop, fill_floor), LINE_FLOOR[a:b])
        if b <= attached:
            return stop
        flat = np.full(b - a, stop)                       # the floor attaches part-way through this chunk
        flat[attached - a:] = (max(stop, fill_floor) if where == "buy price"
                               else np.maximum(stop if where == "above the line" else max(stop, fill_floor),
                                               LINE_FLOOR[attached:b]))
        return flat

    out_stop, level = scan(entry + 1, last + 1, level_of)
    out_line = -1 if armed < 0 else scan_line(armed + 1, last + 1, line)
    if out_stop >= 0 and (out_line < 0 or out_stop <= out_line):
        return out_stop, min(level, float(grid.OPEN[out_stop])), 2
    if out_line >= 0:
        at = min(out_line + 1, last)
        return at, float(grid.OPEN[at]), 1
    return last, float(grid.CLOSE[last]), 3               # never resolved: marked at the last price


def book(sources, bullish, line, arm, where, when):
    trades = []
    for entries, source, stop, own_arm, give in sources:
        for entry in entries:
            entry = int(entry)
            if bullish[entry]:
                exit_at, price, why = mode_a(entry, arm, stop, line, where, when)
            else:
                exit_at, price, why = w.resolve(entry, own_arm, give, stop, None)
            trades.append({"entry": entry, "exit": exit_at, "price": price, "source": source, "why": why})
    return sorted(trades, key=lambda t: t["entry"])


def rules():
    for arm in ARMS:
        yield (arm, None, "-"), f"arm +{arm}%, no floor"
        for where in WHERE:
            for when in WHEN:
                yield (arm, where, when), f"arm +{arm}%, floor at the {where}, {when}"


def main() -> None:
    global LINE_FLOOR
    raw, bullish = cmp.load("ETHUSDT")
    rule = live.load_rule("eth")
    sources = ((live.live_entries(raw, rule), "dip", tm.DIP_STOP, rule["activation_pct"], rule["giveback_pct"]),
               ([t["entry"] for t in cmp.mode_c(raw, rule, 120, 12, 2.5, 30, 1.283, 22.0, 3.5)],
                "breakout", 3.5, 1.283, 22.0),
               (pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES, blocked=rule["blocked"]),
                "pullback", tm.DIP_STOP, rule["activation_pct"], rule["giveback_pct"]))
    line = pd.Series(grid.CLOSE).ewm(span=16 * 60, adjust=False).mean().to_numpy()
    LINE_FLOOR = line * (1 + COSTS / 100)
    pd.set_option("display.width", 250)

    books, rows = {}, []
    for key, label in rules():
        trades = book(sources, bullish, line, *key)
        books[key] = trades
        for lots in (3, 5):
            led = simulate(trades, [(lots, CORE)], *research.WINDOWS["full"])["ledger"]
            rows.append({**vf.score(f"{label} — {lots} x $100", trades, [(lots, CORE)]),
                         "lots": lots, "arm": key[0], "where": key[1] or "none", "when": key[2],
                         "losers": int((led.pnl <= 0).sum()) if len(led) else 0,
                         "avg win": round(led[led.pnl > 0].pnl.mean(), 2) if len(led) else 0.0,
                         "avg loss": round(led[led.pnl <= 0].pnl.mean(), 2) if len(led) else 0.0})
    frame = pd.DataFrame(rows)
    show = ["trades", "win%", "losers", "avg win", "avg loss", "profit", "walk_forward", "windows", "unseen",
            "mtm_dd%"]
    deployed = (DEPLOYED_ARM, "buy price", "on arming")
    base = {lots: frame[(frame.lots == lots) & (frame.arm == DEPLOYED_ARM) & (frame["where"] == "buy price")
                        & (frame["when"] == "on arming")].iloc[0] for lots in (3, 5)}

    print("=== the control (ETH as it stands today)")
    print(pd.DataFrame([base[3], base[5]]).set_index("setup")[show].to_string())

    for lots in (5, 3):
        part = frame[frame.lots == lots].sort_values("walk_forward", ascending=False)
        b = base[lots]
        print(f"\n=== best 15 of {len(part)} at {lots} x $100 "
              f"(control ${b['walk_forward']:.2f}, {b['win%']}% win, {b['mtm_dd%']}%)")
        print(part.set_index("setup").head(15)[show].to_string())
        print(f"  beating the control on walk-forward: {int((part.walk_forward > b['walk_forward']).sum())}"
              f"/{len(part)}; on win rate: {int((part['win%'] > b['win%']).sum())}/{len(part)}")

    print("\n=== question 1: where does the floor belong? (5 x $100, averaged over every arm)")
    five = frame[frame.lots == 5]
    print(five.groupby(["where", "when"]).agg(
        **{"win%": ("win%", "mean"), "profit": ("profit", "mean"), "walk_forward": ("walk_forward", "mean"),
           "best wf": ("walk_forward", "max"), "mtm_dd%": ("mtm_dd%", "mean")}).round(2).to_string())

    print("\n=== question 2: the arm sweep, floor as deployed (buy price, on arming), 5 x $100")
    sweep = five[(five["where"] == "buy price") & (five["when"] == "on arming")].sort_values("arm")
    print(sweep.set_index("arm")[["win%", "losers", "avg win", "avg loss", "profit", "walk_forward", "windows",
                                  "mtm_dd%"]].to_string())

    print("\n=== question 3: does the floor need the arm? (5 x $100, floor at the buy price)")
    q3 = five[five["where"] == "buy price"].pivot_table(index="arm", columns="when",
                                                     values=["walk_forward", "win%"]).round(2)
    print(q3.to_string())

    print("\n=== the honest test: the whole rule chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for lots in (3, 5):
        scores = {k: {x: simulate(v, [(lots, CORE)], *research.WINDOWS[x])["profit"] for x in windows}
                  for k, v in books.items()}
        control = scores[deployed]
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]]) for i in range(6)]
        chosen = sum(scores[p][t] for p, t in zip(picks, rg.TESTS))
        live_sum = sum(control[t] for t in rg.TESTS)
        best = max(scores, key=lambda k: sum(scores[k][t] for t in rg.TESTS))
        print(f"\n  --- {lots} x $100")
        print(f"    choosing honestly ${chosen:8.2f} against ${live_sum:8.2f} deployed ({chosen - live_sum:+.2f})")
        print(f"    it picked: {picks}")
        diffs = [scores[best][t] - control[t] for t in rg.TESTS]
        print(f"    best in hindsight {best}: ${sum(scores[best][t] for t in rg.TESTS):8.2f} "
              f"({sum(d > 0 for d in diffs)}/6: {', '.join(f'{d:+.2f}' for d in diffs)})")
        for key in [(DEPLOYED_ARM, "above the line", "on arming"),
                    (DEPLOYED_ARM, "the higher of the two", "on arming"),
                    (DEPLOYED_ARM, "buy price", "as soon as it covers costs"),
                    (DEPLOYED_ARM, None, "-"), (1.0, "buy price", "on arming"), (2.0, "buy price", "on arming")]:
            d = [scores[key][t] - control[t] for t in rg.TESTS]
            print(f"    {str(key):<46} ${sum(scores[key][t] for t in rg.TESTS):8.2f} "
                  f"({sum(x > 0 for x in d)}/6: {', '.join(f'{x:+.2f}' for x in d)})")


if __name__ == "__main__":
    main()
