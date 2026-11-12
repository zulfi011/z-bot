"""Every signal of all five deployed coins, with its own exit, cached for the compounding study.

Same books as experiments/eth_canonical_v1/four_coin_shared_ratchet.build_inputs (ETH-v5 canonical with the
break-even floor; TRX/BTC/AAVE as deployed), except SOL also gets the break-even floor on its Mode A lots, because
sol_strategy.json has one and the live engine applies it. Candidates are unconstrained: every signal is listed, so
any lot/slot rule can be applied afterwards.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from experiments.eth_canonical_v1 import four_coin_shared_ratchet as fc  # noqa: E402
from experiments.eth_canonical_v1.portfolio_risk import CoinMarket, PortfolioCandidate, _other_exit_kind  # noqa: E402

import all_coins_compare as compare  # noqa: E402
import eth_floor_and_arm as floor_arm  # noqa: E402
import live_ema_hold_all as live  # noqa: E402
import run_sol_stage3_space_grid as grid  # noqa: E402

OUT = ROOT / "data" / "compounding_full_v1"


def sol_with_floor():
    raw, bullish = compare.load("SOLUSDT")
    rule = live.load_rule("sol")
    line = pd.Series(grid.CLOSE).ewm(span=8 * 60, adjust=False).mean().to_numpy()
    floor_arm.LINE_FLOOR = line * (1 + floor_arm.COSTS / 100)
    breakout = [t["entry"] for t in compare.mode_c(raw, rule, 60, 24, 2.0, 0, 1.283, 22.0, 4.0)]
    sources = ((live.live_entries(raw, rule), "dip", rule["stop_pct"], rule["activation_pct"], rule["giveback_pct"]),
               (breakout, "breakout", 4.0, 1.283, 22.0))
    return floor_arm.book(sources, bullish, line, rule["activation_pct"], "buy price", "on arming")


def main():
    markets, candidates, windows = fc.build_inputs()
    candidates = [c for c in candidates if c.coin != "SOL"]
    book = sol_with_floor()
    raw = compare.market()
    market = CoinMarket(pd.DatetimeIndex(raw[4]), raw[0].copy(), raw[3].copy())
    markets["SOL"] = market
    for number, trade in enumerate(book):
        entry, exit_at = int(trade["entry"]), int(trade["exit"])
        candidates.append(PortfolioCandidate(
            "SOL", entry, exit_at, float(trade["price"]), str(trade["source"]), _other_exit_kind(trade, market),
            f"SOL:{trade['source']}:{market.times[entry].isoformat()}:{number}", market.times[entry],
            market.times[exit_at]))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "inputs.pkl", "wb") as handle:
        pickle.dump((markets, candidates, windows), handle)
    counts = pd.Series([c.coin for c in candidates]).value_counts()
    print(counts.to_string())
    print({coin: (m.times[0], m.times[-1]) for coin, m in markets.items()})


if __name__ == "__main__":
    main()
