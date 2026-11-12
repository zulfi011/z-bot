# NEAR — Full Research v1 (same procedure as ETH v2, BTC v1, LINK v1, AVAX v1, AAVE v1)

Grid (`scripts/run_near_full_research.py`, **475,200 combinations**): 1/3/5m candles × 1–15 day completed-close
average × ±0.1…0.5% zone (from below + green confirmation, avoid strong bearish) × stop −0.5…−4% × giveback
10…30% with trail start at break-even (+0.245…+0.315%) or break-even + 1% (+1.245…+1.315%) × break-even stop
none/+0.5%/+0.75% (+1% starts) × trend none / above 30-day / above 30-day ≤ +10% × all hours / skip 06–12 UTC.
$300, full $100 lots, at most 3 open, no time exit, 10 bps fee + 2 bps slippage. Data: Binance NEARUSDT 1m,
Sep 2024 – Jul 2026 plus unseen Aug 1 – Sep 10 2026 (checksums verified, no gaps).

**Only 279 profitable; 60 profitable in both periods.** All use the +1% trail start; 1m candles: none profitable.

## Candidate (weak)

**5m candles, 9-day average, ±0.1% zone, −4% stop, trail from +1.315% with 30% giveback, no trend filter, all
hours** (exact Stage 3 replay = fast grid to the cent)

| Costs | Window | Trades | Win rate | Profit on $300 | Max DD | PF |
|---|---|---:|---:|---:|---:|---:|
| 10/2 bps | Full | 266 | 79.7% | +$26.32 (+8.8%) | −11.07% | 1.12 |
| 10/2 bps | Earlier | 118 | 79.7% | +$4.73 | −9.03% | 1.05 |
| 10/2 bps | Later | 148 | 79.7% | +$21.59 | −11.23% | 1.17 |
| 10/2 bps | Unseen | 11 | 54.5% | −$13.37 | −8.96% | 0.36 |
| 7.5/2 bps (BNB) | Full | 270 | 79.6% | +$39.17 | −10.55% | 1.17 |
| 15/5 bps stress | Full | 222 | 77.9% | **−$32.63** | −17.68% | 0.85 |

Average winner +1.20%, loser −4.21%, 12.1 trades/month, average hold about 9 hours.

## Ideas, one change at a time (full / earlier / later / unseen)

| Change | Result | Verdict |
|---|---|---|
| Above 30-day filter | −$18 / −$17 / +$11 / −$13 | Worse |
| Above 30-day ≤ +10% | −$31 | Worse |
| Skip 06–12 UTC | +$22 / −$4 / +$27 / −$13 | Earlier period turns negative — not used |
| Break-even stop +0.5% / +0.75% | +$0.18 / −$12 | Worse |
| Stop −2% / −2.5% / −3% / −3.5% | −$92 · −$51 · −$4 · +$6 | Only −4% (edge of grid) is profitable |
| Trail start +0.315% (no +1%) | −$62 | +1% start essential |
| Zone ±0.05 / ±0.15% (exact) | −$13.71 · −$12.01 | **Fails** |
| Zone ±0.2 / ±0.3% | −$6 · −$7 | Fails |
| Average 8 / 10 days | −$17 · −$66 | **Knife-edge** |
| 3m / 1m candles | −$14 · −$40 | Fails |

## Selection checks

- Earlier-only pick (3m, 9-day, ±0.3%, −3.5%, break-even after +0.75%): earlier +$18.97 → later −$38.82, unseen
  −$17.79. Of the top 100 earlier-period combinations, 6 were profitable later (median −$34.11).
- Walk-forward (six windows): −$52.42, +$8.74, −$20.99, −$20.59, −$29.95, +$7.90 = **−$107.31**.
- Neighbourhood check: 1 combination had all neighbours available; its worst neighbour lost $21.74. None survive.

## Verdict

**No usable NEAR candidate.** The best setting is barely positive (+$4.73 in the earlier period), loses at stress
costs and on the unseen weeks, and fails if the zone moves by 0.05% or the average by one day. Not recommended.
