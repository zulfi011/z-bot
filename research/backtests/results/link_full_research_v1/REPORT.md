# LINK — Full Research v1 (same procedure as ETH v2 and BTC v1)

Grid (`scripts/run_link_full_research.py`, **475,200 combinations**): 1/3/5m candles × 1–15 day completed-close
average × ±0.1…0.5% zone (from below + green confirmation, avoid strong bearish) × stop −0.5…−4% × giveback
10…30% with trail start at break-even (+0.245…+0.315%) or break-even + 1% (+1.245…+1.315%) × break-even stop
none/+0.5%/+0.75% (+1% starts) × trend none / above 30-day / above 30-day ≤ +10% × all hours / skip 06–12 UTC.
$300, full $100 lots, at most 3 open, no time exit, 10 bps fee + 2 bps slippage. Data: Binance LINKUSDT 1m,
Sep 2024 – Jul 2026 plus unseen Aug 1 – Sep 10 2026 (checksums verified, no gaps).

**2,331 profitable; 529 profitable in both periods. All use the +1% trail start** — break-even starts: 0
profitable. 1,844 of the 2,331 use the 7-day average. Of the top 100 consistent combinations, 3 were profitable
on the unseen weeks (median −$14.49).

## Candidate

**1m candles, 7-day average, ±0.4% zone, −3% stop, trail from +1.306% with 28% giveback, only buy when LINK is
above its 30-day average, skip entries 06–12 UTC** (exact Stage 3 replay = fast grid to the cent)

| Costs | Window | Trades | Win rate | Profit on $300 | Max DD | PF |
|---|---|---:|---:|---:|---:|---:|
| 10/2 bps | Full | 248 | 80.2% | +$88.29 (+29.4%) | −13.30% | 1.56 |
| 10/2 bps | Earlier | 162 | 79.6% | +$55.35 | −13.30% | 1.52 |
| 10/2 bps | Later | 84 | 81.0% | +$30.20 | −8.22% | 1.59 |
| 10/2 bps | Unseen | 17 | 47.1% | −$18.38 | −6.93% | 0.36 |
| 7.5/2 bps (BNB) | Full | 248 | 80.2% | +$100.74 | −12.60% | 1.65 |
| 15/5 bps stress | Full | 237 | 78.9% | +$38.51 | −15.81% | 1.23 |
| 15/5 bps stress | Later | 80 | 80.0% | +$10.60 | −8.24% | 1.20 |

Average winner +1.23%, loser −3.21%, 11.3 trades/month, average hold about 11 hours.

## Ideas, one change at a time (full / earlier / later / unseen)

| Change | Result | Verdict |
|---|---|---|
| No trend filter | +$44 / +$35 / −$11 / −$16 | Above-30-day filter needed — kept |
| Above 30-day ≤ +10% | +$24 / −$4 / +$30 / −$10 | Worse |
| All hours (no 06–12 skip) | +$46 / +$38 / −$3 / −$16 | Skip needed for the later period — kept |
| Break-even stop +0.5% / +0.75% | +$18 / +$47 | Worse — dropped |
| Stop −2% / −2.5% / −3.5% / −4% | +$28 · +$65 · +$80 · +$88 (later +$44, unseen −$14) | −3% and −4% tie; −2% and tighter fail later |
| Trail start +0.306% (no +1%) | −$34 | +1% start essential |
| Zone ±0.3 / ±0.35 / ±0.45 / ±0.5% | +$25 · +$53 · +$46 · +$32 | Holds positive, but most of the profit is ±0.4% itself |
| Average 6 / 8 days | −$13 · −$26 | **Knife-edge: only 7 works** |
| 3m / 5m candles | +$35 · +$38 | Positive but much weaker |

## Selection checks

- Earlier-only pick (1m, 5-day, ±0.1%, −3.5%, no trend filter, skip 06–12): earlier +$75.06 → later −$31.48,
  unseen −$8.65. Of the top 100 earlier-period combinations, 4 were profitable later (median −$37.08).
- Walk-forward (best of previous 6 months, trade next 3, six windows): −$41.61, −$44.54, +$7.84, −$4.19,
  −$7.43, −$27.34 = **−$117.27**, worse than the median combination in four of six windows.
- Neighbourhood check (`scripts/robust_link_full_research.py`): **no combination stays profitable when its
  average moves ±1 day or its zone ±0.1%** (0 of 260). Best-behaved: 1m / 6-day / ±0.2% / −4% (+$25.86 full,
  −$1 unseen, worst neighbour −$13.62).

## Verdict

The best LINK result is one average length (7 days) with one zone (±0.4%). It is positive in both periods and
survives stress costs, but lost $18.38 on the unseen weeks, and choosing settings on past data lost $117 in
walk-forward — the grid is fitting noise on LINK. Treat it as a weak candidate, not paper-trading-ready.
