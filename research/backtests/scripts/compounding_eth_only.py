"""ETH alone: start $300 as 3 x $100, slot 4 at $400, slot 5 at $500, then +$20 per lot for every further $100.

Controls on the same ETH signals and the same $300:
  FIXED 3x$100   never grows
  LIVE ETH       today's rule: up to 5 ETH lots of $100, buys while cash lasts (so it adds lots as profit builds)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compounding_full_analysis as ca  # noqa: E402
from compounding_full_analysis import Policy, T, replay  # noqa: E402

OUT = ca.OUT / "eth_only"


def growth_path(led, eq, initial=300.0):
    """When each slot / lot-size step was first reached on marked equity."""
    e = eq.set_index("timestamp").equity
    hw = e.cummax()
    events = []
    for k in range(1, 30):
        hit = hw[hw >= initial + 100 * k]
        if hit.empty:
            break
        slots = min(5, 3 + k)
        lot = 100 + 20 * max(0, k - 2)
        events.append({"reached": f"${initial + 100 * k:.0f}", "date": hit.index[0].date(),
                       "becomes": f"{slots} x ${lot}"})
    return pd.DataFrame(events)


def main():
    markets, cands = ca.load()
    eth = [c for c in cands if c.coin == "ETH"]
    pols = [Policy("PLAN 3->5 then +$20", "plan", 300.0, 5, 1.0),
            Policy("FIXED 3x$100", "fixed", 300.0, 3),
            Policy("LIVE ETH (5 lots, cash-limited)", "live", 300.0, caps={"ETH": 5})]
    pd.set_option("display.width", 250)
    OUT.mkdir(parents=True, exist_ok=True)

    full, months = [], []
    for p in pols:
        s, led, eq = replay(markets, eth, p, want_frames=True)
        full.append(s)
        m = eq.set_index("timestamp").equity.resample("MS").last()
        months.append(m.rename(p.name))
        if p.kind == "plan":
            path = growth_path(led, eq)
            led.to_csv(OUT / "plan_trades.csv", index=False)
    print("=== ETH only, $300 start, Oct 2024 - Sep 10 2026")
    print(pd.DataFrame(full)[["plan", "profit", "end_equity", "trades", "win_pct", "dd_usd", "dd_pct",
                              "profit_per_dd", "max_order", "avg_open_value", "worst_month_pct"]].round(2)
          .to_string(index=False))
    print("\n=== plan growth steps")
    print(path.to_string(index=False))
    mt = pd.concat(months, axis=1)
    mt.index = mt.index.strftime("%Y-%m")
    print("\n=== month-end equity")
    print(mt.round(0).to_string())

    # different start dates
    rows = []
    for months_n, last in ((12, "2025-09-01"), (6, "2026-03-01")):
        for start in pd.date_range(ca.START, T(last), freq="MS"):
            end = min(start + pd.DateOffset(months=months_n), ca.END)
            for p in pols:
                s = replay(markets, eth, p, start, end)
                rows.append({"horizon": f"{months_n}m", "start": start.date(), "plan": p.name,
                             "profit": s["profit"], "dd_pct": s["dd_pct"]})
    r = pd.DataFrame(rows)
    print("\n=== start with $300 on every month start")
    for h, sub in r.groupby("horizon"):
        piv = sub.pivot(index="start", columns="plan", values="profit")
        print(f"\n-- {h} runs ({len(piv)} starts)")
        print(piv.round(2).to_string())
        for other in ("FIXED 3x$100", "LIVE ETH (5 lots, cash-limited)"):
            d = piv["PLAN 3->5 then +$20"] - piv[other]
            print(f"plan vs {other}: beats {int((d > 0).sum())}/{len(d)}, median {d.median():+.2f}, "
                  f"worst {d.min():+.2f}")
        print("worst dd%:", sub.groupby("plan").dd_pct.min().round(2).to_dict())

    # costs
    rows = []
    for fee, slip in ((7.5, 2), (10, 5), (10, 10), (15, 10)):
        for p in pols:
            rows.append({"costs": f"{fee}+{slip}", "plan": p.name,
                         "profit": replay(markets, eth, p, fee=fee, slip=slip)["profit"]})
    print("\n=== cost stress (bps per side)")
    print(pd.DataFrame(rows).pivot(index="plan", columns="costs", values="profit").round(2).to_string())

    # same money-at-work control
    rows = [replay(markets, eth, Policy(f"LIVE ETH 5 x ${lot}", "live", 300.0, lot=lot, caps={"ETH": 5}))
            for lot in (100, 120, 140)]
    rows.append(full[0])
    print("\n=== live ETH with bigger lots vs plan")
    print(pd.DataFrame(rows)[["plan", "profit", "dd_usd", "dd_pct", "profit_per_dd", "avg_open_value"]]
          .round(2).to_string(index=False))
    r.to_csv(OUT / "rolling.csv", index=False)
    mt.to_csv(OUT / "month_end_equity.csv")
    path.to_csv(OUT / "growth_steps.csv", index=False)


if __name__ == "__main__":
    main()
