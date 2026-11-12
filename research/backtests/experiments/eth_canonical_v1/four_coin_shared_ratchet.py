"""Local-only replay of one five-slot wallet shared by ETH, TRX, BTC and AAVE.

This models the requested *new* portfolio design, rather than claiming that the
current per-coin settings already enforce it: every eligible signal competes in
timestamp order for five global slots.  The configured order size starts at
$100 and ratchets permanently by $20 whenever marked account equity first
passes another $100 profit milestone.  A final entry may use the smaller cash
remainder.  There is no leverage, borrowing, priority rule, or per-coin quota.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import floor
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as eth_baseline
from .portfolio_risk import CoinMarket, PortfolioCandidate, _other_exit_kind
from .run import STAGE2_ROOT


OUTPUT = STAGE2_ROOT / "results" / "four_coin_shared_ratchet_v1"
COINS = ("ETH", "TRX", "BTC", "AAVE")
FEE = 7.5 / 10_000
SLIP = 2.0 / 10_000
INITIAL = 500.0
SLOTS = 5
MIN_ORDER = 5.0


def build_inputs() -> tuple[dict[str, CoinMarket], list[PortfolioCandidate], dict]:
    """Use the accepted canonical ETH book plus current deployed books for peers."""
    import all_coins_compare as compare  # available through baseline's script-path setup

    markets: dict[str, CoinMarket] = {}
    candidates: list[PortfolioCandidate] = []
    eth_market, eth_book, windows = eth_baseline.build_baseline()
    markets["ETH"] = CoinMarket(eth_market.times, eth_market.open, eth_market.close)
    for trade in eth_book:
        candidates.append(PortfolioCandidate(
            "ETH", trade.entry, trade.exit, trade.exit_price, trade.source,
            trade.exit_kind or "unknown", trade.candidate_id,
            eth_market.times[trade.entry], eth_market.times[trade.exit],
        ))

    for coin, builder in (("TRX", compare.trx), ("BTC", compare.btc),
                          ("AAVE", compare.aave), ("SOL", compare.sol)):
        book = builder()
        raw = compare.market()
        market = CoinMarket(pd.DatetimeIndex(raw[4]), raw[0].copy(), raw[3].copy())
        markets[coin] = market
        for number, trade in enumerate(book):
            entry, exit_at = int(trade["entry"]), int(trade["exit"])
            candidates.append(PortfolioCandidate(
                coin, entry, exit_at, float(trade["price"]), str(trade["source"]),
                _other_exit_kind(trade, market),
                f"{coin}:{trade['source']}:{market.times[entry].isoformat()}:{number}",
                market.times[entry], market.times[exit_at],
            ))
    return markets, candidates, windows


def _marked_value(lot: dict, at: pd.Timestamp, markets: dict[str, CoinMarket]) -> float:
    market = markets[lot["coin"]]
    index = int(market.times.searchsorted(at, side="right")) - 1
    index = max(0, min(index, len(market.close) - 1))
    return lot["quantity"] * float(market.close[index]) * (1 - SLIP) * (1 - FEE)


def replay(markets: dict[str, CoinMarket], candidates: list[PortfolioCandidate], start: pd.Timestamp,
           end: pd.Timestamp, coins: tuple[str, ...], ratchet: bool) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Replay one shared wallet.  Same-minute ties use ETH, TRX, BTC, AAVE order."""
    coin_order = {coin: i for i, coin in enumerate((*COINS, "SOL"))}
    wallet, high_water, steps = INITIAL, INITIAL, 0
    opened: list[dict] = []
    filled: list[dict] = []
    blocked: list[dict] = []
    milestones: list[dict] = []
    for candidate in sorted((c for c in candidates if c.coin in coins),
                            key=lambda c: (c.entry_time, coin_order[c.coin], c.candidate_id)):
        if not start <= candidate.entry_time < end:
            continue
        matured = [lot for lot in opened if lot["exit_time"] <= candidate.entry_time]
        wallet += sum(lot["proceeds"] for lot in matured)
        opened = [lot for lot in opened if lot["exit_time"] > candidate.entry_time]

        marked_equity = wallet + sum(_marked_value(lot, candidate.entry_time, markets) for lot in opened)
        high_water = max(high_water, marked_equity)
        new_steps = int(max(0.0, high_water - INITIAL) // 100) if ratchet else 0
        if new_steps > steps:
            for step in range(steps + 1, new_steps + 1):
                milestones.append({"entry_time": candidate.entry_time, "profit_milestone_usd": step * 100,
                                   "marked_equity_usd": marked_equity,
                                   "configured_lot_usd": 100 + step * 20})
            steps = new_steps
        target = 100 + steps * 20 if ratchet else 100.0
        if len(opened) >= SLOTS:
            blocked.append({"coin": candidate.coin, "entry_time": candidate.entry_time, "reason": "all_five_slots_open"})
            continue
        if wallet < MIN_ORDER:
            blocked.append({"coin": candidate.coin, "entry_time": candidate.entry_time, "reason": "insufficient_cash"})
            continue
        spend = min(target, floor(wallet * 100) / 100)
        if spend < MIN_ORDER:
            blocked.append({"coin": candidate.coin, "entry_time": candidate.entry_time, "reason": "below_minimum_order"})
            continue
        market = markets[candidate.coin]
        endpoint = candidate.exit_time >= end
        exit_index = int(market.times.searchsorted(end)) - 1 if endpoint else candidate.exit_index
        exit_raw = float(market.close[exit_index]) if endpoint else candidate.exit_price
        entry_raw = float(market.open[candidate.entry_index])
        entry_fill = entry_raw * (1 + SLIP)
        quantity = spend / (entry_fill * (1 + FEE))
        proceeds = quantity * exit_raw * (1 - SLIP) * (1 - FEE)
        lot = {"candidate_id": candidate.candidate_id, "coin": candidate.coin, "source": candidate.source,
               "entry_time": candidate.entry_time, "exit_time": market.times[exit_index], "spend": spend,
               "configured_lot_usd": target, "used_remainder_cash": spend + 1e-9 < target,
               "quantity": quantity, "proceeds": proceeds, "pnl": proceeds - spend,
               "return_pct": 100 * (proceeds / spend - 1), "endpoint_closed": endpoint,
               "exit_kind": candidate.exit_kind}
        wallet -= spend
        opened.append(lot)
        filled.append(lot)

    wallet += sum(lot["proceeds"] for lot in opened)
    ledger = pd.DataFrame(filled)
    blocks = pd.DataFrame(blocked, columns=["coin", "entry_time", "reason"])
    equity = mark_equity(markets, ledger, start, end)
    wins = ledger[ledger.pnl > 0] if len(ledger) else ledger
    losses = ledger[ledger.pnl <= 0] if len(ledger) else ledger
    summary = {"coins": "+".join(coins), "sizing": "manual_ratchet" if ratchet else "fixed_$100",
               "net_profit": float(ledger.pnl.sum()) if len(ledger) else 0.0,
               "ending_equity": wallet, "trades": len(ledger), "blocked": len(blocks),
               "win_rate_pct": 100 * len(wins) / len(ledger) if len(ledger) else 0.0,
               "average_win": float(wins.pnl.mean()) if len(wins) else 0.0,
               "average_loss": float(losses.pnl.mean()) if len(losses) else 0.0,
               "profit_factor": float(wins.pnl.sum() / -losses.pnl.sum()) if len(losses) else None,
               "maximum_drawdown_usd": float(equity.drawdown_usd.min()),
               "maximum_drawdown_pct": float(equity.drawdown_pct.min()),
               "minimum_order": float(ledger.spend.min()) if len(ledger) else 0.0,
               "maximum_order": float(ledger.spend.max()) if len(ledger) else 0.0,
               "remainder_orders": int(ledger.used_remainder_cash.sum()) if len(ledger) else 0}
    return summary, ledger, blocks, equity, pd.DataFrame(milestones)


def mark_equity(markets: dict[str, CoinMarket], ledger: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    marks = pd.date_range(start, end, freq="1h", inclusive="left")
    values = np.full(len(marks), INITIAL)
    for lot in ledger.to_dict("records"):
        active = (marks >= lot["entry_time"]) & (marks < lot["exit_time"])
        values[marks >= lot["exit_time"]] += lot["pnl"]
        if active.any():
            market = markets[lot["coin"]]
            indices = market.times.searchsorted(marks[active], side="right") - 1
            values[active] += lot["quantity"] * market.close[indices] * (1 - SLIP) * (1 - FEE) - lot["spend"]
    peaks = np.maximum.accumulate(values)
    return pd.DataFrame({"timestamp": marks, "equity": values, "peak_equity": peaks,
                         "drawdown_usd": values - peaks, "drawdown_pct": 100 * (values / peaks - 1)})


def run(output: Path = OUTPUT) -> Path:
    markets, candidates, windows = build_inputs()
    start, end = windows["full"]
    cases = [("eth_only_fixed", ("ETH",), False), ("eth_only_ratchet", ("ETH",), True),
             ("four_coin_fixed", COINS, False), ("four_coin_ratchet", COINS, True)]
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for name, coins, ratchet in cases:
        summary, ledger, blocks, equity, milestones = replay(markets, candidates, start, end, coins, ratchet)
        summary["case"] = name
        summaries.append(summary)
        ledger.to_csv(output / f"{name}_trades.csv", index=False)
        blocks.to_csv(output / f"{name}_blocked.csv", index=False)
        equity.to_csv(output / f"{name}_equity_hourly.csv", index=False)
        milestones.to_csv(output / f"{name}_milestones.csv", index=False)
    table = pd.DataFrame(summaries)
    table.to_csv(output / "summary.csv", index=False)
    selected = pd.read_csv(output / "four_coin_ratchet_trades.csv")
    per_coin = selected.groupby("coin", as_index=False).agg(trades=("coin", "size"), profit=("pnl", "sum"),
        win_rate_pct=("pnl", lambda x: 100 * (x > 0).mean()), average_loss=("pnl", lambda x: x[x <= 0].mean()),
        average_order=("spend", "mean"))
    per_coin.to_csv(output / "four_coin_ratchet_by_coin.csv", index=False)
    base = table.set_index("case")
    change = base.loc["four_coin_ratchet", "net_profit"] - base.loc["eth_only_ratchet", "net_profit"]
    report = f"""# Four-coin, five-slot shared-pot replay (local only)

## Exact model

- One **$500** wallet; at most **five open positions total** across ETH, TRX, BTC and AAVE.
- Signal order is first-come-first-served. Ties use ETH → TRX → BTC → AAVE.
- Manual sizing starts at $100. Each new $100 marked-equity high-water profit step permanently adds $20 to the requested lot. Actual spending is the smaller of the requested lot and free wallet cash.
- No leverage, borrowing, per-coin reservation, or priority rule. Fees/slippage are 7.5/2 bps per side.
- Common evaluation window: {start.date()} to {end.date()} (end exclusive). Positions still open at the end are marked closed at the final completed price.

## Result

| Case | Profit | Ending equity | Trades | Win rate | Avg loss | Max drawdown | Orders | Blocked signals |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
"""
    for row in table.itertuples():
        report += f"| {row.case} | ${row.net_profit:.2f} | ${row.ending_equity:.2f} | {row.trades} | {row.win_rate_pct:.1f}% | ${row.average_loss:.2f} | ${row.maximum_drawdown_usd:.2f} ({row.maximum_drawdown_pct:.2f}%) | ${row.minimum_order:.2f}–${row.maximum_order:.2f} | {row.blocked} |\n"
    coin_rows = "\n".join(
        f"| {row.coin} | {row.trades} | ${row.profit:.2f} | {row.win_rate_pct:.1f}% | "
        f"${row.average_loss:.2f} | ${row.average_order:.2f} |"
        for row in per_coin.itertuples()
    )
    report += f"""

Adding TRX, BTC and AAVE to the ratcheted ETH wallet changed profit by **${change:+.2f}** versus the same ETH-only ratchet control. This is an allocation simulation, not evidence that the current live app already has one global five-slot pool.

## Four-coin ratchet contribution

| Coin | Trades | Profit | Win rate | Average loss | Average order |
|---|---:|---:|---:|---:|---:|
{coin_rows}
"""
    (output / "REPORT.md").write_text(report)
    return output


if __name__ == "__main__":
    result = run()
    print(pd.read_csv(result / "summary.csv").to_string(index=False))
    print(result / "REPORT.md")
