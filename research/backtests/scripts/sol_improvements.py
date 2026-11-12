"""SOL: one change at a time from the live strategy, on the exact Stage 3 replay.

Each row is the live SOL candidate (3m, 12-day average, ±0.5% zone, −2% stop, trail +1.251% giving back 12%,
skip 06–12 UTC, $300 as 3 x $100 lots) with a single setting changed, so the effect of that change is visible on
its own. Trailing starts move with the giveback: break-even + 1%, the rule used across all the research.
"""

from __future__ import annotations

import copy

import pandas as pd

import compare_all_coins as cmp
import run_sol_fixed100_giveback_grid as gb

trail = lambda giveback: {"activation_pct": round(gb.break_even_activation(giveback) + 1, 3),  # noqa: E731
                          "giveback_pct": giveback}
VARIANTS = {
    "Live now": {},
    "Trend: only above 30-day avg": {"trend": "above_30d"},
    "Trend: above 30-day, max +10%": {"trend": "above_30d_max10"},
    "Stop −1.5%": {"stop_pct": 1.5},
    "Stop −2.5%": {"stop_pct": 2.5},
    "Stop −3%": {"stop_pct": 3.0},
    "Give back 10%": trail(10.0),
    "Give back 16%": trail(16.0),
    "Give back 20%": trail(20.0),
    "Give back 30%": trail(30.0),
    "Zone ±0.3%": {"zone_pct": 0.3},
    "Zone ±0.4%": {"zone_pct": 0.4},
    "1-minute candles": {"signal_minutes": 1},
    "5-minute candles": {"signal_minutes": 5},
    "11-day average": {"average_days": 11},
    "13-day average": {"average_days": 13},
}


def main() -> None:
    rows = []
    for name, changes in VARIANTS.items():
        spec = {**copy.deepcopy(cmp.CANDIDATES["SOL"]), **changes}
        result, _ = cmp.run(spec)
        rows += [{"variant": name, **row} for row in result]
        print("done", name, flush=True)
    table = pd.DataFrame(rows)
    table.to_csv(cmp.RESULT_DIR.parent / "sol_improvements.csv", index=False)
    pd.set_option("display.width", 250)
    normal = table[table.cost == "normal 10/2"].pivot(index="variant", columns="window", values="net_profit_usd")
    stress = table[table.cost == "stress 15/5"].pivot(index="variant", columns="window", values="net_profit_usd")
    bnb = table[table.cost == "BNB 7.5/2"].pivot(index="variant", columns="window", values="net_profit_usd")
    extra = table[(table.cost == "normal 10/2") & (table.window == "full")].set_index("variant")
    view = pd.DataFrame({
        "full": normal["full"], "earlier": normal["earlier"], "later": normal["later"], "unseen": normal["unseen"],
        "bnb_full": bnb["full"], "stress_full": stress["full"], "stress_later": stress["later"],
        "trades": extra["trades"], "win_rate": extra["win_rate_pct"], "max_dd": extra["max_drawdown_pct"],
        "profit_factor": extra["profit_factor"],
    }).loc[list(VARIANTS)]
    print(view.round(2).to_string())


if __name__ == "__main__":
    main()
