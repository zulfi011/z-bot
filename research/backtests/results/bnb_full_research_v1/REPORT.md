# BNB — Full Research v1 (same procedure as ETH v2, BTC v1 and the other new coins)

Grid (`scripts/run_bnb_full_research.py`, **475,200 combinations**): 1/3/5m candles × 1–15 day completed-close
average × ±0.1…0.5% zone (from below + green confirmation, avoid strong bearish) × stop −0.5…−4% × giveback
10…30% with trail start at break-even (+0.245…+0.315%) or break-even + 1% (+1.245…+1.315%) × break-even stop
none/+0.5%/+0.75% (+1% starts) × trend none / above 30-day / above 30-day ≤ +10% × all hours / skip 06–12 UTC.
$300, full $100 lots, at most 3 open, no time exit, 10 bps fee + 2 bps slippage. Data: Binance BNBUSDT 1m,
Sep 2024 – Jul 2026 plus unseen Aug 1 – Sep 10 2026 (checksums verified, no gaps).

**664 profitable; 116 profitable in both periods.** All use the +1% trail start. Of the top 100 consistent
combinations, 99 were profitable on the unseen weeks (median +$12.91) — BNB rose steadily in Aug–Sep 2026, which
flatters every long-only setting.

## Candidate (weak)

**1m candles, 9-day average, ±0.1% zone, −4% stop, trail from +1.298% with 26% giveback, no trend filter, skip
entries 06–12 UTC** (exact Stage 3 replay = fast grid to the cent)

| Costs | Window | Trades | Win rate | Profit on $300 | Max DD | PF |
|---|---|---:|---:|---:|---:|---:|
| 10/2 bps | Full | 264 | 78.0% | +$36.98 (+12.3%) | −17.99% | 1.15 |
| 10/2 bps | Earlier | 164 | 77.4% | +$31.34 | −17.99% | 1.21 |
| 10/2 bps | Later | 98 | 78.6% | +$1.45 | −15.88% | 1.02 |
| 10/2 bps | Unseen | 11 | 100% | +$11.78 | −3.98% | — |
| 7.5/2 bps (BNB) | Full | 264 | 78.0% | +$50.21 | −17.01% | 1.21 |
| 15/5 bps stress | Full | 233 | 76.8% | **−$6.53** | −23.32% | 0.97 |
| 15/5 bps stress | Later | 92 | 79.3% | −$7.00 | −16.72% | 0.91 |

Average winner +1.35%, loser −4.14%, 12 trades/month, average hold about 35 hours; worst dip −18%.

## Ideas, one change at a time (full / earlier / later / unseen)

| Change | Result | Verdict |
|---|---|---|
| Above 30-day filter | +$22 / +$47 / −$18 / +$12 | Later period negative |
| Above 30-day ≤ +10% | +$26 / +$51 / −$19 / +$9 | Later period negative |
| All hours (no 06–12 skip) | +$0.94 | Skip essential — kept |
| Break-even stop +0.5% / +0.75% | −$50 / −$42 | Much worse |
| Stop −1% … −3.5% | +$1 · −$23 · −$17 · −$15 · −$32 · −$22 | **Only −4% (edge of grid) works** |
| Trail start +0.298% (no +1%) | −$98 | +1% start essential |
| Zone ±0.05 / ±0.15% (exact) | −$7.70 · +$19.83 (earlier −$2) | **Fails** |
| Zone ±0.2 … ±0.5% | −$10 · −$10 · −$36 · −$70 | Fails |
| Average 7 / 8 / 10 / 11 days | −$52 · −$62 · −$36 · −$32 | **Knife-edge: only 9 days works** |
| 3m / 5m candles | +$35 (later +$26) · +$29 | Hold up |

## Selection checks

- Earlier-only pick (3m, 11-day, ±0.1%, −4%, above 30-day, skip 06–12): earlier +$55.89 → later −$41.31.
  **0 of the top 100 earlier-period combinations were profitable later** (median −$39.98).
- Walk-forward (six windows): −$5.57, −$0.19, +$5.96, −$22.02, +$12.53, −$6.35 = **−$15.64**.
- Neighbourhood check: 0 of 70 combinations survive; best-behaved (3m / 4-day / ±0.4% / −2.5%) +$18.16 with a
  worst neighbour of −$11.91.

## Verdict

**Weak candidate.** Only one average (9 days), one zone (±0.1%) and the widest stop (−4%) work; the later period is
flat (+$1.45) and turns negative at stress costs; the 18% worst dip is the deepest of the candidates. The positive
unseen weeks reflect BNB's rally rather than the rules (99 of the top 100 settings were positive there). Not
recommended.
