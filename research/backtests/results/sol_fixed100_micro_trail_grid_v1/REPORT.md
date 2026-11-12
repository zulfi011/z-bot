# SOL Fixed-$100 Lots with +0.245% / 10% Micro Trail

## Rules

- $300 account; up to 3 open lots; each lot = min($100, free cash); leftover above $100 stays idle.
- Entry: touch from below of an N-day completed-close average (N = 7…15), ±0.1/0.2/0.3/0.4/0.5% zone,
  bullish confirmation within 30 minutes, live "avoid strong bearish" filter, buy at the confirmation boundary.
- Exit: trail activates at +0.245% from entry fill and gives back 10% of peak open profit
  (worst case after activation ≈ break-even after costs); stop −0.5/−1/−1.5/−2%; no time exit.
- Candles 1m/3m/5m. 10 bps fee + 2 bps slippage per side.
- 3 × 9 × 5 × 4 = **540 combinations**. Windows: full 2024-10-01 → 2026-07-31, earlier, later, unseen
  2026-08-01 → 2026-09-10 20:29 UTC.
- 8–14 day averages need a Stage 3 engine change (Stage 3 supports 7/15/30 only).

## Result

**0 of 540 were profitable** over the full history, and none were profitable in either period.
Median result −$110.92 on $300; worst −$209.71.

Best candidate (exact Stage 3 replay, matches the fast grid to the cent, 390 = 390 signals):
**5m candles, 13-day average, ±0.1% zone, −1% stop**

| Window | Trades | Win rate | Profit on $300 | Max DD | Fees + slippage |
|---|---:|---:|---:|---:|---:|
| Full | 334 | 60.8% | −$54.54 (−18.2%) | −18.3% | $78.00 |
| Earlier | 162 | 67.3% | −$29.33 | −10.7% | $38.26 |
| Later | 172 | 54.7% | −$26.56 | −9.1% | $40.78 |
| Unseen | 33 | 78.8% | −$3.70 | −2.0% | $7.90 |

Average winner +0.09%, average loser −0.56%, average hold 53 minutes, ~15 trades/month.

## Why it cannot work

The +0.245% / 10% trail is designed to exit near break-even. Once it activates, the trail sits just
below the peak and ordinary one-minute noise closes the trade, so winners average only +0.09% after
costs. Stops cost −0.5 to −2%. Before costs 302 of 540 combinations were positive (best +$47), but
$78 of fees and slippage on 334 trades turns the best into −$54.54. Fixed $100 lots do not reduce costs —
fees and slippage are a percentage of each trade.
