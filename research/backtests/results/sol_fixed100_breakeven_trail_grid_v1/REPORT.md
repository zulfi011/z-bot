# SOL Fixed-$100 Strategy — Break-even Trail Start per Giveback

## Rules

$300 account, up to 3 lots of min($100, free cash). Touch from below of an N-day completed-close average
(N = 7…15), ±0.1…0.5% zone, bullish confirmation within 30 minutes, avoid strong bearish. Stops
−0.5/−1/−1.5/−2%; no time exit; 1m/3m/5m candles. Each giveback uses its break-even trail start:

| Giveback | 10% | 12% | 14% | 16% | 18% | 20% | 22% | 24% | 26% | 28% | 30% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Trail start | +0.245% | +0.251% | +0.257% | +0.263% | +0.269% | +0.276% | +0.283% | +0.290% | +0.298% | +0.306% | +0.315% |

**5,940 combinations.** Windows: full 2024-10-01 → 2026-07-31, earlier, later, unseen 2026-08-01 →
2026-09-10 21:14 UTC.

## Result

**0 of 5,940 profitable**; none profitable in either period. 3,445 were positive before costs.
Median −$108.07 on $300.

Best candidate (exact Stage 3 replay = fast grid to the cent):
**5m candles, 13-day average, ±0.1% zone, −2% stop, trail from +0.298% with 26% giveback**

| Window | Trades | Win rate | Profit on $300 | Max DD | Fees + slippage |
|---|---:|---:|---:|---:|---:|
| Full | 318 | 80.8% | −$44.51 (−14.8%) | −16.4% | $73.24 |
| Earlier | 156 | 80.1% | −$30.83 | −12.3% | $36.53 |
| Later | 162 | 81.5% | −$13.71 | −6.9% | $38.48 |
| Unseen | 30 | 83.3% | −$0.30 | −1.0% | $7.20 |

283 trailing exits earned +$32.12 (+$0.11 each); 35 stops lost −$76.64 (−$2.19 each).
Median by giveback improves steadily from −$110.9 (10%) to −$105.3 (30%) — never close to profit.
