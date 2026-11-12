"""SOL: what happens without the −2% stop, without the 06–12 UTC block, or without either.

Exact Stage 3 replay of the live SOL strategy (3m, 12-day average, ±0.5% zone, trail +1.251% giving back 12%,
$300 as 3 x $100 lots, no time exit). "No stop" is modelled as a stop 99% below the fill: it can never trigger, so
a losing trade is held until the trailing stop sells it - which only arms once the trade is +1.251% up.
"""

from __future__ import annotations

import copy

import pandas as pd

import compare_all_coins as cmp

VARIANTS = {
    "Live now (stop −2%, skip 06–12)": {},
    "No 06–12 block": {"skip_06_12": False},
    "No stop loss": {"stop_pct": 99.0},
    "Neither (no stop, all hours)": {"stop_pct": 99.0, "skip_06_12": False},
}


def main() -> None:
    rows = []
    for name, changes in VARIANTS.items():
        spec = {**copy.deepcopy(cmp.CANDIDATES["SOL"]), **changes}
        result, ledger = cmp.run(spec)
        for row in result:
            rows.append({"variant": name, **row})
        held = pd.to_datetime(ledger.exit_time) - pd.to_datetime(ledger.entry_time)
        print(f"{name}: {len(ledger)} trades, longest hold {held.max()}, median hold {held.median()}", flush=True)
    table = pd.DataFrame(rows)
    table.to_csv(cmp.RESULT_DIR.parent / "sol_no_stop_no_hours.csv", index=False)
    pd.set_option("display.width", 250)
    for cost in ("normal 10/2", "BNB 7.5/2", "stress 15/5"):
        print(f"\n== {cost}")
        view = table[table.cost == cost].pivot(index="variant", columns="window", values="net_profit_usd")
        extra = table[(table.cost == cost) & (table.window == "full")].set_index("variant")
        view = view[["full", "earlier", "later", "unseen"]].join(
            extra[["trades", "win_rate_pct", "max_drawdown_pct", "profit_factor", "average_hold_hours"]])
        print(view.loc[list(VARIANTS)].round(2).to_string())


if __name__ == "__main__":
    main()
