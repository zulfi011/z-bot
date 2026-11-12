"""TRX-only counterpart to the ETH manual upward-ratchet sizing replay."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .four_coin_shared_ratchet import build_inputs, replay
from .run import STAGE2_ROOT


OUTPUT = STAGE2_ROOT / "results" / "trx_manual_ratchet_compounding_v1"


def run(output: Path = OUTPUT) -> Path:
    markets, candidates, windows = build_inputs()
    rows: list[dict] = []
    details: dict[str, tuple] = {}
    for sizing, ratchet in (("fixed_$100_control", False), ("manual_upward_ratchet", True)):
        for name, bounds in windows.items():
            if name == "post_selection_2026_08_09":
                continue
            result = replay(markets, candidates, *bounds, ("TRX",), ratchet)
            summary = {**result[0], "sizing": sizing, "window": name}
            rows.append(summary)
            if name == "full":
                details[sizing] = result

    table = pd.DataFrame(rows)
    table.to_csv(output / "summary_by_window.csv", index=False) if output.exists() else None
    output.mkdir(parents=True, exist_ok=True)
    table.to_csv(output / "summary_by_window.csv", index=False)
    for sizing, (summary, ledger, blocked, equity, milestones) in details.items():
        slug = sizing.replace("$", "").replace("_", "-")
        ledger.to_csv(output / f"{slug}-trades.csv", index=False)
        blocked.to_csv(output / f"{slug}-blocked.csv", index=False)
        equity.to_csv(output / f"{slug}-equity-hourly.csv", index=False)
        milestones.to_csv(output / f"{slug}-milestones.csv", index=False)

    full = table[table.window.eq("full")].set_index("sizing")
    fixed, ratchet = full.loc["fixed_$100_control"], full.loc["manual_upward_ratchet"]
    wf = table[table.window.str.match(r"wf\d+_test")].pivot(index="window", columns="sizing", values="net_profit")
    changes = wf["manual_upward_ratchet"] - wf["fixed_$100_control"]
    report = f"""# TRX manual upward-ratchet compounding replay

## Exact model

- Start with a **$500 TRX-only wallet**, five configured **$100** lots, and no leverage.
- At every new marked-equity high-water profit milestone of $100, increase the requested lot permanently by $20: $100 → $120 → $140 and so on.
- The configured size never falls. A later order spends the smaller of the configured lot and actual free cash, so a loss can shrink the final remaining order.
- Same current TRX signals and exits; BNB fee 7.5 bps and slippage 2 bps per side.

## Full-period result

| Sizing | Profit | Ending equity | Trades | Win rate | Avg win | Avg loss | Max drawdown | Order range |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed $100 | ${fixed.net_profit:.2f} | ${fixed.ending_equity:.2f} | {fixed.trades} | {fixed.win_rate_pct:.1f}% | ${fixed.average_win:.2f} | ${fixed.average_loss:.2f} | ${fixed.maximum_drawdown_usd:.2f} ({fixed.maximum_drawdown_pct:.2f}%) | ${fixed.minimum_order:.2f}–${fixed.maximum_order:.2f} |
| Manual ratchet | ${ratchet.net_profit:.2f} | ${ratchet.ending_equity:.2f} | {ratchet.trades} | {ratchet.win_rate_pct:.1f}% | ${ratchet.average_win:.2f} | ${ratchet.average_loss:.2f} | ${ratchet.maximum_drawdown_usd:.2f} ({ratchet.maximum_drawdown_pct:.2f}%) | ${ratchet.minimum_order:.2f}–${ratchet.maximum_order:.2f} |

The ratchet changed profit by **${ratchet.net_profit - fixed.net_profit:+.2f}**, and improved **{int((changes > 0).sum())}/{len(changes)}** walk-forward test windows (combined change **${changes.sum():+.2f}**).
"""
    (output / "REPORT.md").write_text(report)
    return output


if __name__ == "__main__":
    result = run()
    print(pd.read_csv(result / "summary_by_window.csv").query("window == 'full'").to_string(index=False))
    print(result / "REPORT.md")
