# ETH — Full Research (same procedure as SOL)

## Grid (356,400 combinations)

1/3/5m candles × 1–15 day completed-close average × ±0.1…0.5% zone (from below + green confirmation, avoid
strong bearish) × stop −0.5/−1/−1.5/−2/−2.5/−3% × giveback 10…30% with trail start at break-even
(+0.245…+0.315%) or break-even + 1% (+1.245…+1.315%) × break-even stop none/+0.5%/+0.75% (+1% starts only)
× trend filter none / above 30-day / above 30-day ≤ +10% × all hours / skip 06–12 UTC. $300, full $100 lots,
at most 3 open, no time exit, 10 bps fee + 2 bps slippage. History Oct 2024 – Jul 2026 (no unseen ETH data).

**6,948 profitable; 2,198 profitable in both periods.** 2,128 of those 2,198 use a 6–8 day average.

## Candidate

**1m candles, 7-day average, ±0.4% zone, −3% stop, trail from +1.315% with 30% giveback, no trend filter,
skip entries 06–12 UTC** (exact Stage 3 replay = fast grid to the cent)

| Costs | Window | Trades | Win rate | Profit on $300 | Max DD | PF |
|---|---|---:|---:|---:|---:|---:|
| 10/2 bps | Full | 317 | 80.8% | +$132.46 (+44.2%) | −9.80% | 1.68 |
| 10/2 bps | Earlier | 170 | 77.1% | +$72.06 | −9.80% | 1.58 |
| 10/2 bps | Later | 148 | 85.1% | +$61.16 | −6.26% | 1.87 |
| 7.5/2 bps (BNB) | Full | 317 | 80.8% | +$148.38 | −9.35% | 1.77 |
| 15/5 bps stress | Full | 305 | 80.0% | +$48.38 | −11.79% | 1.24 |
| 15/5 bps stress | Earlier | 160 | 75.6% | +$9.92 | −11.79% | 1.08 |

Average winner +1.28%, loser −3.21%, 14.4 trades/month, average hold 14 hours.

## Ideas, one change at a time (full / earlier / later)

| Change | Result | Verdict |
|---|---|---|
| Trend filter above 30-day | +$78 / +$50 / +$29 | Worse — dropped |
| Trend filter above 30-day ≤ +10% | +$58 / +$30 / +$29 | Worse — dropped |
| All hours (no 06–12 skip) | +$90 / +$68 / +$17 | Skip helps both periods — kept |
| Break-even stop after +0.5% / +0.75% | −$3 / +$72 | Worse — dropped |
| Stop −2% / −2.5% | +$61 / +$109 | −3% best; −3% is the edge of the grid |
| Trail start +0.315% (no +1%) | −$39 | +1% start essential |
| Zone ±0.3 / ±0.35 / ±0.45 / ±0.5% | +$89 / +$86 / +$112 / +$108 | Holds up |
| Average 6 / 8 days | −$8 / +$59 | 7 is the peak; 5 and 9 fail |
| 3m / 5m candles | +$71 / +$66 | Holds up |

## Earlier-only selection and walk-forward

- Best on the earlier period: 5m, 9-day, ±0.2%, −0.5% stop … → earlier +$85.58, later −$39.92.
  Of the top 100 earlier-period combinations, 14 were profitable later (median −$30.96).
- Walk-forward (choose the best of the previous 6 months, trade the next 3; six windows Apr 2025 – Jul 2026):
  −$8.42, +$17.18, +$3.72, +$11.80, −$9.17, −$3.93 = **+$11.17** in total. The median of all combinations in
  the same windows totals about −$46, so the selection process adds value but only modestly.
