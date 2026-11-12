"""Local grid for a shared five-coin wallet that grows slots before lot size.

Start with $300 and three $100 lots.  At each new $100 marked-equity high-water
profit milestone, unlock one additional $100 slot until the tested maximum N.
Once N is reached, future $100 milestones may increase each requested lot by a
fixed share of $100/N.  All five current coin rule books compete first-come,
first-served for the same slots and free cash.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from pathlib import Path

import numpy as np
import pandas as pd

from .four_coin_shared_ratchet import COINS, FEE, MIN_ORDER, SLIP, _marked_value, build_inputs
from .run import STAGE2_ROOT


ALL_COINS = (*COINS, "SOL")
INITIAL, START_SLOTS, BASE_LOT = 300.0, 3, 100.0
OUTPUT = STAGE2_ROOT / "results" / "five_coin_scaling_plan_v1"


@dataclass(frozen=True)
class Plan:
    maximum_slots: int
    post_slot_share: float  # 0 = retain $100 lots; 1 = distribute all next $100 across N lots

    @property
    def label(self) -> str:
        return f"{self.maximum_slots}_slots_share_{int(self.post_slot_share * 100)}pct"


def replay(markets, candidates, start, end, plan: Plan):
    """One real-cash wallet; each active lot is marked at its own coin's price."""
    order = {coin: number for number, coin in enumerate(ALL_COINS)}
    cash, high_water, slots, size_steps = INITIAL, INITIAL, START_SLOTS, 0
    opened: list[dict] = []
    ledger: list[dict] = []
    blocked: list[dict] = []
    changes: list[dict] = []
    for candidate in sorted(candidates, key=lambda c: (c.entry_time, order[c.coin], c.candidate_id)):
        if not start <= candidate.entry_time < end:
            continue
        matured = [lot for lot in opened if lot["exit_time"] <= candidate.entry_time]
        cash += sum(lot["proceeds"] for lot in matured)
        opened = [lot for lot in opened if lot["exit_time"] > candidate.entry_time]
        marked_equity = cash + sum(_marked_value(lot, candidate.entry_time, markets) for lot in opened)
        high_water = max(high_water, marked_equity)

        # $400 unlocks slot 4, $500 unlocks slot 5, and so on.
        while slots < plan.maximum_slots and high_water + 1e-9 >= INITIAL + (slots - 2) * 100:
            slots += 1
            changes.append({"entry_time": candidate.entry_time, "type": "slot_unlocked",
                            "marked_equity_usd": marked_equity, "slots": slots,
                            "configured_lot_usd": BASE_LOT})
        first_size_milestone = INITIAL + (plan.maximum_slots - 2) * 100
        if plan.post_slot_share > 0 and high_water + 1e-9 >= first_size_milestone:
            steps = int((high_water - first_size_milestone + 1e-9) // 100) + 1
            if steps > size_steps:
                for step in range(size_steps + 1, steps + 1):
                    changes.append({"entry_time": candidate.entry_time, "type": "lot_increased",
                                    "marked_equity_usd": marked_equity, "slots": slots,
                                    "configured_lot_usd": BASE_LOT + step * (100 / plan.maximum_slots) * plan.post_slot_share})
                size_steps = steps
        requested = BASE_LOT + size_steps * (100 / plan.maximum_slots) * plan.post_slot_share
        if len(opened) >= slots:
            blocked.append({"coin": candidate.coin, "entry_time": candidate.entry_time, "reason": "all_slots_open"})
            continue
        if cash < MIN_ORDER:
            blocked.append({"coin": candidate.coin, "entry_time": candidate.entry_time, "reason": "insufficient_cash"})
            continue
        spend = min(requested, floor(cash * 100) / 100)
        if spend < MIN_ORDER:
            blocked.append({"coin": candidate.coin, "entry_time": candidate.entry_time, "reason": "below_minimum_order"})
            continue
        market = markets[candidate.coin]
        endpoint = candidate.exit_time >= end
        exit_index = int(market.times.searchsorted(end)) - 1 if endpoint else candidate.exit_index
        raw_exit = float(market.close[exit_index]) if endpoint else candidate.exit_price
        entry_fill = float(market.open[candidate.entry_index]) * (1 + SLIP)
        quantity = spend / (entry_fill * (1 + FEE))
        proceeds = quantity * raw_exit * (1 - SLIP) * (1 - FEE)
        lot = {"coin": candidate.coin, "candidate_id": candidate.candidate_id,
               "entry_time": candidate.entry_time, "exit_time": market.times[exit_index],
               "spend": spend, "requested_lot_usd": requested, "quantity": quantity,
               "proceeds": proceeds, "pnl": proceeds - spend, "return_pct": 100 * (proceeds / spend - 1),
               "used_remainder_cash": spend + 1e-9 < requested}
        cash -= spend
        opened.append(lot)
        ledger.append(lot)
    cash += sum(lot["proceeds"] for lot in opened)
    frame = pd.DataFrame(ledger)
    blocks = pd.DataFrame(blocked, columns=["coin", "entry_time", "reason"])
    equity = mark_equity(markets, frame, start, end)
    wins = frame[frame.pnl > 0] if len(frame) else frame
    losses = frame[frame.pnl <= 0] if len(frame) else frame
    return ({"net_profit": float(frame.pnl.sum()) if len(frame) else 0.0, "ending_equity": cash,
             "trades": len(frame), "blocked": len(blocks),
             "win_rate_pct": 100 * len(wins) / len(frame) if len(frame) else 0.0,
             "average_loss": float(losses.pnl.mean()) if len(losses) else 0.0,
             "profit_factor": float(wins.pnl.sum() / -losses.pnl.sum()) if len(losses) else None,
             "maximum_drawdown_usd": float(equity.drawdown_usd.min()),
             "maximum_drawdown_pct": float(equity.drawdown_pct.min()),
             "minimum_order": float(frame.spend.min()) if len(frame) else 0.0,
             "maximum_order": float(frame.spend.max()) if len(frame) else 0.0,
             "remainder_orders": int(frame.used_remainder_cash.sum()) if len(frame) else 0},
            frame, blocks, equity, pd.DataFrame(changes))


def mark_equity(markets, ledger: pd.DataFrame, start, end) -> pd.DataFrame:
    marks = pd.date_range(start, end, freq="1h", inclusive="left")
    value = np.full(len(marks), INITIAL)
    for lot in ledger.to_dict("records"):
        active = (marks >= lot["entry_time"]) & (marks < lot["exit_time"])
        value[marks >= lot["exit_time"]] += lot["pnl"]
        if active.any():
            market = markets[lot["coin"]]
            indices = market.times.searchsorted(marks[active], side="right") - 1
            value[active] += lot["quantity"] * market.close[indices] * (1 - SLIP) * (1 - FEE) - lot["spend"]
    peak = np.maximum.accumulate(value)
    return pd.DataFrame({"timestamp": marks, "equity": value, "peak_equity": peak,
                         "drawdown_usd": value - peak, "drawdown_pct": 100 * (value / peak - 1)})


def run(output: Path = OUTPUT) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    markets, candidates, windows = build_inputs()
    plans = [Plan(n, share) for n in range(3, 11) for share in (0.0, 0.5, 0.75, 1.0)]
    full_rows, wf_rows, artifacts = [], [], {}
    for plan in plans:
        result = replay(markets, candidates, *windows["full"], plan)
        row = {"plan": plan.label, "maximum_slots": plan.maximum_slots,
               "post_slot_share_pct": plan.post_slot_share * 100, **result[0]}
        full_rows.append(row)
        artifacts[plan.label] = result
        for name, bounds in windows.items():
            if not name.startswith("wf") or not name.endswith("_test"):
                continue
            score = replay(markets, candidates, *bounds, plan)[0]
            wf_rows.append({"plan": plan.label, "window": name, "net_profit": score["net_profit"],
                            "maximum_drawdown_pct": score["maximum_drawdown_pct"]})
    full = pd.DataFrame(full_rows)
    wf = pd.DataFrame(wf_rows)
    wf_score = wf.groupby("plan").agg(walk_forward_profit=("net_profit", "sum"),
        positive_windows=("net_profit", lambda x: int((x > 0).sum()))).reset_index()
    full = full.merge(wf_score, on="plan", validate="one_to_one")
    full["profit_to_drawdown"] = full.net_profit / full.maximum_drawdown_usd.abs()
    full = full.sort_values(["positive_windows", "walk_forward_profit", "profit_to_drawdown"], ascending=False)
    full.to_csv(output / "all_plans.csv", index=False)
    wf.to_csv(output / "walk_forward.csv", index=False)

    # Save transparent ledgers for the strongest full-history and strongest walk-forward plan.
    selected = {"best_walk_forward": full.iloc[0],
                "best_full_profit": full.sort_values("net_profit", ascending=False).iloc[0]}
    for label, row in selected.items():
        result = artifacts[row.plan]
        result[1].to_csv(output / f"{label}_trades.csv", index=False)
        result[2].to_csv(output / f"{label}_blocked.csv", index=False)
        result[3].to_csv(output / f"{label}_equity_hourly.csv", index=False)
        result[4].to_csv(output / f"{label}_growth_events.csv", index=False)
    baseline = full[full.plan.eq("3_slots_share_0pct")].iloc[0]
    chosen = full.iloc[0]
    report = f"""# Five-coin shared-pot scaling plan (local only)

## Model

One $300 wallet is shared by ETH, TRX, BTC, AAVE and SOL. It begins with three $100 slots. At each $100 marked-equity high-water milestone it unlocks a further $100 slot until cap N. After N, the post-slot share says what fraction of each further $100 profit is distributed evenly across N requested lots: 100% means 5 slots go from $100 to $120 after the next $100 profit; at 6 slots it becomes $116.67. Actual spend always uses remaining free cash when it is smaller.

The grid tested N=3…10 and post-slot distribution shares of 0%, 50%, 75%, and 100%. Plans are ranked by positive walk-forward periods, then combined walk-forward profit, then profit/drawdown.

## Selected robust plan

**{chosen.plan}**: ${chosen.net_profit:.2f} profit, {chosen.trades} trades, {chosen.win_rate_pct:.1f}% win rate, {chosen.maximum_drawdown_pct:.2f}% maximum drawdown, and ${chosen.walk_forward_profit:.2f} combined walk-forward profit across {chosen.positive_windows}/6 positive windows.

Baseline (stay at 3×$100): ${baseline.net_profit:.2f} profit, {baseline.maximum_drawdown_pct:.2f}% drawdown, ${baseline.walk_forward_profit:.2f} walk-forward profit.

The full matrix is in `all_plans.csv`; this is research only and does not modify the live bot.
"""
    (output / "REPORT.md").write_text(report)
    return output


if __name__ == "__main__":
    path = run()
    print(pd.read_csv(path / "all_plans.csv").head(12).to_string(index=False))
    print(path / "REPORT.md")
