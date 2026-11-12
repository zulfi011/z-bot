"""Experiment 11: replay ETH, BTC, SOL and AAVE through one marked-to-market wallet."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as eth_baseline
from .run import STAGE2_ROOT


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "crypto_portfolio_risk_v1.json"


@dataclass(frozen=True)
class CoinMarket:
    times: pd.DatetimeIndex
    open: np.ndarray
    close: np.ndarray


@dataclass(frozen=True)
class PortfolioCandidate:
    coin: str
    entry_index: int
    exit_index: int
    exit_price: float
    source: str
    exit_kind: str
    candidate_id: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    market_episode: str = ""


@dataclass(frozen=True)
class RiskLimits:
    global_open_value_usd: float
    maximum_episode_open_value_usd: float | None = None
    maximum_coins_per_episode: int | None = None
    extra_stop_slippage_bps: float = 0.0


def assign_common_episodes(candidates: list[PortfolioCandidate], maximum_gap_minutes: int) -> list[PortfolioCandidate]:
    """Group temporally connected signals across all coins into one crypto episode."""
    ordered = sorted(candidates, key=lambda item: (item.entry_time, item.coin, item.candidate_id))
    output: list[PortfolioCandidate] = []
    episode = 0
    previous: pd.Timestamp | None = None
    for candidate in ordered:
        if previous is None or (candidate.entry_time - previous).total_seconds() / 60 > maximum_gap_minutes:
            episode += 1
        output.append(replace(candidate, market_episode=f"crypto:{episode:04d}"))
        previous = candidate.entry_time
    return output


def _other_exit_kind(trade: dict, market: CoinMarket) -> str:
    if int(trade["why"]) == 1:
        return "strategy_exit"
    if int(trade["why"]) != 2:
        return "data_endpoint"
    entry_fill = float(market.open[int(trade["entry"])]) * 1.0002
    return "protective_stop" if float(trade["price"]) / entry_fill < 0.99 else "break_even"


def build_inputs() -> tuple[dict[str, CoinMarket], list[PortfolioCandidate], dict]:
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

    builders = {"BTC": eth_baseline.compare.btc, "SOL": eth_baseline.compare.sol,
                "AAVE": eth_baseline.compare.aave}
    for coin, builder in builders.items():
        book = builder()
        raw = eth_baseline.compare.market()
        market = CoinMarket(pd.DatetimeIndex(raw[4]), raw[0].copy(), raw[3].copy())
        markets[coin] = market
        for index, trade in enumerate(book):
            entry, exit_at = int(trade["entry"]), int(trade["exit"])
            candidates.append(PortfolioCandidate(
                coin, entry, exit_at, float(trade["price"]), str(trade["source"]),
                _other_exit_kind(trade, market),
                f"{coin}:{trade['source']}:{market.times[entry].isoformat()}:{index}",
                market.times[entry], market.times[exit_at],
            ))
    return markets, candidates, windows


def replay_shared_wallet(markets: dict[str, CoinMarket], candidates: list[PortfolioCandidate],
                         start: pd.Timestamp, end: pd.Timestamp, config: dict,
                         limits: RiskLimits) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    wallet = float(config["wallet"]["initial_capital_usd"])
    lot_size = float(config["wallet"]["lot_size_usd"])
    fee = float(config["costs"]["fee_bps_per_side"]) / 10_000
    slip = float(config["costs"]["slippage_bps_per_side"]) / 10_000
    per_coin = config["wallet"]["per_coin_maximum_lots"]
    opened: list[dict] = []
    filled: list[dict] = []
    blocked: list[dict] = []
    ordered = sorted(candidates, key=lambda item: (item.entry_time, item.coin, item.candidate_id))

    for candidate in ordered:
        if not start <= candidate.entry_time < end:
            continue
        matured = [lot for lot in opened if lot["exit_time"] <= candidate.entry_time]
        wallet += sum(lot["proceeds"] for lot in matured)
        opened = [lot for lot in opened if lot["exit_time"] > candidate.entry_time]
        same_coin = [lot for lot in opened if lot["coin"] == candidate.coin]
        same_episode = [lot for lot in opened if lot["market_episode"] == candidate.market_episode]
        reason = None
        if len(same_coin) >= int(per_coin[candidate.coin]):
            reason = "coin_slots"
        elif sum(lot["spend"] for lot in opened) + lot_size > limits.global_open_value_usd + 1e-9:
            reason = "global_open_value"
        elif (limits.maximum_episode_open_value_usd is not None
              and sum(lot["spend"] for lot in same_episode) + lot_size
              > limits.maximum_episode_open_value_usd + 1e-9):
            reason = "correlated_episode_value"
        elif (limits.maximum_coins_per_episode is not None
              and candidate.coin not in {lot["coin"] for lot in same_episode}
              and len({lot["coin"] for lot in same_episode}) >= limits.maximum_coins_per_episode):
            reason = "correlated_episode_coins"
        elif wallet < 5:
            reason = "insufficient_cash"
        if reason:
            blocked.append({"candidate_id": candidate.candidate_id, "coin": candidate.coin,
                            "entry_time": candidate.entry_time, "market_episode": candidate.market_episode,
                            "reason": reason, "open_value": sum(lot["spend"] for lot in opened)})
            continue

        market = markets[candidate.coin]
        endpoint = candidate.exit_time >= end
        if endpoint:
            exit_index = int(market.times.searchsorted(end)) - 1
            exit_raw = float(market.close[exit_index])
        else:
            exit_index = candidate.exit_index
            exit_raw = candidate.exit_price
        spend = min(lot_size, np.floor(wallet * 100) / 100)
        entry_raw = float(market.open[candidate.entry_index])
        entry_fill = entry_raw * (1 + slip)
        quantity = spend / (entry_fill * (1 + fee))
        extra = (limits.extra_stop_slippage_bps / 10_000
                 if candidate.exit_kind == "protective_stop" else 0.0)
        exit_fill = exit_raw * (1 - slip - extra)
        proceeds = quantity * exit_fill * (1 - fee)
        lot = {
            "candidate_id": candidate.candidate_id, "coin": candidate.coin,
            "source": candidate.source, "market_episode": candidate.market_episode,
            "exit_kind": candidate.exit_kind, "entry_index": candidate.entry_index,
            "entry_time": candidate.entry_time, "exit_index": exit_index,
            "exit_time": market.times[exit_index], "endpoint_closed": endpoint,
            "spend": spend, "quantity": quantity, "entry_fill_price": entry_fill,
            "exit_fill_price": exit_fill, "proceeds": proceeds, "pnl": proceeds - spend,
            "return_pct": 100 * (proceeds / spend - 1),
        }
        wallet -= spend
        opened.append(lot)
        filled.append(lot)

    wallet += sum(lot["proceeds"] for lot in opened)
    ledger = pd.DataFrame(filled)
    blocked_frame = pd.DataFrame(blocked)
    equity = _mark_equity(markets, ledger, start, end, float(config["wallet"]["initial_capital_usd"]), fee, slip)
    wins = ledger[ledger.pnl > 0] if len(ledger) else ledger
    losses = ledger[ledger.pnl <= 0] if len(ledger) else ledger
    gross_loss = float(-losses.pnl.sum()) if len(losses) else 0.0
    summary = {
        "initial_capital": float(config["wallet"]["initial_capital_usd"]),
        "ending_equity": wallet, "net_profit": float(ledger.pnl.sum()) if len(ledger) else 0.0,
        "trades": len(ledger), "blocked": len(blocked_frame),
        "win_rate_pct": 100 * len(wins) / len(ledger) if len(ledger) else 0.0,
        "average_win": float(wins.pnl.mean()) if len(wins) else 0.0,
        "average_loss": float(losses.pnl.mean()) if len(losses) else 0.0,
        "profit_factor": float(wins.pnl.sum()) / gross_loss if gross_loss else None,
        "maximum_drawdown_usd": float(equity.drawdown_usd.min()),
        "maximum_drawdown_pct": float(equity.drawdown_pct.min()),
        "maximum_open_value": _maximum_open_value(ledger),
        "maximum_simultaneous_coins": _maximum_simultaneous_coins(ledger),
    }
    return summary, ledger, blocked_frame, equity


def _mark_equity(markets: dict[str, CoinMarket], ledger: pd.DataFrame, start: pd.Timestamp,
                 end: pd.Timestamp, initial: float, fee: float, slip: float) -> pd.DataFrame:
    marks = pd.date_range(start=start, end=end, freq="1h", inclusive="left")
    values = np.full(len(marks), initial, dtype=float)
    if len(ledger):
        for lot in ledger.to_dict("records"):
            active = (marks >= lot["entry_time"]) & (marks < lot["exit_time"])
            closed = marks >= lot["exit_time"]
            values[closed] += lot["pnl"]
            if active.any():
                market = markets[lot["coin"]]
                indices = market.times.searchsorted(marks[active], side="right") - 1
                marked = lot["quantity"] * market.close[indices] * (1 - slip) * (1 - fee)
                values[active] += marked - lot["spend"]
    peaks = np.maximum.accumulate(values)
    return pd.DataFrame({"timestamp": marks, "equity": values, "peak_equity": peaks,
                         "drawdown_usd": values - peaks,
                         "drawdown_pct": 100 * (values / peaks - 1)})


def _maximum_open_value(ledger: pd.DataFrame) -> float:
    if ledger.empty:
        return 0.0
    events = [(row.entry_time, 1, row.spend) for row in ledger.itertuples()]
    events += [(row.exit_time, 0, -row.spend) for row in ledger.itertuples()]
    current = maximum = 0.0
    for _, _, change in sorted(events):
        current += change
        maximum = max(maximum, current)
    return maximum


def _maximum_simultaneous_coins(ledger: pd.DataFrame) -> int:
    if ledger.empty:
        return 0
    maximum = 0
    for timestamp in sorted(set(ledger.entry_time) | set(ledger.exit_time)):
        active = ledger[(ledger.entry_time <= timestamp) & (ledger.exit_time > timestamp)]
        maximum = max(maximum, active.coin.nunique())
    return int(maximum)


def _episode_table(ledger: pd.DataFrame) -> pd.DataFrame:
    if ledger.empty:
        return pd.DataFrame()
    return (ledger.groupby("market_episode", as_index=False)
            .agg(first_entry=("entry_time", "min"), last_exit=("exit_time", "max"),
                 trades=("candidate_id", "count"), coins=("coin", "nunique"),
                 pnl=("pnl", "sum"), protective_stops=("exit_kind", lambda x: (x == "protective_stop").sum()))
            .sort_values("pnl"))


def _per_coin(ledger: pd.DataFrame) -> pd.DataFrame:
    return (ledger.groupby("coin", as_index=False)
            .agg(trades=("candidate_id", "count"), profit=("pnl", "sum"),
                 win_rate_pct=("pnl", lambda x: 100 * (x > 0).mean()),
                 average_loss=("pnl", lambda x: x[x <= 0].mean())))


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    config = json.loads(config_path.read_text())
    markets, plain_candidates, windows = build_inputs()
    candidates = assign_common_episodes(
        plain_candidates, int(config["common_market_episode"]["maximum_signal_gap_minutes"])
    )
    full = windows["full"]
    control_limits = RiskLimits(float(config["wallet"]["global_open_value_usd"]))
    control = replay_shared_wallet(markets, candidates, *full, config, control_limits)
    variants = []
    variant_ledgers = []
    for item in config["frozen_variants"]:
        limits = RiskLimits(
            float(item.get("global_open_value_usd", control_limits.global_open_value_usd)),
            item.get("maximum_episode_open_value_usd"), item.get("maximum_coins_per_episode"),
        )
        result = replay_shared_wallet(markets, candidates, *full, config, limits)
        summary = result[0]
        limit_blocks = int((~result[2].reason.eq("coin_slots")).sum()) if len(result[2]) else 0
        variants.append({"variant": item["name"], **summary,
                         "profit_change": summary["net_profit"] - control[0]["net_profit"],
                         "drawdown_change_pct_points": summary["maximum_drawdown_pct"] - control[0]["maximum_drawdown_pct"],
                         "risk_rule_blocks": limit_blocks})
        variant_ledgers.append(result[1].assign(variant=item["name"]))
    stress_rows = []
    for extra in config["stress_extra_stop_slippage_bps"]:
        result = replay_shared_wallet(markets, candidates, *full, config,
                                      replace(control_limits, extra_stop_slippage_bps=float(extra)))
        stress_rows.append({"extra_stop_slippage_bps": extra, **result[0],
                            "profit_change": result[0]["net_profit"] - control[0]["net_profit"]})

    window_rows = []
    for name, bounds in windows.items():
        if name == "post_selection_2026_08_09":
            continue
        base_result = replay_shared_wallet(markets, candidates, *bounds, config, control_limits)[0]
        for item in config["frozen_variants"]:
            limits = RiskLimits(float(item.get("global_open_value_usd", control_limits.global_open_value_usd)),
                                item.get("maximum_episode_open_value_usd"), item.get("maximum_coins_per_episode"))
            result = replay_shared_wallet(markets, candidates, *bounds, config, limits)[0]
            window_rows.append({"variant": item["name"], "window": name,
                                "profit": result["net_profit"], "control_profit": base_result["net_profit"],
                                "profit_change": result["net_profit"] - base_result["net_profit"]})

    output = output_dir or STAGE2_ROOT / "results" / config["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    variants_frame = pd.DataFrame(variants).sort_values("profit_change", ascending=False)
    stress_frame = pd.DataFrame(stress_rows)
    control[1].to_csv(output / "control_trades.csv", index=False)
    control[2].to_csv(output / "control_blocked_signals.csv", index=False)
    control[3].to_csv(output / "portfolio_equity_hourly.csv", index=False)
    _episode_table(control[1]).to_csv(output / "common_market_episodes.csv", index=False)
    _per_coin(control[1]).to_csv(output / "per_coin_results.csv", index=False)
    variants_frame.to_csv(output / "variants.csv", index=False)
    stress_frame.to_csv(output / "stop_slippage_stress.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.concat(variant_ledgers, ignore_index=True).to_csv(output / "variant_trades.csv", index=False)
    (output / "summary.json").write_text(json.dumps({"control": control[0],
        "best_profit_variant": variants_frame.iloc[0].to_dict(),
        "best_drawdown_variant": variants_frame.sort_values("maximum_drawdown_pct", ascending=False).iloc[0].to_dict()},
        indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(control, variants_frame, stress_frame,
                                                pd.DataFrame(window_rows)))
    return output


def _report(control, variants: pd.DataFrame, stress: pd.DataFrame, windows: pd.DataFrame) -> str:
    base, ledger = control[0], control[1]
    coins = _per_coin(ledger)
    episodes = _episode_table(ledger)
    worst = episodes.iloc[0]
    rows = []
    for row in variants.itertuples():
        wf = windows[(windows.variant == row.variant) & windows.window.str.startswith("wf")]
        rows.append(f"| {row.variant} | ${row.net_profit:.2f} | ${row.profit_change:+.2f} | "
                    f"{row.trades} | {row.maximum_drawdown_pct:.2f}% | "
                    f"{row.drawdown_change_pct_points:+.2f} pp | {int((wf.profit_change > 0).sum())}/6 | {row.risk_rule_blocks} |")
    coin_rows = "\n".join(f"| {r.coin} | {r.trades} | ${r.profit:.2f} | {r.win_rate_pct:.1f}% | ${r.average_loss:.2f} |"
                          for r in coins.itertuples())
    stress_rows = "\n".join(f"| +{r.extra_stop_slippage_bps:.0f} bps | ${r.net_profit:.2f} | ${r.profit_change:+.2f} | {r.maximum_drawdown_pct:.2f}% |"
                             for r in stress.itertuples())
    best_dd = variants.sort_values("maximum_drawdown_pct", ascending=False).iloc[0]
    return f"""# Four-coin shared-wallet portfolio-risk experiment

