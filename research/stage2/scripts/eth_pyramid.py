"""Pyramiding on ETH: add lots to a winning trend instead of letting slots sit idle.

Scale-out lost 28% because ETH's money is in a few large moves. This tests the opposite: ADD to winners.

  parent      any lot the deployed system actually takes (dip or Mode C)
  add 1       the first 1-minute close at +X% from the parent's fill, with that close above the 16-hour EMA
  add 2       the same at +2X%, only after add 1 exists
  buy         next minute's open, only if a slot and $100 are free (same 3 x $100 shared pot)

Two ways an add can leave:
  own exit    the deployed rule from its own fill: stop -4.5%, trail arms +1.315%, Mode A EMA hold in uptrends
  with parent every add sells the minute its parent sells - the classic pyramid, one decision for the stack

Two scopes: adds only on trend lots (bought while 7d>15d>30d, the Mode A lots), or on every lot.
Everything else is ETH as deployed. BNB fees, 2 bps slippage.
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
import three_modes as tm

COIN = "eth"
STEPS = [2.0, 3.0, 4.0, 6.0]
LOT, LOTS, INITIAL = 100.0, 3, 300.0
FEE = 7.5 / 10_000
TESTS = [f"wf{i}_test" for i in range(len(research.TESTS))]
TRAINS = [f"wf{i}_train" for i in range(len(research.TESTS))]


def base_trades(raw, bullish, ema):
    rule = live.load_rule(COIN)
    trades = []
    for entry in live.live_entries(raw, rule):
        entry = int(entry)
        line = ema if bullish[entry] else None
        out, price, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], tm.DIP_STOP, line)
        trades.append({"entry": entry, "exit": out, "price": price, "source": "dip", "parent": None})
    mc = tm.MODE_C
    high, low, open_, close, last_minute = v4.bars_for(raw, mc["chart"])
    entries = v4.entries_for(high, low, close, last_minute, mc["bars"], mc["zone"], mc["confirm"],
                             grid.CLOSE, len(raw))
    hour = grid.TIMES[entries].hour
    for entry in entries[~((hour >= 6) & (hour < 12))]:
        entry = int(entry)
        line = ema if bullish[entry] else None
        out, price, _ = opt.trade(entry, mc["arm"], mc["giveback"], mc["stop"], line)
        trades.append({"entry": entry, "exit": out, "price": price, "source": "breakout", "parent": None})
    for key, trade in enumerate(trades):
        trade["key"] = key
    return trades


def adds_for(parents, bullish, ema, step, style, scope):
    """Add-on candidates for every parent. They only become real if the parent was actually taken."""
    rule = live.load_rule(COIN)
    adds = []
    for parent in parents:
        if parent["exit"] < 0 or (scope == "trend" and not bullish[parent["entry"]]):
            continue
        fill = grid.OPEN[parent["entry"]] * (1 + grid.SLIP)
        start, stop_at = parent["entry"] + 1, parent["exit"]
        for level in (1, 2):
            if start >= stop_at:
                break
            close, line = grid.CLOSE[start:stop_at], ema[start:stop_at]
            hits = np.flatnonzero((close >= fill * (1 + level * step / 100)) & (close > line))
            if not len(hits):
                break
            signal = start + int(hits[0])
            entry = signal + 1
            if entry >= stop_at:
                break
            if style == "with parent":
                out, price = parent["exit"], parent["price"]
            else:
                trend = ema if bullish[entry] else None
                out, price, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], tm.DIP_STOP, trend)
            adds.append({"entry": entry, "exit": out, "price": price, "source": "pyramid",
                         "parent": parent["key"], "level": level})
            start = entry
    return adds


def account(trades, start, end):
    """tm.account's $300 pot, except an add is only taken while its parent is open in this same run."""
    cash, slots, taken, open_keys = INITIAL, [], [], set()
    peak, worst = INITIAL, 0.0
    for trade in sorted(trades, key=lambda t: (t["entry"], t["parent"] is not None)):
        entry = trade["entry"]
        if not (start <= grid.TIMES[entry] < end):
            continue
        for slot in [s for s in slots if s[0] <= entry]:
            cash += slot[1]
            open_keys.discard(slot[2])
        slots = [s for s in slots if s[0] > entry]
        equity = cash + LOT * len(slots)
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1)
        if trade["exit"] < 0 or len(slots) >= LOTS or cash < LOT:
            continue
        if trade["parent"] is not None and trade["parent"] not in open_keys:
            continue
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        quantity = LOT / (fill * (1 + FEE))
        proceeds = quantity * trade["price"] * (1 - grid.SLIP) * (1 - FEE)
        cash -= LOT
        key = trade.get("key", ("add", entry))
        slots.append((trade["exit"], proceeds, key))
        open_keys.add(key)
        taken.append({"entry": entry, "source": trade["source"], "pnl": proceeds - LOT,
                      "level": trade.get("level", 0)})
    for slot in slots:
        cash += slot[1]
    frame = pd.DataFrame(taken)
    return {"profit": cash - INITIAL, "dd": worst * 100, "ledger": frame}


