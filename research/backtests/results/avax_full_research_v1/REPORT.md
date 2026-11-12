# AVAX — Full Research v1 (same procedure as ETH v2, BTC v1 and LINK v1)

Grid (`scripts/run_avax_full_research.py`, **475,200 combinations**): 1/3/5m candles × 1–15 day completed-close
average × ±0.1…0.5% zone (from below + green confirmation, avoid strong bearish) × stop −0.5…−4% × giveback
10…30% with trail start at break-even (+0.245…+0.315%) or break-even + 1% (+1.245…+1.315%) × break-even stop
none/+0.5%/+0.75% (+1% starts) × trend none / above 30-day / above 30-day ≤ +10% × all hours / skip 06–12 UTC.
$300, full $100 lots, at most 3 open, no time exit, 10 bps fee + 2 bps slippage. Data: Binance AVAXUSDT 1m,
Sep 2024 – Jul 2026 plus unseen Aug 1 – Sep 10 2026 (checksums verified, no gaps).

**Only 139 of 475,200 combinations are profitable over the full period, and none (0) is profitable in both the
earlier and the later period.** Every profitable one uses the +1% trail start; 120 of the 139 use the 2-day average.

## Best full-period result (not a valid candidate)

**5m candles, 2-day average, ±0.3% zone, −4% stop, trail from +1.315% with 30% giveback, no trend filter, skip
entries 06–12 UTC** (exact Stage 3 replay = fast grid to the cent)

| Costs | Window | Trades | Win rate | Profit on $300 | Max DD | PF |
|---|---|---:|---:|---:|---:|---:|
| 10/2 bps | Full | 474 | 80.8% | +$94.62 | −20.48% | 1.25 |
| 10/2 bps | Earlier | 281 | 77.9% | **−$9.52** | −20.48% | 0.96 |
| 10/2 bps | Later | 197 | 85.3% | +$109.23 | −13.44% | 1.89 |
| 10/2 bps | Unseen | 20 | 65.0% | −$17.79 | −6.60% | 0.40 |
| 7.5/2 bps (BNB) | Full | 483 | 81.2% | +$128.78 | −17.23% | 1.34 |
| 15/5 bps stress | Full | 448 | 79.2% | **−$9.97** | −31.13% | 0.98 |

Average winner +1.25%, loser −4.21%, 21.6 trades/month, average hold about 10 hours.

All its profit comes from one stretch: **$127.64 in Jul–Sep 2025** (a single walk-forward window). It loses in
the earlier period, at stress costs over the full period, and on the unseen weeks.

## Ideas, one change at a time (full / earlier / later / unseen)

| Change | Result | Verdict |
|---|---|---|
| Above 30-day filter | +$19 / −$46 / +$87 / −$15 | Worse (unlike BTC and LINK) |
| Above 30-day ≤ +10% | −$58 | Worse |
| All hours | +$76 / −$7 / +$83 / −$21 | Skip 06–12 slightly better |
| Break-even stop +0.5% / +0.75% | −$64 / −$33 | Much worse |
| Stop −2% / −2.5% / −3% / −3.5% | −$9 · +$35 · +$62 · +$44 | Only very wide stops survive |
| Trail start +0.315% (no +1%) | −$96 | +1% start essential |
| Zone ±0.1 / ±0.2 / ±0.4 / ±0.5% | +$29 · +$45 · +$36 · +$27 | All lose in the earlier period |
| Average 1 / 3 / 4 days | −$67 · −$73 · −$90 | **Only 2 days works** |
| 1m / 3m candles | −$15 · +$19 | Worse |

## Selection checks

- Earlier-only pick (5m, 7-day, ±0.4%, −3%, no filter, skip 06–12): earlier +$43.40 → later −$51.82, unseen
  −$23.76. **0 of the top 100 earlier-period combinations were profitable later** (median −$54.64).
- Walk-forward (six windows): +$20.16, −$8.78, +$24.03, −$35.87, +$4.42, −$1.60 = **+$2.36** — essentially zero.
- Neighbourhood check: nothing to check — no combination is profitable in both periods.

## Verdict

**No usable AVAX candidate.** Under these rules AVAX's pullbacks to its averages kept falling through the stops
in the earlier period; the only profitable settings rode one strong stretch in mid-2025. Not recommended for
paper trading.