## Original references

- Canonical ETH alone: **$430.16 profit · 459 trades · -9.66% maximum drawdown** on $500.
- Unchanged ETH + BTC + SOL + AAVE in one $1,400 wallet: **${base['net_profit']:.2f} profit · {base['trades']} trades · {base['win_rate_pct']:.1f}% headline wins · ${base['average_loss']:.2f} average loss · {base['maximum_drawdown_pct']:.2f}% drawdown**.

This is the first valid shared-wallet baseline. The ETH-only 9.66% drawdown must not be treated as the whole trading account's risk.

## Where the shared result came from

| Coin | Trades | Profit | Headline win rate | Average loss |
|---|---:|---:|---:|---:|
{coin_rows}

Maximum simultaneous exposure was **${base['maximum_open_value']:.0f}** across **{base['maximum_simultaneous_coins']} coins**. The worst common crypto episode was **{worst.market_episode}**, losing **${worst.pnl:.2f}** across **{int(worst.coins)} coin(s)** and {int(worst.trades)} trades.

## Frozen correlated-exposure tests

| Rule | Profit | Change vs shared control | Trades | Drawdown | DD change | WF windows improved | Risk-rule blocks |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Stops slipping together

| Extra slippage on every protective stop | Profit | Change | Drawdown |
|---|---:|---:|---:|
{stress_rows}

## Decision

**Do not deploy a correlated-exposure rule from this experiment.** The best percentage-drawdown rule was `{best_dd.variant}`, changing drawdown from **{base['maximum_drawdown_pct']:.2f}%** to **{best_dd.maximum_drawdown_pct:.2f}%**, but the worst dollar drawdown remained **${-base['maximum_drawdown_usd']:.2f}**. It changed profit by **${best_dd.profit_change:+.2f}** and improved only **{int(((windows.variant == best_dd.variant) & windows.window.str.startswith('wf') & (windows.profit_change > 0)).sum())}/6** walk-forward windows.

The useful change is measurement: future live risk reporting should use one shared marked-to-market equity curve and common crypto episode exposure. This local test does not alter ETH or any other live strategy, and it does not use the retired August-September period as acceptance evidence.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXPERIMENT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output)
    print((output / "REPORT.md").read_text())
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
