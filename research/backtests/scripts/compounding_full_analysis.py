"""Full re-check of compounding_strategy.md: the live money rule against the shared-pot growth plan.

Same five deployed rule books, one real-cash wallet, first come first served, 7.5 bps fee + 2 bps slippage per side.

  LIVE      what live_execution_service does today: every coin has its own lots (ETH 5, SOL/BTC/AAVE/TRX 3) of $100,
            no global slot limit, and a buy spends the full lot or whatever free USDT is left. Profits stay in the
            wallet, so as cash grows the bot can hold more $100 lots at once - live already compounds by COUNT.
  PLAN      the document: $300, 3 global slots; slot 4 at $400, slot 5 at $500 marked high-water; after that each
            further $100 adds share x $100 / N to every requested lot (5 slots, 100% share = +$20 per lot).
  FIXED     N global slots x $100, never grows.
  CONT      N global slots, lot = marked equity / N at each buy (continuous compounding, can shrink).

Marked equity at a decision uses the PREVIOUS minute's close (the earlier script used the entry minute's close,
a one-minute look-ahead). Lots still open at the end of a window are closed at the last close.
"""

from __future__ import annotations

import math
import pickle
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
INPUTS = ROOT / "data" / "compounding_full_v1" / "inputs.pkl"
OUT = ROOT / "results" / "compounding_full_v1"
COINS = ("ETH", "TRX", "BTC", "AAVE", "SOL")
LIVE_CAPS = {"ETH": 5, "SOL": 3, "BTC": 3, "AAVE": 3, "TRX": 3}
MIN_ORDER = 5.0
T = lambda s: pd.Timestamp(s, tz="UTC")  # noqa: E731
START, END = T("2024-10-01"), T("2026-09-10")


