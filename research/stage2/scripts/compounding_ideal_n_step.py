"""Shared five-coin pot: find the ideal number of lots N, then the ideal lot increase after N.

Rules (user spec, 17 Oct 2026): start $300 as 3 x $100, one pot for ETH/TRX/BTC/AAVE/SOL, first come first served.
A buy takes the full lot if cash allows, otherwise whatever is left (the last lot carries the losses). Profit refills
lots up to their size. Every new $100 marked high-water adds one lot until N. After N, every new $100 adds $X to
each lot. X = 100/N spends exactly the new $100; smaller X keeps some aside, larger X over-commits (the remainder
rule then limits it to real cash).

Tests: full history, every monthly start (12-month and 6-month runs), choose-on-one-year/test-on-the-other,
cost stress, and neighbourhood (plateau) checks. LIVE (per-coin lots, no global cap) is the reference.
"""

from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compounding_full_analysis as ca  # noqa: E402
from compounding_full_analysis import Policy, T, replay  # noqa: E402

COINSET = tuple(sys.argv[1].split("+")) if len(sys.argv) > 1 else ca.COINS
OUT = ca.OUT / ("ideal_n_step" if COINSET == ca.COINS else "ideal_n_step_" + "_".join(COINSET).lower())
NS = range(3, 13)
STEPS = (0, 5, 10, 15, 20, 25, 30, 35, 40, 50)
HALVES = {"earlier": (T("2024-10-01"), T("2025-09-01")), "later": (T("2025-09-01"), ca.END)}
M, C = None, None


def init():
    global M, C
    M, C = ca.load()
    C = [c for c in C if c.coin in COINSET]


def plans():
    out = [Policy("LIVE", "live", 300.0)]
    for n in NS:
        incs = sorted(set(STEPS) | {round(100 / n, 2)})
        for inc in incs:
            out.append(Policy(f"N{n} +${inc:g}", "step", 300.0, n, float(inc)))
    return out


def job(args):
    policy, start, end, fee, slip, tag = args
    s = replay(M, C, policy, start, end, fee=fee, slip=slip)
    return {"tag": tag, "start": start.date(), "plan": policy.name, "n": policy.slots if policy.kind == "step" else 0,
            "inc": policy.share if policy.kind == "step" else 0.0, **{k: s[k] for k in
            ("profit", "dd_usd", "dd_pct", "profit_per_dd", "trades", "win_pct", "max_order", "avg_open_value",
             "worst_month_pct")}}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pols = plans()
    tasks = []
    for p in pols:
        tasks.append((p, ca.START, ca.END, 7.5, 2.0, "full"))
        tasks.append((p, ca.START, ca.END, 10.0, 10.0, "stress"))
        for name, (a, b) in HALVES.items():
            tasks.append((p, a, b, 7.5, 2.0, name))
        for s in pd.date_range(ca.START, T("2025-09-01"), freq="MS"):
            tasks.append((p, s, min(s + pd.DateOffset(months=12), ca.END), 7.5, 2.0, "r12"))
        for s in pd.date_range(ca.START, T("2026-03-01"), freq="MS"):
            tasks.append((p, s, s + pd.DateOffset(months=6), 7.5, 2.0, "r6"))
    print(f"{len(pols)} plans, {len(tasks)} replays", flush=True)
    with Pool(8, initializer=init) as pool:
        rows = pool.map(job, tasks, chunksize=8)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "all_runs.csv", index=False)
    print("saved", OUT / "all_runs.csv")


if __name__ == "__main__":
    main()
