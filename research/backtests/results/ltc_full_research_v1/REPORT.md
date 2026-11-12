# LTC — Full Research v1 (same procedure as ETH v2, BTC v1, LINK v1, AVAX v1, AAVE v1, NEAR v1)

Grid (`scripts/run_ltc_full_research.py`, **475,200 combinations**): 1/3/5m candles × 1–15 day completed-close
average × ±0.1…0.5% zone (from below + green confirmation, avoid strong bearish) × stop −0.5…−4% × giveback
10…30% with trail start at break-even (+0.245…+0.315%) or break-even + 1% (+1.245…+1.315%) × break-even stop
none/+0.5%/+0.75% (+1% starts) × trend none / above 30-day / above 30-day ≤ +10% × all hours / skip 06–12 UTC.
$300, full $100 lots, at most 3 open, no time exit, 10 bps fee + 2 bps slippage. Data: Binance LTCUSDT 1m,
Sep 2024 – Jul 2026 plus unseen Aug 1 – Sep 10 2026 (checksums verified, no gaps).

**1,661 profitable; 320 profitable in both periods.** All use the +1% trail start; 1,250 of the 1,661 use the
"above 30-day average but ≤ +10%" filter; profitable averages cluster at 6–8 days. **None of the top 100 consistent
combinations was profitable on the unseen weeks** (median −$10.00).

## Candidate

**5m candles, 7-day average, ±0.1% zone, −3.5% stop, trail from +1.29% with 24% giveback, only buy when LTC is
above its 30-day average by at most 10%, skip entries 06–12 UTC** (exact Stage 3 replay = fast grid to the cent)

| Costs | Window | Trades | Win rate | Profit on $300 | Max DD | PF |
|---|---|---:|---:|---:|---:|---:|
| 10/2 bps | Full | 218 | 78.9% | +$53.79 (+17.9%) | −10.42% | 1.31 |
| 10/2 bps | Earlier | 127 | 78.0% | +$28.13 | −8.30% | 1.27 |
| 10/2 bps | Later | 75 | 77.3% | +$7.95 | −11.08% | 1.13 |
| 10/2 bps | Unseen | 8 | 62.5% | −$8.35 | −4.16% | 0.41 |
| 7.5/2 bps (BNB) | Full | 218 | 78.9% | +$64.72 | −9.83% | 1.38 |
| 15/5 bps stress | Full | 215 | 78.1% | +$23.02 | −14.53% | 1.13 |
| 15/5 bps stress | Later | 73 | 76.7% | **−$3.56** | −12.04% | 0.95 |

Average winner +1.31%, loser −3.71%, 9.9 trades/month, average hold about 16 hours.

Robust alternative (every average ±1 day / zone ±0.1% neighbour profitable): same rules with **±0.4% zone and −3%
stop** — +$50.13 full, +$34.00 earlier, +$13.64 later, −$8.23 unseen; +$60.10 with BNB fees; +$16.20 at stress but
−$9.67 in the later period at stress (exact replay).

## Ideas, one change at a time (full / earlier / later / unseen)

| Change | Result | Verdict |
|---|---|---|
| No trend filter | +$48 / +$22 / +$23 / −$13 | Close; filter improves earlier |
| Above 30-day (no cap) | +$44 / +$19 / +$8 / −$8 | Slightly worse |
| All hours (no 06–12 skip) | −$1 | Skip essential — kept |
| Break-even stop +0.5% / +0.75% | −$11 / +$28 | Worse — dropped |
| Stop −2% / −2.5% / −3% / −4% | +$43 (later −$8) · +$32 · +$49 · +$52 | −3% to −4% similar |
| Trail start +0.29% (no +1%) | −$26 | +1% start essential |
| Zone ±0.05 / ±0.15% (exact) | +$35 (later −$4) · +$53 | Mixed |
| Zone ±0.2 / ±0.3 / ±0.4 / ±0.5% | +$32 · +$32 · +$37 · +$2 | Positive to ±0.4% |
| Average 5 / 6 / 8 / 9 days | −$25 · +$31 · −$9 · −$26 | Mostly 7 days only |
| 1m / 3m candles | −$13 · +$28 | 5m best |

## Selection checks

- Earlier-only pick (5m, 1-day, ±0.5%, −4%, above 30-day, skip 06–12): earlier +$74.76 → later −$37.07, unseen
  −$13.48. **0 of the top 100 earlier-period combinations were profitable later** (median −$16.29).
- Walk-forward (six windows): −$29.10, +$3.80, −$41.16, −$29.27, +$9.73, −$4.18 = **−$90.19**.
- Neighbourhood check: 10 combinations survive, all 5m / 7-day / above 30-day ≤ +10% / skip 06–12 (see alternative).

## Verdict

**Weak candidate.** Positive in both periods, but the later period is thin (+$7.95, negative at stress costs), the
unseen weeks lost money for both the candidate and the robust alternative, and walk-forward selection lost $90.
Not recommended for paper trading on this evidence.
