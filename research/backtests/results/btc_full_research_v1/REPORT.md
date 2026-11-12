# BTC — Full Research v1 (same procedure as ETH v2)

Grid (`scripts/run_btc_full_research.py`, **475,200 combinations**): 1/3/5m candles × 1–15 day completed-close
average × ±0.1…0.5% zone (from below + green confirmation, avoid strong bearish) × stop −0.5…−4% × giveback
10…30% with trail start at break-even (+0.245…+0.315%) or break-even + 1% (+1.245…+1.315%) × break-even stop
none/+0.5%/+0.75% (+1% starts) × trend none / above 30-day / above 30-day ≤ +10% × all hours / skip 06–12 UTC.
$300, full $100 lots, at most 3 open, no time exit, 10 bps fee + 2 bps slippage. Unseen data: Binance archives
BTCUSDT-1m-2026-08 and 2026-09-01 … 09-10 (checksums verified).

**4,891 profitable; 855 profitable in both periods. Every one of them uses the +1% trail start** — break-even
starts: 0 profitable. Of the top 100 consistent combinations, 31 were profitable on the unseen weeks (median −$4.85).

## Candidate

**5m candles, 5-day average, ±0.2% zone, −3% stop, trail from +1.257% with 14% giveback, only buy when BTC is
above its 30-day average, skip entries 06–12 UTC** (exact Stage 3 replay = fast grid to the cent)

| Costs | Window | Trades | Win rate | Profit on $300 | Max DD | PF |
|---|---|---:|---:|---:|---:|---:|
| 10/2 bps | Full | 189 | 81.5% | +$71.92 (+24.0%) | −8.28% | 1.64 |
| 10/2 bps | Earlier | 131 | 81.7% | +$59.23 | −8.28% | 1.77 |
| 10/2 bps | Later | 57 | 80.7% | +$11.73 | −4.71% | 1.33 |
| 10/2 bps | Unseen | 9 | 33.3% | −$16.50 | −5.54% | 0.14 |
| 7.5/2 bps (BNB) | Full | 189 | 81.5% | +$81.41 | −8.01% | 1.73 |
| 15/5 bps stress | Full | 188 | 80.3% | +$37.33 | −9.15% | 1.30 |
| 15/5 bps stress | Later | 47 | 76.6% | −$5.19 | −6.27% | 0.86 |

Average winner +1.20%, loser −3.21%, 8.6 trades/month, average hold about 25 hours.

## Ideas, one change at a time (full / earlier / later / unseen)

| Change | Result | Verdict |
|---|---|---|
| No trend filter | +$53 / +$58 / −$10 / −$13 | Above-30-day filter needed for the later period — kept |
| Above 30-day ≤ +10% | +$51 / +$38 / +$12 / −$12 | Worse |
| All hours (no 06–12 skip) | +$68 / +$62 / −$2 / −$17 | Skip helps later — kept |
| Break-even stop +0.5% / +0.75% | +$16 / +$47 | Worse — dropped |
| Stop −2% / −2.5% / −3.5% / −4% | +$45 · +$61 · +$69 (unseen +$0.17) · +$59 (unseen +$0.10) | −3% best overall; −3.5% the only one flat on unseen |
| Trail start +0.257% (no +1%) | −$34 | +1% start essential |
| Zone ±0.1 / ±0.3 / ±0.4% | +$57 · +$30 · −$13 | Falls apart from ±0.3% |
| Zone ±0.15 / ±0.25% (exact) | +$59 (later −$8) · +$62 (later −$9) | Later period turns negative |
| Average 4 / 6 days | −$15 · +$0.33 | **Knife-edge: only 5 works** |
| 1m / 3m candles | +$30 · +$63 | 3m holds up |

## Selection checks

- Earlier-only pick (5m, 5-day, ±0.2%, −2.5%, no trend filter, skip 06–12): earlier +$64.75 → later −$17.51,
  unseen −$13.49. Of the top 100 earlier-period combinations, 8 were profitable later (median −$20.01).
- Walk-forward (best of previous 6 months, trade next 3, six windows): −$1.14, −$5.68, −$3.22, −$5.86, −$9.64,
  +$5.74 = **−$19.80**. The median of all combinations in the same windows is worse in five of six windows, but
  the selection process itself lost money.
- Neighbourhood check (`scripts/robust_btc_full_research.py`): **no combination stays profitable when its
  average is moved ±1 day or its zone ±0.1%** (0 of 434 consistent combinations with all neighbours present).
  The best-behaved families are 3–5m / 5-day / ±0.2% and 5m / 14-day / ±0.4% (the latter only +$1…+$8 full).

## Verdict

The candidate is the best BTC result under the same rules as SOL and ETH, but it is fragile: one average length
(5 days) and one zone band (±0.2%) carry it, the later period is thin (+$11.73, negative at stress costs), the
unseen weeks lost $16.50, and walk-forward selection lost money. Treat it as a weak candidate, not a
paper-trading-ready strategy.
