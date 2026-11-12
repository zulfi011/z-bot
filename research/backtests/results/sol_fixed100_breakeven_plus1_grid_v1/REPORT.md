# SOL Fixed-$100 Strategy — Break-even Trail Start + 1% per Giveback

## Rules

$300 account, up to 3 lots of min($100, free cash). Touch from below of an N-day completed-close average
(N = 7…15), ±0.1…0.5% zone, bullish confirmation within 30 minutes, avoid strong bearish. Stops
−0.5/−1/−1.5/−2%; no time exit; 1m/3m/5m candles. Each giveback uses its break-even trail start plus 1%:

| Giveback | 10% | 12% | 14% | 16% | 18% | 20% | 22% | 24% | 26% | 28% | 30% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Trail start | +1.245% | +1.251% | +1.257% | +1.263% | +1.269% | +1.276% | +1.283% | +1.290% | +1.298% | +1.306% | +1.315% |

**5,940 combinations.** Windows: full 2024-10-01 → 2026-07-31, earlier, later, unseen 2026-08-01 →
2026-09-10 21:26 UTC.

## Result

**161 of 5,940 profitable**; **6** profitable in both periods — all the same setup at givebacks 10–20%.
Median −$67.51.

### Best candidate — profitable in every window

**3m candles, 12-day average, ±0.5% zone, −2% stop, trail from +1.251% with 12% giveback**
(exact Stage 3 replay = fast grid to the cent, 476 signals)

| Window | Trades | Win rate | Profit on $300 | Max DD | Fees + slippage |
|---|---:|---:|---:|---:|---:|
| Full | 280 | 69.6% | **+$17.84 (+5.9%)** | −9.2% | $66.82 |
| Earlier | 145 | 70.3% | +$11.19 | −9.2% | $34.42 |
| Later | 135 | 68.9% | +$6.63 | −7.3% | $32.40 |
| Unseen | 21 | 81.0% | +$8.03 | −2.7% | $5.04 |

195 trailing exits +$205.38 (+$1.05 each); 85 stops −$187.54 (−$2.21 each). Average hold 6.5 hours.

### Highest full-history profit — not consistent

1m candles, 13-day average, ±0.1% zone, −1.5% stop, trail from +1.306% with 28% giveback: **+$27.70**
full, but **−$20.79 earlier**, +$49.62 later, −15.2% drawdown.

## Warnings

- Chosen after seeing both periods; unseen window has 21 trades.
- For this setup ±0.3% and ±0.4% zones lose while ±0.2% and ±0.5% profit (see trail1245 grid).
- A 12-day average needs a Stage 3 engine change (supports 7/15/30 only).
