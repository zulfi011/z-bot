# Improving the Fixed-$100 SOL Candidate

Base: 3m candles, 12-day average, ±0.5% zone, from below + bullish confirmation, avoid strong bearish,
−2% stop, trail from +1.251% with 12% giveback, no time exit, $300 with up to 3 lots of min($100, cash).
Windows: full 2024-10-01 → 2026-07-31; earlier → 2025-08-31; later 2025-09-01 → 2026-07-31; unseen
2026-08-01 → 2026-09-10 21:50 UTC. All finalists re-run on the exact Stage 3 replay (fast = exact to the cent).

## One idea at a time (profit on $300, 10 bps fee + 2 bps slippage)

| Idea | Full | Earlier | Later | Unseen | Verdict |
|---|---:|---:|---:|---:|---|
| Base | +$17.84 | +$11.19 | +$6.63 | +$8.03 | — |
| Trend: price above 30-day average | **+$33.49** | +$15.01 | +$18.48 | +$6.92 | **Keep** |
| Trend: above 30-day, at most +10% | +$39.61 | +$21.13 | +$18.48 | $0 (0 trades) | Drop — cap is data-fitted, removes all unseen trades |
| Trend: 7 > 15 > 30 bullish regime | +$10.15 | −$5.06 | +$15.27 | +$6.92 | Drop |
| Trend: 12-day average rising | +$26.56 | +$7.84 | +$18.72 | +$8.03 | Drop (hurts earlier) |
| Break-even stop after +0.5% | −$68.46 | −$22.96 | −$47.05 | +$5.52 | **Drop** |
| Break-even stop after +0.75% | −$34.01 | −$15.38 | −$18.73 | +$12.12 | **Drop** |
| Break-even stop after +1.0% | +$15.13 | +$9.48 | +$5.62 | +$7.01 | Drop |
| Stop −1.5% | −$25.77 | −$19.18 | −$6.08 | +$8.12 | Drop |
| Stop −2.5% | −$3.29 | +$1.58 | −$4.87 | +$11.67 | Drop |
| Stop −3% | −$12.26 | +$11.98 | −$23.96 | +$10.67 | Drop |
| Skip entries 06:00–12:00 UTC | **+$51.94** | +$22.61 | +$29.34 | +$8.02 | **Keep** (found from full-history diagnostics — not independent) |
| Zone ±0.45% / ±0.55% | +$10.56 / +$25.34 | −$4.90 / +$10.22 | +$15.58 / +$15.12 | +$7.03 / +$5.14 | Neutral |
| Average 11 / 13 days | −$34.34 / −$52.65 | −$52.78 / −$44.07 | +$20.44 / −$9.59 | −$7.86 / +$7.49 | **Warning: 12 days is a knife-edge** |

Break-even stops fail because 60 of the winners first dip below −1% — the break-even stop closes trades
that would have recovered. The −2% stop is already the best width.

## Improved candidate

**Base + only buy when the confirmation close is above the 30-day average + skip entries 06:00–12:00 UTC**

| Costs | Window | Trades | Win rate | Profit on $300 | Max DD | Profit factor |
|---|---|---:|---:|---:|---:|---:|
| 10/2 bps | Full | 172 | 75.0% | **+$44.77 (+14.9%)** | −8.51% | 1.47 |
| 10/2 bps | Earlier | 104 | 72.1% | +$17.17 | −8.51% | 1.27 |
| 10/2 bps | Later | 68 | 79.4% | +$27.60 | −4.12% | 1.89 |
| 10/2 bps | Unseen | 20 | 80.0% | +$6.92 | −2.71% | 1.78 |
| 7.5/2 bps (BNB) | Full | 172 | 75.0% | +$53.40 | −8.12% | 1.58 |
| 15/5 bps stress | Full | 171 | 73.1% | +$10.57 | −10.55% | 1.10 |
| 15/5 bps stress | Earlier | 103 | 69.9% | −$4.46 | −10.55% | 0.94 |

Average winner +1.09%, loser −2.22%, 7.8 trades/month, fees + slippage $41.18 (base: $66.82).

## Neighbourhood (improved rules, full / later profit)

| Zone \ Average | 11d | 12d | 13d |
|---|---:|---:|---:|
| ±0.45% | −$24.42 / +$21.90 | +$33.31 / +$26.37 | −$19.51 / +$5.99 |
| ±0.50% | −$10.48 / +$24.62 | +$44.77 / +$27.60 | −$2.32 / +$8.63 |
| ±0.55% | +$4.18 / +$30.04 | +$61.45 / +$34.72 | −$16.04 / +$2.09 |

With the two filters, all nine neighbours are profitable in the later period, but 11- and 13-day averages
lose over the full history (their earlier periods lose). The 12-day average remains the weakest link.

## Earlier-only selection check

Best of all 1,440 on the earlier period (12d, ±0.55%, −3% stop, skip 06–12, no trend filter): earlier
+$33.51 → later +$8.49, unseen +$6.69, full +$42.03, stress −$5.05. Positive later but weaker than the
two-filter version, again showing earlier-period winners fade.