@dataclass(frozen=True)
class Policy:
    name: str
    kind: str                      # live | plan | fixed | cont
    initial: float = 300.0
    slots: int = 5                 # plan: maximum slots; fixed/cont: slots
    share: float = 1.0             # plan only
    lot: float = 100.0
    caps: dict | None = field(default=None, hash=False, compare=False)

    def limits(self, high_water: float, equity: float) -> tuple[float, float]:
        """(global slots, requested lot) at this moment."""
        if self.kind == "live":
            return math.inf, self.lot
        if self.kind == "fixed":
            return self.slots, self.lot
        if self.kind == "cont":
            return self.slots, max(MIN_ORDER, equity / self.slots)
        if self.kind == "step":                                          # share field = $ added per lot
            steps = int((high_water - self.initial + 1e-9) // 100)
            extra = max(0, steps - (self.slots - 3))
            return min(self.slots, 3 + max(0, steps)), self.lot + extra * self.share
        steps = int((high_water - self.initial + 1e-9) // 100)          # $100 milestones reached
        slots = min(self.slots, 3 + max(0, steps))
        extra = max(0, steps - (self.slots - 3))                          # milestones after the last slot unlock
        return slots, self.lot + extra * self.share * 100 / self.slots


def load():
    with open(INPUTS, "rb") as handle:
        markets, candidates, _ = pickle.load(handle)
    return markets, candidates


def replay(markets, candidates, policy: Policy, start=START, end=END, fee=7.5, slip=2.0, tie_seed=None,
           want_frames=False):
    fee, slip = fee / 10_000, slip / 10_000
    order = {coin: n for n, coin in enumerate(COINS)}
    pool = [c for c in candidates if start <= c.entry_time < end]
    if tie_seed is None:
        pool.sort(key=lambda c: (c.entry_time, order[c.coin], c.candidate_id))
    else:
        rng = random.Random(tie_seed)
        keys = {c.candidate_id: rng.random() for c in pool}
        pool.sort(key=lambda c: (c.entry_time, keys[c.candidate_id]))
    cash = high_water = policy.initial
    opened, ledger, blocked = [], [], 0
    caps = policy.caps or (LIVE_CAPS if policy.kind == "live" else None)
    for cand in pool:
        still = []
        for lot in opened:
            if lot["exit_time"] <= cand.entry_time:
                cash += lot["proceeds"]
            else:
                still.append(lot)
        opened = still
        equity = cash
        for lot in opened:
            m = markets[lot["coin"]]
            i = max(0, int(m.times.searchsorted(cand.entry_time, side="left")) - 1)
            equity += lot["quantity"] * float(m.close[i]) * (1 - slip) * (1 - fee)
        high_water = max(high_water, equity)
        slots, requested = policy.limits(high_water, equity)
        if len(opened) >= slots or (caps and sum(l["coin"] == cand.coin for l in opened) >= caps[cand.coin]):
            blocked += 1
            continue
        spend = min(requested, math.floor(cash * 100) / 100)
        if spend < MIN_ORDER:
            blocked += 1
            continue
        m = markets[cand.coin]
        if cand.exit_time >= end:
            xi = int(m.times.searchsorted(end)) - 1
            raw_exit = float(m.close[xi])
        else:
            xi, raw_exit = cand.exit_index, cand.exit_price
        fill = float(m.open[cand.entry_index]) * (1 + slip)
        qty = spend / (fill * (1 + fee))
        proceeds = qty * raw_exit * (1 - slip) * (1 - fee)
        lot = {"coin": cand.coin, "source": cand.source, "entry_time": cand.entry_time,
               "exit_time": m.times[xi], "spend": spend, "requested": requested, "quantity": qty,
               "proceeds": proceeds, "pnl": proceeds - spend}
        cash -= spend
        opened.append(lot)
        ledger.append(lot)
    led = pd.DataFrame(ledger)
    eq = mark_equity(markets, led, policy.initial, start, end, fee, slip)
    profit = float(led.pnl.sum()) if len(led) else 0.0
    peak = eq.equity.cummax()
    dd_usd, dd_pct = float((eq.equity - peak).min()), float((eq.equity / peak - 1).min() * 100)
    monthly = eq.set_index("timestamp").equity.resample("MS").last()
    month_ret = monthly.pct_change().dropna() * 100
    summary = {"plan": policy.name, "start_money": policy.initial, "profit": profit,
               "end_equity": policy.initial + profit, "return_pct": 100 * profit / policy.initial,
               "trades": len(led), "blocked": blocked,
               "win_pct": 100 * float((led.pnl > 0).mean()) if len(led) else 0.0,
               "dd_usd": dd_usd, "dd_pct": dd_pct,
               "profit_per_dd": profit / abs(dd_usd) if dd_usd else np.nan,
               "max_order": float(led.spend.max()) if len(led) else 0.0,
               "avg_order": float(led.spend.mean()) if len(led) else 0.0,
               "worst_month_pct": float(month_ret.min()) if len(month_ret) else 0.0,
               "avg_open_value": float(eq.open_value.mean())}
    return (summary, led, eq) if want_frames else summary


def mark_equity(markets, led, initial, start, end, fee, slip):
    marks = pd.date_range(start, end, freq="1h", inclusive="left")
    value = np.full(len(marks), initial, dtype=float)
    open_value = np.zeros(len(marks))
    for lot in led.to_dict("records") if len(led) else []:
        active = (marks >= lot["entry_time"]) & (marks < lot["exit_time"])
        value[marks >= lot["exit_time"]] += lot["pnl"]
        if active.any():
            m = markets[lot["coin"]]
            idx = m.times.searchsorted(marks[active], side="right") - 1
            worth = lot["quantity"] * m.close[idx] * (1 - slip) * (1 - fee)
            value[active] += worth - lot["spend"]
            open_value[active] += worth
    return pd.DataFrame({"timestamp": marks, "equity": value, "open_value": open_value})


def policies():
    out = {"LIVE $300": Policy("LIVE $300", "live", 300.0),
           "PLAN 5 slots +$20": Policy("PLAN 5 slots +$20", "plan", 300.0, 5, 1.0)}
    for n in range(3, 11):
        for share in (0.0, 0.5, 0.75, 1.0):
            name = f"PLAN {n} slots {int(share * 100)}%"
            out.setdefault(name, Policy(name, "plan", 300.0, n, share))
    for n in (3, 5):
        out[f"FIXED {n}x$100"] = Policy(f"FIXED {n}x$100", "fixed", 300.0, n)
        out[f"CONT {n} slots"] = Policy(f"CONT {n} slots", "cont", 300.0, n)
    return out


if __name__ == "__main__":
    markets, candidates = load()
    pd.set_option("display.width", 250)
    rows = [replay(markets, candidates, p) for p in policies().values()]
    print(pd.DataFrame(rows).round(2).to_string(index=False))
