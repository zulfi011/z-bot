"""SOL capitulation reversal: buy when a sharp sell-off's forced selling runs out.

Hourly bars built from 1-minute data (volume and taker-buy volume from Binance; aggressive SELLING =
volume - taker buy):

  drop     the hour's close is at least D% below the highest high of the previous 12 / 24 / 48 hours
  climax   that hour's aggressive selling is at least M x its own 7-day hourly average (or no volume test)
  turn     what has to happen next: the next hour closes green and its selling is under half the climax hour's,
           just a green hour, or a reclaim - the next hour closes back above the climax hour's high
  buy      the first minute after the turn hour closes, at most one entry per 24 hours
  exit     SOL's deployed dip exit (stop -2%), the same trail with a -6% or -10% stop (a capitulation bounce is
           violent and SOL's tight stop may be hit by the last flush), always Mode A, or always Mode B
  lots     SHARED with SOL's 3 deployed lots, or 1-3 lots of its own

No downtrend filter and no blocked hours: a capitulation happens BECAUSE the market is breaking down, and the
core's filters were fitted to a different rule. Corrected window engine, hourly mark-to-market drawdown,
walk-forward selection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import eth_regime as rg
import sol_volume_filter as vf
import sol_wide_stop as w
from sol_wide_stop import CORE, TRAINS, simulate

CAP = {"capitulation"}
DROPS = [4.0, 5.0, 6.0, 8.0, 10.0, 12.0]
LOOKBACKS = [12, 24, 48]
CLIMAX = [None, 2.0, 3.0, 5.0]
TURNS = ["green + calmer", "green", "reclaim"]
EXITS = ["deployed", "stop -6%", "stop -10%", "mode a", "mode b"]
SIZES = [1, 2, 3]


class Events:
    """Hourly bars with the two things a capitulation needs: how far it fell, and how hard it was sold."""

    def __init__(self, raw: pd.DataFrame):
        v = raw.set_index("open_time")
        h = pd.DataFrame({"open": v.open.resample("1h").first(), "high": v.high.resample("1h").max(),
                          "low": v.low.resample("1h").min(), "close": v.close.resample("1h").last(),
                          "volume": v.volume.resample("1h").sum(),
                          "taker_buy": v.taker_buy_base_volume.resample("1h").sum(),
                          "n": v.close.resample("1h").size()})
        h = h[h.n == 60]
        h["sell"] = h.volume - h.taker_buy
        h["sell_avg"] = h.sell.rolling(24 * 7).mean().shift(1)
        self.h = h
        self.act = np.searchsorted(w.grid.TIMES, h.index + pd.Timedelta(hours=1))
        self._prior = {}

    def prior_high(self, hours):
        if hours not in self._prior:
            self._prior[hours] = self.h.high.rolling(hours).max().shift(1).to_numpy()
        return self._prior[hours]

    def signals(self, drop, lookback, climax, turn):
        h = self.h
        close, open_, high = h.close.to_numpy(), h.open.to_numpy(), h.high.to_numpy()
        sell = h.sell.to_numpy()
        down = close / self.prior_high(lookback) - 1 <= -drop / 100
        spike = np.ones(len(h), bool) if climax is None else (sell >= climax * h.sell_avg.to_numpy())
        green_next = np.r_[close[1:] > open_[1:], False]
        if turn == "green + calmer":
            confirm = green_next & np.r_[sell[1:] < 0.5 * sell[:-1], False]
        elif turn == "green":
            confirm = green_next
        else:
            confirm = np.r_[close[1:] > high[:-1], False]                  # the next hour reclaims the flush
        turns = np.flatnonzero(down & spike & confirm) + 1
        kept, last = [], -10 ** 9
        for t in turns:
            if t < len(self.act) and self.act[t] < len(w.grid.OPEN) - 1 and t - last >= 24:
                kept.append(t)
                last = t
        return np.asarray(kept, dtype=np.int64)


def build(events, rule, bullish, ema, drop, lookback, climax, turn, exit_style):
    stop = {"deployed": rule["stop_pct"], "stop -6%": 6.0, "stop -10%": 10.0,
            "mode a": rule["stop_pct"], "mode b": rule["stop_pct"]}[exit_style]
    trades = []
    for hour in events.signals(drop, lookback, climax, turn):
        entry = int(events.act[hour])
        line = ema if (exit_style == "mode a" or (exit_style != "mode b" and bullish[entry])) else None
        exit_at, price, why = w.resolve(entry, rule["activation_pct"], rule["giveback_pct"], stop, line)
        trades.append({"entry": entry, "exit": exit_at, "price": price, "source": "capitulation", "why": why})
    return trades


def name_of(key):
    drop, lookback, climax, turn, exit_style = key
    return (f"-{drop:g}% under the {lookback}h high, "
            f"{'no volume test' if climax is None else f'selling {climax:g}x'}, {turn}, {exit_style}")


def main() -> None:
    raw, bullish, ema = vf.setup()
    rule, dips, breaks = w.signals(raw)
    core = w.core_trades(rule, dips, breaks, bullish, ema)
    events = Events(raw)
    pd.set_option("display.width", 280)

    base = w.score("SOL as deployed, 3 x $100", core, [(3, CORE)])
    controls = {n: w.score(f"flat core {n} (control)", core, [(n, CORE)]) for n in (4, 5, 6)}
    print("=== the controls")
    print(pd.DataFrame([base, *controls.values()]).set_index("setup").to_string())

    keys = [(d, lb, c, t, e) for d in DROPS for lb in LOOKBACKS for c in CLIMAX for t in TURNS for e in EXITS]
    sets = {key: build(events, rule, bullish, ema, *key) for key in keys}
    sets = {key: trades for key, trades in sets.items() if trades}
    counts = pd.Series({name_of(k): len(v) for k, v in sets.items()})
    print(f"\n{len(sets)} capitulation rules that fire at all; signals per rule: median {counts.median():.0f}, "
          f"range {counts.min()}-{counts.max()}")

    print("\n=== 1. capitulation ALONE, on its own money (2 x $100) - best 10 by walk-forward")
    rows = [w.score(name_of(key), trades, [(2, CAP)]) for key, trades in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  rules that made money alone over the full window: {int((frame.profit > 0).sum())}/{len(frame)}")

    print("\n=== 2. SHARED: capitulation competes for SOL's 3 deployed lots")
    rows = [base] + [w.score(name_of(key), sorted(core + trades, key=lambda t: t["entry"]), [(3, CORE | CAP)])
                     for key, trades in sets.items()]
    frame2 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame2.set_index("setup").head(8).to_string())
    print(f"  beating no capitulation: {int((frame2.walk_forward > base['walk_forward']).sum())}/{len(frame2) - 1}"
          f" on walk-forward, {int((frame2.profit > base['profit']).sum())}/{len(frame2) - 1} on the full window")

    print("\n=== 3. SEPARATE: the core carries on, capitulation holds lots of its own")
    for size in SIZES:
        control = controls[3 + size]
        rows = [w.score(name_of(key), sorted(core + trades, key=lambda t: t["entry"]), [(3, CORE), (size, CAP)])
                for key, trades in sets.items()]
        part = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
        print(f"\n  --- own {size} (${(3 + size) * 100}) against flat core {3 + size} "
              f"(+${control['walk_forward']:.2f}, {control['windows']}, {control['mtm_dd%']}%)")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating that control: {int((part.walk_forward > control['walk_forward']).sum())}/{len(part)} "
              f"on walk-forward, {int((part['mtm_dd%'] > control['mtm_dd%']).sum())}/{len(part)} on drawdown")

    print("\n=== 4. the honest test: the rule is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for label, pots, control_pots in (("shared, 3 lots", [(3, CORE | CAP)], [(3, CORE)]),
                                      ("own 1", [(3, CORE), (1, CAP)], [(4, CORE)]),
                                      ("own 2", [(3, CORE), (2, CAP)], [(5, CORE)]),
                                      ("own 3", [(3, CORE), (3, CAP)], [(6, CORE)])):
        control_w = {x: simulate(core, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        scores = {key: {x: simulate(sorted(core + trades, key=lambda t: t["entry"]), pots,
                                    *research.WINDOWS[x])["profit"] for x in windows}
                  for key, trades in sets.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(sets, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        print(f"\n  --- {label}")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    best fixed rule in hindsight {name_of(best)}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")


if __name__ == "__main__":
    main()