def evaluate(label, trades):
    periods = {name: account(trades, *research.WINDOWS[name]) for name in ("full", "earlier", "later", "unseen", *TESTS)}
    ledger = periods["full"]["ledger"]
    wins, losses = ledger[ledger.pnl > 0], ledger[ledger.pnl <= 0]
    adds = ledger[ledger.source == "pyramid"]
    wf = [periods[w]["profit"] for w in TESTS]
    return {"strategy": label, "trades": len(ledger), "dip": int((ledger.source == "dip").sum()),
            "modeC": int((ledger.source == "breakout").sum()), "adds": len(adds),
            "adds_pnl": round(adds.pnl.sum(), 2) if len(adds) else 0.0,
            "add_win%": round(100 * (adds.pnl > 0).mean(), 1) if len(adds) else 0.0,
            "win_rate": round(100 * (ledger.pnl > 0).mean(), 1),
            "avg_win": round(wins.pnl.mean(), 2), "avg_loss": round(losses.pnl.mean(), 2),
            "profit": round(periods["full"]["profit"], 2), "earlier": round(periods["earlier"]["profit"], 2),
            "later": round(periods["later"]["profit"], 2), "unseen": round(periods["unseen"]["profit"], 2),
            "walk_forward": round(sum(wf), 2), "wf_windows": f"{sum(p > 0 for p in wf)}/6",
            "drawdown": round(periods["full"]["dd"], 2)}


def setup():
    raw = replay.load_raw("ETHUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=tm.EMA_HOURS * 60, adjust=False).mean().to_numpy()
    return raw, bullish, ema


def main() -> None:
    raw, bullish, ema = setup()
    parents = base_trades(raw, bullish, ema)
    pd.set_option("display.width", 320)

    variants = {"no pyramiding (deployed today)": []}
    for scope in ("trend", "all"):
        for style in ("own exit", "with parent"):
            for step in STEPS:
                variants[f"{scope} lots, +{step:g}% steps, {style}"] = adds_for(parents, bullish, ema, step, style, scope)

    rows = [evaluate(name, parents + adds) for name, adds in variants.items()]
    frame = pd.DataFrame(rows).set_index("strategy")
    print("=== ETH with pyramiding, $300 as 3 x $100 shared, BNB fees")
    print(frame.to_string())

    # the honest gate: choose the variant on the six months before each test window
    scores = {name: {w: account(parents + adds, *research.WINDOWS[w])["profit"] for w in (*TRAINS, *TESTS)}
              for name, adds in variants.items()}
    deployed = "no pyramiding (deployed today)"
    picks, table = [], []
    for i, test in enumerate(TESTS):
        chosen = max(scores, key=lambda n: scores[n][TRAINS[i]])
        picks.append(chosen)
        table.append({"window": research.TESTS[i][0], "chosen on the 6 months before": chosen,
                      "it earned": round(scores[chosen][test], 2), "deployed earned": round(scores[deployed][test], 2)})
    print("\n=== honest selection test, window by window")
    print(pd.DataFrame(table).to_string(index=False))
    honest = sum(scores[n][t] for n, t in zip(picks, TESTS))
    base = sum(scores[deployed][t] for t in TESTS)
    print(f"\n  picked in advance (honest)   ${honest:8.2f}")
    print(f"  deployed, no pyramiding      ${base:8.2f}")
    print(f"  oracle (hindsight)           ${sum(max(scores[n][t] for n in scores) for t in TESTS):8.2f}")
    print("\n=== windows each variant beat the deployed system")
    beats = {n: sum(scores[n][t] > scores[deployed][t] for t in TESTS) for n in scores if n != deployed}
    print(pd.Series(beats).sort_values(ascending=False).to_string())


if __name__ == "__main__":
    main()
