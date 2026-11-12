# SOL Fixed-$100 Strategy — Trail from +1.245%

## Rules

$300 account, up to 3 lots of min($100, free cash). Touch from below of an N-day completed-close average
(N = 7…15), ±0.1/0.2/0.3/0.4/0.5% zone, bullish confirmation within 30 minutes, avoid strong bearish,
buy at the confirmation boundary. Trail starts at **+1.245%** from entry fill, giveback 10, 12, … 30%;
stops −0.5/−1/−1.5/−2%; no time exit. 1m/3m/5m candles. 10 bps fee + 2 bps slippage per side.
3 × 9 × 5 × 4 × 11 = **5,940 combinations**. Windows: full 2024-10-01 → 2026-07-31, earlier → 2025-08-31,
later 2025-09-01 → 2026-07-31, unseen 2026-08-01 → 2026-09-10 20:57 UTC.

## Result

**161 of 5,940 profitable** over the full history; **8** profitable in both periods (all the same setup).
Median −$68.13.

### Best candidate — profitable in every window

**3m candles, 12-day average, ±0.5% zone, −2% stop, trail from +1.245% with 12% giveback**
(exact Stage 3 replay = fast grid to the cent, 476 signals)

| Window | Trades | Win rate | Profit on $300 | Max DD | Fees + slippage |
|---|---:|---:|---:|---:|---:|
| Full | 280 | 69.6% | **+$17.00 (+5.7%)** | −9.2% | $66.82 |
| Earlier | 145 | 70.3% | +$10.66 | −9.2% | $34.40 |
| Later | 135 | 68.9% | +$6.31 | −7.3% | $32.40 |
| Unseen | 21 | 81.0% | +$7.65 | −2.7% | $5.04 |

Average winner +1.06%, average loser −2.22%, average hold 6.5 hours, 195 trailing / 85 stop exits.

The same setup is profitable in both periods for givebacks 10–24% (+$5.85 to +$17.00 full).

### Highest full-history profit — not consistent

1m candles, 13-day average, ±0.1% zone, −1.5% stop, 18% giveback: **+$21.20** full, but **−$24.85 earlier**
and +$47.41 later (−16.5% drawdown). All top-ranked rows share this pattern.

## Warnings

- Zone sensitivity is erratic for the candidate setup: ±0.2% and ±0.5% profit, ±0.3% and ±0.4% lose.
- Chosen after seeing both periods; the unseen window has 21 trades.
- A 12-day average needs a Stage 3 engine change (Stage 3 supports 7/15/30 only).
- Stops: −2% best (median −$50.8), −0.5% worst (−$100.8). Averages: 12-day best (median −$39.5).
