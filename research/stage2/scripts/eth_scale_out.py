"""Does selling ETH in two pieces beat selling it in one?

Today a lot is all-or-nothing: $100 in, one exit out. Scaling out sells a fraction at a first target and
lets the rest run on the deployed rule - Mode A's EMA hold or Mode B's giveback trail.

  target never reached   the lot behaves exactly as deployed, nothing is sold early
  target reached first   `fraction` is sold there, the remainder exits by the deployed rule
  stop hit first         the whole lot stops out, exactly as deployed

The take-profit piece is a limit sell, so it fills AT the target even on a gap up - the same conservative
convention the protective stop uses in reverse.

Because fees and slippage are proportional to notional, two sells cost the same as one, and a split exit
can be expressed as one effective price:  f x target + (1 - f) x runner_price.  That keeps the account
model in three_modes.py untouched, so the baseline still reproduces the deployed figures exactly.

Also tested: a LOOSER trail on the runner. Once half is banked the lot is already green, so the remainder
can afford to give back more (50% instead of 30%) in exchange for catching the occasional real trend.
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


def scale_trade(entry, arm, giveback, stop, ema, target_pct, fraction, runner_giveback=None):
    """One lot, sold in two pieces. Returns (exit index of the LAST piece, effective price, code)."""
    base_out, base_price, code = opt.trade(entry, arm, giveback, stop, ema)
    if target_pct is None or base_out < 0:
        return base_out, base_price, code
    fill = grid.OPEN[entry] * (1 + grid.SLIP)
    target = fill * (1 + target_pct / 100)
    hit = research.first_hit(entry, target, True)
    if hit < 0 or hit > base_out:
        return base_out, base_price, code                      # the lot closed before the target
    if runner_giveback is None or ema is not None:
        runner_out, runner_price = base_out, base_price        # Mode A lots keep the EMA hold
    else:
        runner_out, runner_price, _ = opt.trade(entry, arm, runner_giveback, stop, ema)
        if runner_out < 0:                                     # a looser trail can outlive the data
            runner_out, runner_price = len(grid.CLOSE) - 1, grid.CLOSE[-1]
    return runner_out, fraction * target + (1 - fraction) * runner_price, code


def build(raw, bullish, ema, mode_c, target=None, fraction=0.5, runner_giveback=None, scope=("dip", "breakout")):
    rule = live.load_rule(COIN)
    trades = []
    for entry in live.live_entries(raw, rule):
        entry = int(entry)
        line = ema if bullish[entry] else None
        use = target if "dip" in scope else None
        out, price, _ = scale_trade(entry, rule["activation_pct"], rule["giveback_pct"], tm.DIP_STOP,
                                    line, use, fraction, runner_giveback)
        trades.append((entry, out, price, "dip"))
    for entry in mode_c:
        entry = int(entry)
        line = ema if bullish[entry] else None
        use = target if "breakout" in scope else None
        out, price, _ = scale_trade(entry, tm.MODE_C["arm"], tm.MODE_C["giveback"], tm.MODE_C["stop"],
                                    line, use, fraction, runner_giveback)
        trades.append((entry, out, price, "breakout"))
    return sorted(trades, key=lambda row: row[0])


def mode_c_entries(raw):
    mc = tm.MODE_C
    high, low, open_, close, last_minute = v4.bars_for(raw, mc["chart"])
    entries = v4.entries_for(high, low, close, last_minute, mc["bars"], mc["zone"], mc["confirm"],
                             grid.CLOSE, len(raw))
    blocked = live.load_rule(COIN)["blocked"]
    hours = grid.TIMES[entries].hour
    return entries[~((hours >= blocked[0]) & (hours < blocked[1]))]


def setup():
    raw = replay.load_raw("ETHUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=tm.EMA_HOURS * 60, adjust=False).mean().to_numpy()
    return raw, bullish, ema, mode_c_entries(raw)


def main() -> None:
    raw, bullish, ema, entries = setup()
    pd.set_option("display.width", 280)
    base = tm.evaluate("sell all at once (deployed today)", build(raw, bullish, ema, entries))

    print("=== 1. sell HALF at a first target, remainder on the deployed rule")
    rows = [base]
    for target in (1.0, 1.5, 2.0, 3.0):
        rows.append(tm.evaluate(f"half out at +{target}%", build(raw, bullish, ema, entries, target=target)))
    print(pd.DataFrame(rows).set_index("strategy").to_string())

    print("\n=== 2. how much to sell at +1.5%")
    rows = [base]
    for fraction in (0.25, 0.33, 0.5, 0.67, 0.75):
        rows.append(tm.evaluate(f"{int(fraction * 100)}% out at +1.5%",
                                build(raw, bullish, ema, entries, target=1.5, fraction=fraction)))
    print(pd.DataFrame(rows).set_index("strategy").to_string())

    print("\n=== 3. bank half, then give the runner a LOOSER leash (Mode B lots; Mode A keeps its EMA)")
    rows = [base]
    for target in (1.0, 1.5, 2.0):
        for runner in (40.0, 50.0, 60.0):
            rows.append(tm.evaluate(f"half out at +{target}%, runner gives back {runner:.0f}%",
                                    build(raw, bullish, ema, entries, target=target, runner_giveback=runner)))
    print(pd.DataFrame(rows).set_index("strategy").to_string())

    print("\n=== 4. which entry should scale out?")
    rows = [base]
    for scope, title in ((("dip",), "dip lots only"), (("breakout",), "Mode C lots only"),
                         (("dip", "breakout"), "both")):
        rows.append(tm.evaluate(f"half out at +1.5%, {title}",
                                build(raw, bullish, ema, entries, target=1.5, scope=scope)))
    print(pd.DataFrame(rows).set_index("strategy").to_string())


if __name__ == "__main__":
    main()
