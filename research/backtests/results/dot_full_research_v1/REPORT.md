# DOT — Full Research v1 (same procedure as ETH v2, BTC v1, LINK v1, AVAX v1, AAVE v1, NEAR v1, LTC v1)

Grid (`scripts/run_dot_full_research.py`, **475,200 combinations**): 1/3/5m candles × 1–15 day completed-close
average × ±0.1…0.5% zone (from below + green confirmation, avoid strong bearish) × stop −0.5…−4% × giveback
10…30% with trail start at break-even (+0.245…+0.315%) or break-even + 1% (+1.245…+1.315%) × break-even stop
none/+0.5%/+0.75% (+1% starts) × trend none / above 30-day / above 30-day ≤ +10% × all hours / skip 06–12 UTC.
$300, full $100 lots, at most 3 open, no time exit, 10 bps fee + 2 bps slippage. Data: Binance DOTUSDT 1m,
Sep 2024 – Jul 2026 plus unseen Aug 1 – Sep 10 2026 (checksums verified, no gaps).

**3,091 profitable; 797 profitable in both periods — but every one needs a trend filter** (no-filter: 0 profitable)
and the profits are small: the best full-period result is +$27.35. DOT's long downtrend leaves few entries
(the candidate made only 35 trades in the earlier 11 months). Of the top 100 consistent combinations, 82 were
profitable on the unseen weeks (median +$9.33) — the most of any coin so far, but on small amounts.

## Candidate (weak)

**1m candles, 10-day average, ±0.3% zone, −1.5% stop, trail from +1.306% with 28% giveback, only buy when DOT is
above its 30-day average by at most 10%, all hours** (exact Stage 3 replay = fast grid to the cent)

| Costs | Window | Trades | Win rate | Profit on $300 | Max DD | PF |
|---|---|---:|---:|---:|---:|---:|
| 10/2 bps | Full | 136 | 63.2% | +$27.35 (+9.1%) | −8.03% | 1.32 |
| 10/2 bps | Earlier | 35 | 60.0% | +$7.99 | −2.82% | 1.33 |
| 10/2 bps | Later | 101 | 64.4% | +$19.36 | −8.22% | 1.31 |
| 10/2 bps | Unseen | 33 | 45.5% | −$15.08 | −7.56% | 0.51 |
| 7.5/2 bps (BNB) | Full | 136 | 63.2% | +$34.16 | −7.57% | 1.41 |
| 15/5 bps stress | Full | 129 | 61.2% | +$1.85 | −9.31% | 1.02 |
| 15/5 bps stress | Later | 92 | 62.0% | −$2.34 | −9.16% | 0.96 |

Average winner +1.32%, loser −1.72%, 6.2 trades/month, average hold about 6 hours. Unlike the other coins, DOT
prefers a tight stop (−1.5% to −2%).

Unseen-friendly variant (grid): **5m / 10-day / ±0.2% / −2% / +1.315%/30% / above 30-day ≤ +10% / skip 06–12** —
+$26.72 full, +$4.49 earlier, +$22.23 later, **+$16.05 unseen**, only 84 trades in 23 months.

## Ideas, one change at a time (full / earlier / later / unseen)

| Change | Result | Verdict |
|---|---|---|
| No trend filter | −$62 | Filter essential |
| Above 30-day (no cap) | −$11 | The ≤ +10% cap matters |
| Skip 06–12 UTC | +$21 / +$5 / +$16 / −$6 | Similar; slightly less profit, better unseen |
| Break-even stop +0.5% / +0.75% | −$0.58 / +$15 | Worse |
| Stop −1% / −2% / −2.5% / −3% | +$6 · +$24 (unseen +$14) · +$17 (unseen +$17) · −$8 | −1.5% to −2.5% |
| Trail start +0.306% (no +1%) | −$26 | +1% start essential |
| Zone ±0.25 / ±0.35% (exact) | −$0.85 · +$29.14 | Mixed |
| Zone ±0.2 / ±0.4 / ±0.5% | +$5 · +$18 · −$5 | Mixed |
| Average 8 / 9 / 11 / 12 days | −$75 · −$35 · −$13 · −$43 | **Knife-edge: only 10 days works** |
| 3m / 5m candles | +$11 · +$25 | 5m holds |

## Selection checks

- Earlier-only pick (3m, 3-day, ±0.1%, −4%, break-even after +0.75%, above 30-day, skip 06–12): earlier +$38.38 →
  later −$34.14, unseen −$17.83. **0 of the top 100 earlier-period combinations were profitable later.**
- Walk-forward (six windows): +$24.36, −$21.93, −$9.01, −$2.03, −$36.40, $0.00 = **−$45.01**.
- Neighbourhood check: 1 combination survives (5m / 10-day / ±0.3% / −1.5% / break-even after +0.75%), worst
  neighbour +$0.09, full +$14.43.

## Verdict

**Weak candidate.** DOT only works with the capped trend filter and a 10-day average, trades rarely, earns little
(+$27 in 23 months, about +$2 at stress costs) and the candidate lost on the unseen weeks. Not recommended.
