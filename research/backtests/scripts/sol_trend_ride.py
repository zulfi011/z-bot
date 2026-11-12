"""SOL live rule: the problem is that it sells into strength. Four ways to fix it, measured together.

The live rule (sol_strategy.json): 3-minute signal candles, 12-day average, +-0.5% touch zone from below,
bullish-candle confirmation within 30 minutes, no entries 06:00-12:00 UTC, avoid-strong-bearish filter,
stop -2%, trailing armed at +1.251% giving back 12%.

Its weakness: the trailing stop takes about +1.1% and leaves the rest of the move behind, while every loss is
a full -2%. Tested here:

  base      the live rule, unchanged
  chain     after a trailing exit, wait W minutes; if price is above the exit price, buy again and keep going.
            The chain ends on a downtrend signal - see DOWNTREND below.
  giveback  the same rule but giving back more of the open profit (12 -> 50%), so winners run further
  trend     after the trail arms, ignore the giveback and hold until a 1-minute close below an EMA
  half      sell half at the usual trailing exit, ride the rest on the EMA

DOWNTREND (how a chain is ended), each tested on its own:
  lower_high  the new trade's peak fails to beat the previous trade's peak
  any_loss    the new trade closes below its entry
  ema_break   price closes below the EMA
  two_fails   like lower_high, but one failure is forgiven and two in a row end it
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

SYMBOL = "SOLUSDT"
SIGNAL_MINUTES, AVERAGE_DAYS, ZONE_PCT = 3, 12, 0.5
BLOCKED = (6, 12)
STOP_PCT, ACTIVATION_PCT, GIVEBACK_PCT = 2.0, 1.251, 12.0
WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
FEE, SLIP = 7.5 / 10_000, 2 / 10_000
LOT = 100.0
MAX_CHAIN = 10


def live_entries(raw: pd.DataFrame) -> np.ndarray:
    """Raw 1-minute entry indices for the live SOL rule, including its 12-day average and blocked hours."""
    daily = replay.daily_averages(raw)
    average_n = replay.daily_average_n(raw, AVERAGE_DAYS)
    frame = grid.signal_frame(raw, daily, SIGNAL_MINUTES)
    for period in (7, 15, 30):
        frame[period] = np.array([np.nan if value is None else float(value) for value in frame[period]])
    days = frame["open_time"].floor("D")
    frame[AVERAGE_DAYS] = np.array([float(average_n[day]) if average_n.get(day) is not None else np.nan
                                    for day in days])
    config = {"signal_minutes": SIGNAL_MINUTES, "average_days": AVERAGE_DAYS, "zone_pct": ZONE_PCT,
              "approach": "from_below", "market_filter": "avoid_strong_bearish"}
    signals = grid.fast_signals(frame, config)
    entries = signals.entry_index.to_numpy(np.int64)
    entries = entries[entries < len(raw) - 1]
    hours = pd.DatetimeIndex(raw.open_time).hour.to_numpy()[entries]
    return entries[~((hours >= BLOCKED[0]) & (hours < BLOCKED[1]))]


def trade(entry: int, activation_pct, giveback_pct, ema=None, ema_exit=False):
    """One position. Returns (exit index, exit price, reason, peak price)."""
    fill = grid.OPEN[entry] * (1 + SLIP)
    stop_level = fill * (1 - STOP_PCT / 100)
    armed = research.first_hit(entry, fill * (1 + activation_pct / 100), True)
    stopped = research.first_hit(entry, stop_level, False, None if armed < 0 else armed)
    if stopped >= 0 and (armed < 0 or stopped <= armed):
        return stopped, min(stop_level, grid.OPEN[stopped]), "stop", grid.HIGH[entry:stopped + 1].max()
    if armed < 0:
        return -1, np.nan, "open", grid.HIGH[entry:].max()
    if ema_exit:
        peak = grid.HIGH[armed]
        for position in range(armed + 1, len(grid.CLOSE)):
            peak = max(peak, grid.HIGH[position])
            if grid.CLOSE[position] < ema[position] or grid.LOW[position] <= stop_level:
                price = min(grid.OPEN[position], ema[position]) if grid.CLOSE[position] < ema[position] \
                    else min(stop_level, grid.OPEN[position])
                return position, price, "trend", peak
        return -1, np.nan, "open", peak
    hit, price = research.trail_exit(armed, fill, giveback_pct)
    if hit < 0:
        return -1, np.nan, "open", grid.HIGH[armed:].max()
    return hit, min(price, grid.OPEN[hit]), "trail", grid.HIGH[entry:hit + 1].max()


def sequence(entries, mode, times, start, end, wait=0, downtrend="lower_high", giveback=GIVEBACK_PCT,
             ema=None, half_giveback=50.0):
    """Walk the signals in time order, one position at a time, applying one variant."""
    cash, taken, peak_equity, worst = LOT, [], LOT, 0.0
    busy_until = -1
    for entry in entries:
        if entry <= busy_until or not (start <= times[entry] < end):
            continue
        chain_peak, forgiven = 0.0, 0
        position, link = int(entry), 0
        while True:
            ema_exit = mode in ("trend", "chain_trend")
            out, price, reason, high = trade(position, ACTIVATION_PCT,
                                             giveback if mode != "giveback" else giveback,
                                             ema=ema, ema_exit=ema_exit)
            if out < 0:
                break
            fill = grid.OPEN[position] * (1 + SLIP)
            if mode == "half":
                out2, price2, reason2, _ = trade(position, ACTIVATION_PCT, GIVEBACK_PCT)
                first = 0.5 * (price2 / fill) if out2 >= 0 else 0.0
                out3, price3, reason3, _ = trade(position, ACTIVATION_PCT, GIVEBACK_PCT, ema=ema, ema_exit=True)
                second = 0.5 * (price3 / fill) if out3 >= 0 else 0.5 * (price / fill)
                gross = first + second
                out = max(out2, out3)
                price = fill * gross
            change = (price * (1 - SLIP) * (1 - FEE)) / (fill * (1 + FEE)) - 1
            cash *= 1 + change
            taken.append({"entry_time": times[position], "return_pct": change * 100, "reason": reason,
                          "link": link, "hours": (out - position) / 60})
            peak_equity = max(peak_equity, cash)
            worst = min(worst, cash / peak_equity - 1)
            busy_until = out
            if mode not in ("chain", "chain_trend") or reason == "stop" or link >= MAX_CHAIN:
                break
            # --- the chain: wait, look for another bullish signal, decide whether the trend is over
            check = out + wait
            if check >= len(grid.CLOSE) - 1:
                break
            failed = False
            if downtrend == "lower_high":
                failed = link > 0 and high <= chain_peak
            elif downtrend == "any_loss":
                failed = change <= 0
            elif downtrend == "ema_break":
                failed = grid.CLOSE[check] < ema[check]
            elif downtrend == "two_fails":
                if link > 0 and high <= chain_peak:
                    forgiven += 1
                    failed = forgiven >= 2
                else:
                    forgiven = 0
            chain_peak = max(chain_peak, high)
            if failed or grid.CLOSE[check] <= price:            # no fresh bullish confirmation
                break
            position, link = check + 1, link + 1
            busy_until = position
    frame = pd.DataFrame(taken)
    wins = int((frame.return_pct > 0).sum()) if len(frame) else 0
    return {"profit": cash - LOT, "trades": len(frame), "wins": wins, "dd": worst * 100,
            "links": int((frame.link > 0).sum()) if len(frame) else 0,
            "avg_win": frame.loc[frame.return_pct > 0, "return_pct"].mean() if wins else 0.0,
            "avg_loss": frame.loc[frame.return_pct <= 0, "return_pct"].mean() if len(frame) > wins else 0.0,
            "ledger": frame}


def evaluate(label, entries, times, **kwargs):
    periods = {name: sequence(entries, times=times, start=research.WINDOWS[name][0],
                              end=research.WINDOWS[name][1], **kwargs)
               for name in ("full", "earlier", "later", "unseen", *WF)}
    full = periods["full"]
    return {"variant": label, "trades": full["trades"], "extra_buys": full["links"],
            "win_rate": round(100 * full["wins"] / max(full["trades"], 1)),
            "avg_win_pct": full["avg_win"], "avg_loss_pct": full["avg_loss"],
            "full": full["profit"], "earlier": periods["earlier"]["profit"],
            "later": periods["later"]["profit"], "unseen": periods["unseen"]["profit"],
            "walk_forward": sum(periods[w]["profit"] for w in WF),
            "wf_windows": f"{sum(periods[w]['profit'] > 0 for w in WF)}/6", "drawdown": full["dd"]}


def main() -> None:
    raw = replay.load_raw(SYMBOL, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP, grid.FEE = SLIP, FEE
    times = pd.DatetimeIndex(raw.open_time)
    entries = live_entries(raw)
    print(f"{len(entries)} live entry signals ({times[entries].min().date()} to {times[entries].max().date()})",
          flush=True)
    emas = {span: pd.Series(grid.CLOSE).ewm(span=span, adjust=False).mean().to_numpy() for span in (30, 60, 120, 240)}

    rows = [evaluate("base (live rule today)", entries, times, mode="base")]
    print(pd.DataFrame(rows).round(2).to_string(index=False), flush=True)

    for wait in [3, 5, 7, 10, 15, 20, 30]:
        rows.append(evaluate(f"chain, wait {wait}m, lower-high stop", entries, times, mode="chain", wait=wait,
                             downtrend="lower_high", ema=emas[60]))
    for rule in ["any_loss", "ema_break", "two_fails"]:
        rows.append(evaluate(f"chain, wait 5m, {rule} stop", entries, times, mode="chain", wait=5,
                             downtrend=rule, ema=emas[60]))
    for give in [20.0, 30.0, 40.0, 50.0]:
        rows.append(evaluate(f"giveback {give:g}% instead of 12%", entries, times, mode="giveback", giveback=give))
    for span in [30, 60, 120, 240]:
        rows.append(evaluate(f"hold to EMA{span} break", entries, times, mode="trend", ema=emas[span]))
        rows.append(evaluate(f"half out, rest to EMA{span}", entries, times, mode="half", ema=emas[span]))

    out = pd.DataFrame(rows)
    out.to_csv(grid.ROOT / "results" / "sol_trend_ride.csv", index=False)
    pd.set_option("display.width", 250)
    print("\n=== SOL live rule, one $100 lot, BNB fees")
    print(out.set_index("variant").round(2).to_string())


if __name__ == "__main__":
    main()
