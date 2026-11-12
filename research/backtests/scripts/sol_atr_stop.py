"""Does an ATR-scaled stop (and trail arm) beat SOL's flat percentages?

SOL risks a flat -2% on every dip lot and -4% on a Mode C lot, and arms its trail at a flat +1.251%, however
violent the week is. ATR (Average True Range) measures how far SOL actually travels in a normal day, so the same
-2% is a long way down in a calm week and ordinary noise in a wild one.

  True Range of a day = the largest of: high - low, |high - previous close|, |low - previous close|
  ATR(n) = the average of the last n days' true ranges, expressed as a % of price so 2024 and 2026 compare.

No lookahead: a day's ATR uses completed UTC days only and takes effect the next UTC day, the same convention
the daily averages already use.

Every combination:
  period    ATR over 7, 14 or 21 days
  stop      0.25 / 0.35 / 0.5 / 0.75 / 1.0 / 1.5 x ATR, or left flat
  arm       0.15 / 0.2 / 0.25 / 0.3 / 0.4 x ATR, or left flat
  scope     which lots are scaled: the dip only, Mode C only, or both
  lots      SHARED - the 3 deployed lots all switch to the ATR rule
            SEPARATE - the 3 core lots keep the flat rule and an ATR sleeve of 1-3 lots of its own takes the
            same signals alongside them, so the two rules run side by side out of one wallet

Then the honest test: choose the ATR rule on the six months before each window and use it in the window it has
never seen. Everything else is SOL as deployed: dip at the 12-day average, Mode C, Mode A on the 8-hour line,
the live buying rule, BNB fees.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import eth_regime as rg
import sol_pullback as sp

COIN = "sol"
PERIODS = [7, 14, 21]
STOPS = [None, 0.25, 0.35, 0.5, 0.75, 1.0, 1.5]
ARMS = [None, 0.15, 0.2, 0.25, 0.3, 0.4]
SCOPES = ["dip", "mode c", "both"]
FEE, MIN_ORDER, LOT = 7.5 / 10_000, 5.0, 100.0
FLAT, ATR = {"dip", "breakout"}, {"atr dip", "atr breakout"}
TRAINS = [f"wf{i}_train" for i in range(6)]


def atr_percent(raw: pd.DataFrame, period: int) -> np.ndarray:
    """ATR as a % of price for every 1-minute row, from completed days only, effective the next day."""
    day = raw.open_time.dt.floor("D")
    daily = raw.groupby(day).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"),
                                 n=("close", "size"))
    daily = daily[daily.n == 1440]
    previous = daily.close.shift(1)
    true_range = pd.concat([daily.high - daily.low, (daily.high - previous).abs(),
                            (daily.low - previous).abs()], axis=1).max(axis=1)
    atr = true_range.rolling(period).mean() / daily.close * 100
    effective = pd.Series(atr.to_numpy(), index=daily.index + pd.Timedelta(days=1))
    return day.map(effective).to_numpy(float)


def signals(raw):
    """The entry minutes of both ways in, exactly as deployed. Exits are decided later."""
    rule = live.load_rule(COIN)
    dips = [int(entry) for entry in live.live_entries(raw, rule)]
    high, low, open_, close, last_minute = v4.bars_for(raw, sp.MODE_C["chart"])
    entries = v4.entries_for(high, low, close, last_minute, sp.MODE_C["bars"], sp.MODE_C["zone"],
                             sp.MODE_C["confirm"], grid.CLOSE, len(raw))
    blocked = rule["blocked"]
    if blocked:
        hours = grid.TIMES[entries].hour
        entries = entries[~((hours >= blocked[0]) & (hours < blocked[1]))]
    return rule, dips, [int(entry) for entry in entries]


def build(rule, dips, breaks, bullish, ema, atr=None, stop_k=None, arm_m=None, scope="both", tag=""):
    """Every candidate trade. A None multiplier keeps the deployed flat percentage for that side."""
    out = []
    for entries, source, flat_stop, flat_arm, giveback in (
            (dips, "dip", rule["stop_pct"], rule["activation_pct"], rule["giveback_pct"]),
            (breaks, "breakout", sp.MODE_C["stop"], sp.MODE_C["arm"], sp.MODE_C["giveback"])):
        scaled = atr is not None and scope in ("both", "dip" if source == "dip" else "mode c")
        for entry in entries:
            stop, arm = flat_stop, flat_arm
            if scaled and np.isfinite(atr[entry]):
                stop = flat_stop if stop_k is None else stop_k * atr[entry]
                arm = flat_arm if arm_m is None else arm_m * atr[entry]
            exit_at, price, _ = opt.trade(entry, arm, giveback, stop, ema if bullish[entry] else None)
            out.append({"entry": entry, "exit": exit_at, "price": price, "source": f"{tag}{source}"})
    return sorted(out, key=lambda t: t["entry"])


def simulate(trades, pots, start, end):
    """One shared wallet, per-pot slot limits, the live buying rule (a full lot, or whatever is left)."""
    initial = sum(n for n, _ in pots) * LOT
    wallet, slots, taken = initial, [[] for _ in pots], []
    for trade in trades:
        entry = trade["entry"]
        if not (start <= grid.TIMES[entry] < end):
            continue
        for p in range(len(pots)):
            for slot in [s for s in slots[p] if s[0] <= entry]:
                wallet += slot[1]
            slots[p] = [s for s in slots[p] if s[0] > entry]
        if trade["exit"] < 0 or wallet < MIN_ORDER:
            continue
        for p, (lots, sources) in enumerate(pots):
            if trade["source"] in sources and len(slots[p]) < lots:
                spend = min(LOT, np.floor(wallet * 100) / 100)
                fill = grid.OPEN[entry] * (1 + grid.SLIP)
                proceeds = spend / (fill * (1 + FEE)) * trade["price"] * (1 - grid.SLIP) * (1 - FEE)
                wallet -= spend
                slots[p].append((trade["exit"], proceeds))
                taken.append({"source": trade["source"], "pnl": proceeds - spend, "entry": entry})
                break
    for p in range(len(pots)):
        wallet += sum(s[1] for s in slots[p])
    return {"profit": wallet - initial, "ledger": pd.DataFrame(taken)}


def drawdown(trades, pots, start, end):
    """Worst peak-to-trough of realised equity inside the window, as a % of the money put in."""
    led = simulate(trades, pots, start, end)["ledger"]
    if not len(led):
        return 0.0
    equity = led.pnl.cumsum().to_numpy()
    peak = np.maximum.accumulate(np.r_[0.0, equity])
    return round(float((np.r_[0.0, equity] - peak).min()) / (sum(n for n, _ in pots) * LOT) * 100, 2)


def score(label, trades, pots):
    runs = {w: simulate(trades, pots, *research.WINDOWS[w]) for w in ("full", "unseen", *rg.TESTS)}
    led = runs["full"]["ledger"]
    wf = [runs[w]["profit"] for w in rg.TESTS]
    return {"setup": label, "money": int(sum(n for n, _ in pots) * LOT), "trades": len(led),
            "win%": round(100 * (led.pnl > 0).mean(), 1) if len(led) else 0.0,
            "profit": round(runs["full"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "windows": f"{sum(x > 0 for x in wf)}/6", "unseen": round(runs["unseen"]["profit"], 2),
            "drawdown%": drawdown(trades, pots, *research.WINDOWS["full"])}


def name_of(key):
    period, stop_k, arm_m, scope = key
    stop = "flat stop" if stop_k is None else f"stop {stop_k:g}xATR"
    arm = "flat arm" if arm_m is None else f"arm {arm_m:g}xATR"
    return f"ATR{period} {stop}, {arm}, {scope}"


def main() -> None:
    raw, bullish, ema = sp.setup()
    rule, dips, breaks = signals(raw)
    atrs = {period: atr_percent(raw, period) for period in PERIODS}
    pd.set_option("display.width", 270)

    window = (grid.TIMES >= research.WINDOWS["full"][0]) & (grid.TIMES < research.WINDOWS["full"][1])
    series = pd.Series(atrs[14][window]).dropna()
    print(f"SOL candidates: {len(dips)} dips, {len(breaks)} Mode C breaks")
    print("\n=== SOL daily ATR(14) as a % of price, over the full window")
    print(series.describe(percentiles=[.1, .25, .5, .75, .9]).round(2).to_string())
    print(f"The deployed flat dip stop of -{rule['stop_pct']}% equals {rule['stop_pct'] / series.median():.2f}x the "
          f"median ATR, but {rule['stop_pct'] / series.quantile(.9):.2f}x on the calmest days and "
          f"{rule['stop_pct'] / series.quantile(.1):.2f}x on the wildest.")

    flat = build(rule, dips, breaks, bullish, ema)
    base = score("flat -2% / -4%, +1.251% arm (deployed)", flat, [(3, FLAT)])
    print("\n=== SOL as deployed, 3 x $100")
    print(pd.DataFrame([base]).set_index("setup").to_string())

    keys = [(p, s, a, sc) for p in PERIODS for s in STOPS for a in ARMS for sc in SCOPES
            if not (s is None and a is None)]
    sets = {key: build(rule, dips, breaks, bullish, ema, atrs[key[0]], key[1], key[2], key[3]) for key in keys}

    print(f"\n=== 1. SHARED: all {len(sets)} ATR rules replacing the flat one on SOL's 3 lots")
    rows = [score(name_of(key), trades, [(3, FLAT)]) for key, trades in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(12).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  ATR rules that beat the flat rule: {int((frame.profit > base['profit']).sum())}/{len(frame)} on the "
          f"full window, {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame)} on walk-forward, "
          f"{int((frame['drawdown%'] > base['drawdown%']).sum())}/{len(frame)} on drawdown")

    print("\n=== 2. SEPARATE: the core keeps the flat rule, an ATR sleeve of its own takes the same signals")
    best = [key for key, _ in sorted(zip(sets, rows), key=lambda item: -item[1]["walk_forward"])][:4]
    table = [base]
    for key in best:
        sleeve = build(rule, dips, breaks, bullish, ema, atrs[key[0]], key[1], key[2], key[3], tag="atr ")
        for k in (1, 2, 3):
            table.append(score(f"{name_of(key)} - sleeve {k}", sorted(flat + sleeve, key=lambda t: t["entry"]),
                               [(3, FLAT), (k, ATR)]))
    for extra in (1, 2, 3):
        table.append(score(f"CONTROL flat core {3 + extra}", flat, [(3 + extra, FLAT)]))
    print(pd.DataFrame(table).set_index("setup").to_string())

    print("\n=== 3. honest test: choose the ATR rule on the six months before each window")
    for label, pots, with_sleeve in (("shared, 3 lots", [(3, FLAT)], False),
                                     ("sleeve of 1", [(3, FLAT), (1, ATR)], True),
                                     ("sleeve of 2", [(3, FLAT), (2, ATR)], True)):
        base_w = {w: simulate(flat, [(3, FLAT)] if not with_sleeve else pots, *research.WINDOWS[w])["profit"]
                  for w in (*TRAINS, *rg.TESTS)}
        scores = {}
        for key, trades in sets.items():
            if with_sleeve:
                sleeve = build(rule, dips, breaks, bullish, ema, atrs[key[0]], key[1], key[2], key[3], tag="atr ")
                use = sorted(flat + sleeve, key=lambda t: t["entry"])
            else:
                use = trades
            scores[key] = {w: simulate(use, pots, *research.WINDOWS[w])["profit"] - base_w[w]
                           for w in (*TRAINS, *rg.TESTS)}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > 0 for p, t in zip(picks, rg.TESTS))
        best_fixed = max(sets, key=lambda k: sum(scores[k][t] for t in rg.TESTS))
        print(f"  {label:<16} honest ${honest:8.2f} ({wins}/6) | best fixed rule in hindsight "
              f"{name_of(best_fixed)}: ${sum(scores[best_fixed][t] for t in rg.TESTS):8.2f}")
        print(f"{'':18}picked: {', '.join(name_of(p) for p in picks)}")


if __name__ == "__main__":
    main()
