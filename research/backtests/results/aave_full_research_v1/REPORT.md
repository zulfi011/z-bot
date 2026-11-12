# AAVE — Full Research v1 (same procedure as ETH v2, BTC v1, LINK v1, AVAX v1)

Grid (`scripts/run_aave_full_research.py`, **475,200 combinations**): 1/3/5m candles × 1–15 day completed-close
average × ±0.1…0.5% zone (from below + green confirmation, avoid strong bearish) × stop −0.5…−4% × giveback
10…30% with trail start at break-even (+0.245…+0.315%) or break-even + 1% (+1.245…+1.315%) × break-even stop
none/+0.5%/+0.75% (+1% starts) × trend none / above 30-day / above 30-day ≤ +10% × all hours / skip 06–12 UTC.
$300, full $100 lots, at most 3 open, no time exit, 10 bps fee + 2 bps slippage. Data: Binance AAVEUSDT 1m,
Sep 2024 – Jul 2026 plus unseen Aug 1 – Sep 10 2026 (checksums verified, no gaps).

**8,344 profitable; 3,164 profitable in both periods** (8,337 with the +1% trail start, 7 with a break-even start).
Profitable settings spread over 6–10 day averages. Of the top 100 consistent combinations, 38 were profitable on the
unseen weeks (median $0.00).

## Candidate

**3m candles, 10-day average, ±0.1% zone, −4% stop, trail from +1.276% with 20% giveback, no trend filter, skip
entries 06–12 UTC** (exact Stage 3 replay = fast grid to the cent)

| Costs | Window | Trades | Win rate | Profit on $300 | Max DD | PF |
|---|---|---:|---:|---:|---:|---:|
| 10/2 bps | Full | 250 | 84.4% | +$77.23 (+25.7%) | −9.96% | 1.47 |
| 10/2 bps | Earlier | 142 | 82.4% | +$39.51 | −9.96% | 1.38 |
| 10/2 bps | Later | 104 | 86.5% | +$33.91 | −6.92% | 1.58 |
| 10/2 bps | Unseen | 17 | 82.4% | −$0.22 | −4.68% | 0.98 |
| 7.5/2 bps (BNB) | Full | 255 | 84.7% | +$96.70 | −9.59% | 1.60 |
| 7.5/2 bps (BNB) | Unseen | 17 | 82.4% | +$0.63 | −4.65% | 1.05 |
| 15/5 bps stress | Full | 232 | 82.3% | +$17.29 | −12.50% | 1.10 |
| 15/5 bps stress | Later | 98 | 85.7% | +$17.39 | −7.85% | 1.29 |

Average winner +1.14%, loser −4.21%, 11.4 trades/month, average hold about 9 hours.

## Ideas, one change at a time (full / earlier / later / unseen)

| Change | Result | Verdict |
|---|---|---|
| Above 30-day filter | +$32 / +$24 / +$7 / −$0.22 | Worse — not used |
| Above 30-day ≤ +10% | +$6 | Worse |
| All hours (no 06–12 skip) | +$25 / −$4 / +$30 / +$3 | Skip needed for the earlier period — kept |
| Break-even stop +0.5% / +0.75% | −$10 / +$18 | Worse — dropped |
| Stop −2% / −2.5% / −3% / −3.5% | −$9 · +$21 · +$42 · +$61 | Wider is better; −4% is the edge of the grid |
| Trail start +0.276% (no +1%) | −$42 | +1% start essential |
| Zone ±0.05 / ±0.15% (exact) | +$90.94 · +$84.52 (both positive in every period) | **Holds** |
| Zone ±0.2 / ±0.3 / ±0.5% | +$24 · −$15 · +$20 | Fades from ±0.2% |
| Average 8 / 9 / 11 / 12 days | −$13 · +$8 · −$38 · −$34 | **Knife-edge on the average** |
| 1m / 5m candles | +$48 · +$62 | Holds up |

## Selection checks

- Earlier-only pick (3m, 3-day, ±0.4%, −4%, above 30-day, skip 06–12): earlier +$58.15 → later −$24.93, unseen
  −$8.21. Of the top 100 earlier-period combinations, 13 were profitable later (median −$15.47).
- Walk-forward (six windows): −$5.71, −$18.46, −$33.81, −$12.93, +$32.34, +$3.70 = **−$34.87**; the candidate itself
  made +$80.82 in the same windows.
- Neighbourhood check (`scripts/robust_aave_full_research.py`): **46 combinations stay profitable when the average
  moves ±1 day and the zone ±0.1%** (7–9 day averages, 3m/5m) — the first coin since ETH with any. The most robust,
  5m / 7-day / ±0.2% / −3% / +1.315%/30% / above 30-day / skip 06–12, is weak on its own: +$32.89 full, +$4.61 at
  stress, −$11.07 unseen (exact replay).

## Verdict

A real but modest edge: profitable in both periods, flat on the unseen weeks, positive at stress costs, and the
zone can move ±0.05% without hurting it. The weak points are the average length (only 10 days carries the
candidate; 9 is marginal, 11 loses), the wide −4% stop against a +1.14% average win, and a negative walk-forward.
Better evidence than BTC, LINK and AVAX; not as robust as ETH.
