"""One coin with all three modes, and a simulator that can say which rule earned what.

Mode A and Mode B are EXITS - how a lot takes its profit. Mode C is an ENTRY - a second reason to buy. A
Mode C lot still leaves through Mode A or Mode B, so the three are not three alternatives: C feeds A and B.

  Entry 1 (dip)    the deployed rule: 5-minute signals, 7-day average, +-0.5% zone from below, green candle
                   within 30 minutes, no entries 06:00-12:00 UTC, skip strong downtrends.
  Entry 2 (Mode C) consolidation breakout: a 2-hour chart, the last 12 bars (24h) inside a band, an hourly
                   close above the band top, then a wait before buying.
  Exit   (Mode A)  bought while 7d > 15d > 30d: hold until a minute closes below the 16-hour EMA.
  Exit   (Mode B)  bought at any other time: give back a share of the best profit.

$300 as 3 x $100 lots, at most 3 open, shared by both entries, first come first served.
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

WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
LOT, LOTS, INITIAL = 100.0, 3, 300.0
COIN = "eth"
EMA_HOURS = 16
DIP_STOP = 4.5
MODE_C = dict(chart=120, bars=12, zone=2.5, confirm=30, stop=3.5, arm=1.283, giveback=22.0)


def account(trades, start, end, fee):
    """$300, three $100 lots, in time order. Returns the ledger of what was actually taken."""
    cash, slots, taken = INITIAL, [], []
    peak, worst = INITIAL, 0.0
    for entry, exit_index, exit_price, source in trades:
        if not (start <= grid.TIMES[entry] < end):
            continue
        slots = [slot for slot in slots if slot[0] > entry or taken.append(None) or False] if False else slots
        matured = [slot for slot in slots if slot[0] <= entry]
        for out_index, proceeds in matured:
            cash += proceeds
        slots = [slot for slot in slots if slot[0] > entry]
        equity = cash + LOT * len(slots)
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1)
        if len(slots) >= LOTS or cash < LOT or exit_index < 0:
            continue
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        quantity = LOT / (fill * (1 + fee))
        proceeds = quantity * exit_price * (1 - grid.SLIP) * (1 - fee)
        cash -= LOT
        slots.append((exit_index, proceeds))
        taken.append({"entry": entry, "exit": exit_index, "source": source, "pnl": proceeds - LOT,
                      "hours": (exit_index - entry) / 60})
    for _, proceeds in slots:
        cash += proceeds
    frame = pd.DataFrame([row for row in taken if row])
    wins = int((frame.pnl > 0).sum()) if len(frame) else 0
    return {"profit": cash - INITIAL, "trades": len(frame), "wins": wins, "dd": worst * 100, "ledger": frame}


def evaluate(label, trades, fee=7.5 / 10_000):
    periods = {name: account(trades, *research.WINDOWS[name], fee) for name in ("full", "earlier", "later", "unseen", *WF)}
    full = periods["full"]
    ledger = full["ledger"]
    by_source = ledger.source.value_counts().to_dict() if len(ledger) else {}
    wins = ledger[ledger.pnl > 0] if len(ledger) else ledger
    losses = ledger[ledger.pnl <= 0] if len(ledger) else ledger
    return {"strategy": label, "trades": full["trades"],
            "dip": by_source.get("dip", 0), "modeC": by_source.get("breakout", 0),
            "win_rate": round(100 * full["wins"] / max(full["trades"], 1), 1),
            "avg_win": round(wins.pnl.mean(), 2) if len(wins) else 0.0,
            "avg_loss": round(losses.pnl.mean(), 2) if len(losses) else 0.0,
            "profit": round(full["profit"], 2), "earlier": round(periods["earlier"]["profit"], 2),
            "later": round(periods["later"]["profit"], 2), "unseen": round(periods["unseen"]["profit"], 2),
            "walk_forward": round(sum(periods[w]["profit"] for w in WF), 2),
            "wf_windows": f"{sum(periods[w]['profit'] > 0 for w in WF)}/6", "drawdown": round(full["dd"], 2)}


def build(raw, bullish, ema, use_ema_on, mode_c=MODE_C, dip_stop=DIP_STOP,
          dip_arm=None, dip_giveback=None):
    """Every candidate trade, in time order, with the exit its mode gives it."""
    rule = live.load_rule(COIN)
    trades = []
    for entry in live.live_entries(raw, rule):
        entry = int(entry)
        line = ema if (bullish[entry] and "dip" in use_ema_on) else None
        out, price, _ = opt.trade(entry, dip_arm or rule["activation_pct"],
                                  dip_giveback or rule["giveback_pct"], dip_stop, line)
        trades.append((entry, out, price, "dip"))
    if mode_c:
        high, low, open_, close, last_minute = v4.bars_for(raw, mode_c["chart"])
        breakout = v4.entries_for(high, low, close, last_minute, mode_c["bars"], mode_c["zone"],
                                  mode_c["confirm"], grid.CLOSE, len(raw))
        blocked = live.load_rule(COIN)["blocked"]
        if blocked:
            hours = grid.TIMES[breakout].hour
            breakout = breakout[~((hours >= blocked[0]) & (hours < blocked[1]))]
        for entry in breakout:
            entry = int(entry)
            line = ema if (bullish[entry] and "breakout" in use_ema_on) else None
            out, price, _ = opt.trade(entry, mode_c["arm"], mode_c["giveback"], mode_c["stop"], line)
            trades.append((entry, out, price, "breakout"))
    return sorted(trades, key=lambda row: row[0])


def main() -> None:
    raw = replay.load_raw(COIN.upper() + "USDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=EMA_HOURS * 60, adjust=False).mean().to_numpy()
    pd.set_option("display.width", 260)

    rows = [
        evaluate("1. dip entry, Mode B only (the old live rule)", build(raw, bullish, ema, set(), mode_c=None, dip_stop=3.5)),
        evaluate("2. dip entry, Mode A + B (deployed now)", build(raw, bullish, ema, {"dip"}, mode_c=None)),
        evaluate("3. Mode C entry alone, its own trail", build(raw, bullish, ema, set(), mode_c=MODE_C, dip_stop=DIP_STOP)[0:0]
                 + [t for t in build(raw, bullish, ema, set()) if t[3] == "breakout"]),
        evaluate("4. Mode C entry alone, Mode A + B exits", [t for t in build(raw, bullish, ema, {"breakout"}) if t[3] == "breakout"]),
        evaluate("5. all three: dip + Mode C, Mode A on dips only", build(raw, bullish, ema, {"dip"})),
        evaluate("6. all three: dip + Mode C, Mode A on everything", build(raw, bullish, ema, {"dip", "breakout"})),
    ]
    print("=== ETH, $300 as 3 x $100 lots, BNB fees")
    print(pd.DataFrame(rows).set_index("strategy").to_string())

    print("\n=== does Mode C's own setting matter inside the combined system?")
    tuned = []
    for zone in (2.0, 2.5, 3.0):
        for confirm in (15, 30, 60):
            setting = {**MODE_C, "zone": zone, "confirm": confirm}
            tuned.append(evaluate(f"zone {zone}%, wait {confirm}m",
                                  build(raw, bullish, ema, {"dip", "breakout"}, mode_c=setting)))
    print(pd.DataFrame(tuned).set_index("strategy").to_string())


if __name__ == "__main__":
    main()
