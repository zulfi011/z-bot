"""Ideas taken from github.com/Jakeschincariol/day-trader-skill (trader-risk / trader-budget), on the live shared pot.

Same five deployed rule books and candidates as compounding_full_analysis (inputs.pkl), one wallet, $300 as
3 x $100 shared lots (the live pot), 7.5 bps fee + 2 bps slippage per side, lots open at a window's end closed at
its last close.

  cooldown   after a coin's losing lot closes, that coin takes no new entry for H hours
  streak     after K losing lots in a row on a coin, that coin takes no new entry for H hours
  daily      once the day's (UTC) closed losses reach $X, nothing new opens until the next UTC day
  per_day    at most N entries per coin per UTC day
  risk       equal dollar risk per lot (trader-budget's sizing): lot = R / stop%, so a 2% stop gets twice the lot
             of a 4% stop; R is set so the average lot is about $100 and compared against flat lots

A loss is known only once its lot has closed before the candidate's entry minute, so nothing looks ahead.
Honest gate: on each of the six walk-forward windows, choose the best setting (including "off") on the train
window, run it fresh on the test window, sum, and compare with "off".
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compounding_full_analysis as ca  # noqa: E402

STOPS = {("ETH", "dip"): 4.5, ("ETH", "pullback"): 4.5, ("ETH", "breakout"): 3.5,
         ("SOL", "dip"): 2.0, ("SOL", "breakout"): 4.0, ("BTC", "dip"): 3.0,
         ("AAVE", "dip"): 4.0, ("AAVE", "breakout"): 3.5, ("TRX", "dip"): 4.0, ("TRX", "breakout"): 3.0}
H = pd.Timedelta(hours=1)


@dataclass(frozen=True)
class Rule:
    name: str
    cooldown_h: float = 0
    streak_k: int = 0
    streak_h: float = 0
    daily_usd: float = 0
    per_day: int = 0
    risk_usd: float = 0
    slots: int = 3
    lot: float = 100.0


def replay(markets, candidates, rule: Rule, start, end, fee=7.5, slip=2.0):
    fee, slip = fee / 10_000, slip / 10_000
    order = {coin: n for n, coin in enumerate(ca.COINS)}
    pool = sorted((c for c in candidates if start <= c.entry_time < end),
                  key=lambda c: (c.entry_time, order[c.coin], c.candidate_id))
    cash = 100.0 * rule.slots                                  # same wallet whatever the lot size
    opened, ledger, closed = [], [], []
    blocked_until, streak, day_loss, day_count = {}, {}, {}, {}
    for cand in pool:
        still = []
        for lot in sorted(opened, key=lambda l: l["exit_time"]):
            if lot["exit_time"] <= cand.entry_time:
                cash += lot["proceeds"]
                coin, loss = lot["coin"], lot["pnl"] < 0
                if loss and rule.cooldown_h:
                    blocked_until[coin] = max(blocked_until.get(coin, lot["exit_time"]),
                                              lot["exit_time"] + rule.cooldown_h * H)
                streak[coin] = streak.get(coin, 0) + 1 if loss else 0
                if rule.streak_k and streak[coin] >= rule.streak_k:
                    blocked_until[coin] = max(blocked_until.get(coin, lot["exit_time"]),
                                              lot["exit_time"] + rule.streak_h * H)
                    streak[coin] = 0
                if loss:
                    d = lot["exit_time"].floor("D")
                    day_loss[d] = day_loss.get(d, 0.0) - lot["pnl"]
            else:
                still.append(lot)
        opened = still
        coin, today = cand.coin, cand.entry_time.floor("D")
        if len(opened) >= rule.slots:
            continue
        if blocked_until.get(coin) is not None and cand.entry_time < blocked_until[coin]:
            continue
        if rule.daily_usd and day_loss.get(today, 0.0) >= rule.daily_usd:
            continue
        if rule.per_day and day_count.get((coin, today), 0) >= rule.per_day:
            continue
        requested = rule.risk_usd / (STOPS[(coin, cand.source)] / 100) if rule.risk_usd else rule.lot
        spend = min(requested, math.floor(cash * 100) / 100)
        if spend < ca.MIN_ORDER:
            continue
        m = markets[coin]
        if cand.exit_time >= end:
            xi = int(m.times.searchsorted(end)) - 1
            raw_exit = float(m.close[xi])
        else:
            xi, raw_exit = cand.exit_index, cand.exit_price
        fill = float(m.open[cand.entry_index]) * (1 + slip)
        qty = spend / (fill * (1 + fee))
        proceeds = qty * raw_exit * (1 - slip) * (1 - fee)
        lot = {"coin": coin, "source": cand.source, "entry_time": cand.entry_time, "exit_time": m.times[xi],
               "spend": spend, "quantity": qty, "proceeds": proceeds, "pnl": proceeds - spend}
        cash -= spend
        day_count[(coin, today)] = day_count.get((coin, today), 0) + 1
        opened.append(lot)
        ledger.append(lot)
    led = pd.DataFrame(ledger)
    eq = ca.mark_equity(markets, led, 100.0 * rule.slots, start, end, fee, slip)
    peak = eq.equity.cummax()
    return {"rule": rule.name, "profit": float(led.pnl.sum()) if len(led) else 0.0, "trades": len(led),
            "win_pct": 100 * float((led.pnl > 0).mean()) if len(led) else 0.0,
            "dd_pct": float((eq.equity / peak - 1).min() * 100), "avg_lot": float(led.spend.mean()) if len(led) else 0,
            "avg_open_value": float(eq.open_value.mean())}


def families(slots=3):
    off = Rule("off", slots=slots)
    fam = {
        "cooldown": [off] + [Rule(f"cooldown {h}h", cooldown_h=h, slots=slots) for h in (2, 6, 12, 24, 48, 72, 96, 120, 168)],
        "streak": [off] + [Rule(f"streak {k} -> {h}h", streak_k=k, streak_h=h, slots=slots)
                           for k in (2, 3) for h in (12, 24, 48, 96)],
        "daily": [off] + [Rule(f"daily loss ${x}", daily_usd=x, slots=slots) for x in (3, 5, 8, 12, 20)],
        "per_day": [off] + [Rule(f"{n} per coin per day", per_day=n, slots=slots) for n in (1, 2, 3)],
        "risk": [off] + [Rule(f"equal risk ${r}", risk_usd=r, slots=slots) for r in (3.0, 3.5, 4.0)]
                + [Rule(f"flat ${l}", lot=l, slots=slots) for l in (90, 110, 120)],
    }
    return fam


def honest(markets, cands, rules, windows):
    total = {"chosen": 0.0, "off": 0.0}
    rows, won = [], 0
    for k in range(6):
        tr, te = windows[f"wf{k}_train"], windows[f"wf{k}_test"]
        train = pd.DataFrame([replay(markets, cands, r, *tr) for r in rules])
        pick = rules[int(train.profit.idxmax())]
        got = replay(markets, cands, pick, *te)["profit"]
        base = replay(markets, cands, rules[0], *te)["profit"]
        total["chosen"] += got
        total["off"] += base
        won += got > base + 1e-9
        rows.append(f"{te[0].date()} {pick.name:<22} {got:8.2f} vs off {base:8.2f}")
    return total, won, rows


def main():
    import pickle
    with open(ca.INPUTS, "rb") as handle:
        markets, cands, windows = pickle.load(handle)
    pd.set_option("display.width", 220)
    for slots in (3, 5):
        print(f"\n################ pot {slots} x $100")
        for fam, rules in families(slots).items():
            full = pd.DataFrame([replay(markets, cands, r, ca.START, ca.END) for r in rules])
            wf = []
            for r in rules:
                per = [replay(markets, cands, r, *windows[f"wf{k}_test"])["profit"] for k in range(6)]
                wf.append(per)
            off = wf[0]
            full["walk_fwd"] = [sum(p) for p in wf]
            full["wins_vs_off"] = [sum(a > b + 1e-9 for a, b in zip(p, off)) for p in wf]
            print(f"\n=== {fam}")
            print(full.round(2).to_string(index=False))
            total, won, rows = honest(markets, cands, rules, windows)
            print(f"honest gate: chosen {total['chosen']:.2f} vs off {total['off']:.2f} "
                  f"= {total['chosen'] - total['off']:+.2f}, {won}/6 windows")
            for line in rows:
                print("   ", line)


if __name__ == "__main__":
    main()
