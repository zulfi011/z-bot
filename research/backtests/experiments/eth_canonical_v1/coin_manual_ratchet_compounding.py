"""Run the ETH/TRX manual-ratchet sizing test for one current coin strategy."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import baseline as _baseline  # sets up the shared research-script import path
from .four_coin_shared_ratchet import CoinMarket, PortfolioCandidate, _other_exit_kind, replay
from .run import STAGE2_ROOT


def build_coin_inputs(coin: str) -> tuple[dict[str, CoinMarket], list[PortfolioCandidate], dict]:
    """Avoid rebuilding every other coin when this is a one-coin sizing test."""
    import all_coins_compare as compare
    import run_eth_full_research as research

    builder = {"BTC": compare.btc, "SOL": compare.sol, "AAVE": compare.aave}[coin]
    book = builder()
    raw = compare.market()
    market = CoinMarket(pd.DatetimeIndex(raw[4]), raw[0].copy(), raw[3].copy())
    candidates = [
        PortfolioCandidate(
            coin, int(trade["entry"]), int(trade["exit"]), float(trade["price"]), str(trade["source"]),
            _other_exit_kind(trade, market),
            f"{coin}:{trade['source']}:{market.times[int(trade['entry'])].isoformat()}:{number}",
            market.times[int(trade["entry"])], market.times[int(trade["exit"])],
        )
        for number, trade in enumerate(book)
    ]
    return {coin: market}, candidates, dict(research.WINDOWS)


def run(coin: str) -> Path:
    coin = coin.upper()
    if coin not in {"BTC", "SOL", "AAVE"}:
        raise ValueError("This runner is reserved for BTC, SOL, and AAVE.")
    output = STAGE2_ROOT / "results" / f"{coin.lower()}_manual_ratchet_compounding_v1"
    output.mkdir(parents=True, exist_ok=True)
    markets, candidates, windows = build_coin_inputs(coin)
    rows, details = [], {}
    for variant, ratchet in (("fixed_$100_control", False), ("manual_upward_ratchet", True)):
        for name, bounds in windows.items():
            if name in {"post_selection_2026_08_09", "unseen"}:
                continue
            result = replay(markets, candidates, *bounds, (coin,), ratchet)
            rows.append({**result[0], "sizing": variant, "window": name})
            if name == "full":
                details[variant] = result
    summary = pd.DataFrame(rows)
    summary.to_csv(output / "summary_by_window.csv", index=False)
    for variant, (_, ledger, blocked, equity, milestones) in details.items():
        stem = variant.replace("$", "").replace("_", "-")
        ledger.to_csv(output / f"{stem}-trades.csv", index=False)
        blocked.to_csv(output / f"{stem}-blocked.csv", index=False)
        equity.to_csv(output / f"{stem}-equity-hourly.csv", index=False)
        milestones.to_csv(output / f"{stem}-milestones.csv", index=False)
    full = summary[summary.window.eq("full")].set_index("sizing")
    fixed, ratchet = full.loc["fixed_$100_control"], full.loc["manual_upward_ratchet"]
    wf = summary[summary.window.str.match(r"wf\d+_test")].pivot(
        index="window", columns="sizing", values="net_profit")
    change = wf["manual_upward_ratchet"] - wf["fixed_$100_control"]
    report = f"""# {coin} manual upward-ratchet compounding replay

Local-only sizing experiment. It starts with one **$500 {coin}-only wallet** and five $100 slots. Every new $100 marked-equity high-water profit milestone permanently raises later requested orders by $20. Each actual order uses the lesser of that request and free cash; no leverage or borrowing is used. Current {coin} entries/exits and 7.5/2 bps BNB-fee/slippage assumptions are unchanged.

| Sizing | Profit | Ending equity | Trades | Win rate | Avg win | Avg loss | Max drawdown | Order range |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed $100 | ${fixed.net_profit:.2f} | ${fixed.ending_equity:.2f} | {fixed.trades} | {fixed.win_rate_pct:.1f}% | ${fixed.average_win:.2f} | ${fixed.average_loss:.2f} | ${fixed.maximum_drawdown_usd:.2f} ({fixed.maximum_drawdown_pct:.2f}%) | ${fixed.minimum_order:.2f}–${fixed.maximum_order:.2f} |
| Manual ratchet | ${ratchet.net_profit:.2f} | ${ratchet.ending_equity:.2f} | {ratchet.trades} | {ratchet.win_rate_pct:.1f}% | ${ratchet.average_win:.2f} | ${ratchet.average_loss:.2f} | ${ratchet.maximum_drawdown_usd:.2f} ({ratchet.maximum_drawdown_pct:.2f}%) | ${ratchet.minimum_order:.2f}–${ratchet.maximum_order:.2f} |

Ratchet profit change: **${ratchet.net_profit - fixed.net_profit:+.2f}**. Walk-forward: better in **{int((change > 0).sum())}/{len(change)}** test windows; combined change **${change.sum():+.2f}**.
"""
    (output / "REPORT.md").write_text(report)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("coin", choices=["BTC", "SOL", "AAVE"])
    args = parser.parse_args()
    path = run(args.coin)
    print(pd.read_csv(path / "summary_by_window.csv").query("window == 'full'").to_string(index=False))
    print(path / "REPORT.md")
