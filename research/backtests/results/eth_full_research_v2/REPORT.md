# ETH — Full Research v2 (stops to −4%, unseen Aug–Sep 2026)

Same grid as v1 plus −3.5% and −4% stops: **475,200 combinations**. Unseen data: Binance archives
ETHUSDT-1m-2026-08 and 2026-09-01 … 09-10 (checksums verified). Windows: full Oct 2024 – Jul 2026, earlier
→ Aug 2025, later Sep 2025 – Jul 2026, unseen Aug 1 – Sep 10 2026.

**14,645 profitable; 5,338 profitable in both periods.** Of the top 100 consistent combinations, 60 were
profitable on the unseen weeks (median +$2.36).

## Candidate

**5m candles, 7-day average, ±0.5% zone, −3.5% stop, trail from +1.315% with 30% giveback, no trend filter,
skip entries 06–12 UTC** (exact Stage 3 replay = fast grid to the cent)

| Costs | Window | Trades | Win rate | Profit on $300 | Max DD | PF |
|---|---|---:|---:|---:|---:|---:|
| 10/2 bps | Full | 246 | 82.9% | +$134.05 (+44.7%) | −8.98% | 1.86 |
| 10/2 bps | Earlier | 124 | 79.0% | +$83.42 | −8.98% | 1.86 |
| 10/2 bps | Later | 124 | 86.3% | +$47.83 | −6.07% | 1.76 |
| 10/2 bps | Unseen | 19 | 84.2% | +$2.37 | −4.56% | 1.61 |
| 7.5/2 bps (BNB) | Full | 250 | 82.8% | +$145.95 | −8.61% | 1.93 |
| 7.5/2 bps (BNB) | Unseen | 19 | 84.2% | +$3.39 | −4.42% | 1.70 |
| 15/5 bps stress | Full | 242 | 82.6% | +$66.10 | −10.19% | 1.41 |
| 15/5 bps stress | Unseen | 18 | 77.8% | −$4.57 | −4.13% | 0.90 |

Average winner +1.42%, loser −3.71%, 11.2 trades/month.

## Neighbourhood (full / unseen)

| Change | Result |
|---|---|
| Stop −3% / −4% | +$104.76 / +$0.64 · +$103.02 / +$16.42 |
| Zone ±0.4 / ±0.45 / ±0.55% | +$68.26 · +$95.31 · +$112.88 |
| Average 6 / 8 days | +$30.61 · +$78.98 |
| 1m / 3m candles | +$109.98 · +$104.58 |
| Trend filters | +$68.22 / +$29.31 (worse) |
| All hours | +$87.57 (worse) |
| Break-even stop +0.5 / +0.75% | +$35.81 / +$54.80 (worse) |
| Trail start +0.315% | −$17.31 |

Runner-up with nearly the same history: 1m, 7-day, ±0.4%, −3.5% stop → +$133.54 full, −$5.12 unseen.

## Selection checks

- Earlier-only pick (1m, 9-day, ±0.1%, −4%, above 30-day, all hours): earlier +$113.34 → later −$23.24.
- Walk-forward (best of previous 6 months, next 3 months, 6 windows): −$4.26, +$36.56, −$0.01, +$11.80,
  −$9.17, −$11.11 = **+$23.82**, versus about −$43 for the median combination.
