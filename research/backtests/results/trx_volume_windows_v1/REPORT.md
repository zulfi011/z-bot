# TRX spot volume over 4h / 12h / 24h / 3-day windows (25 Oct 2026)

TRX only, 3 x $100 → 5 x $100 → +$20 per lot. Full tables: `tables.txt`.

## 1. ETH's 4h rule, unchanged (unbiased check)

Rule fixed on ETH: skip a buy when trades in the last 4h are more than 1.5× the 30-day normal
(`scripts/volume4h_rule_check.py`, `results/volume4h_rule_check_v1`).

| | TRX |
|---|---:|
| Profit change | **−$32.42** (+$250.30 → +$217.88) |
| Skipped buys | 43 trades, 91% win, +$33.79 |
| One-year starts better | 0/12 |
| Quarters better / worse | 1 / 6 |

Fails on TRX.

## 2. TRX's own full search (`FG_COIN=TRX scripts/eth_volume_windows.py`, 96 rules)

| | Profit | Win |
|---|---:|---:|
| No filter | +$250.30 | 92.7% |
| Best on full history: skip if 24h USDT volume > 2.5× normal | +$265.46 | 93.9% |
| Honest walk-forward | **−$39.22** vs no filter | better 0/6, worse 4/6 |
| Choose on one year, test on the other | $0.00 / −$2.72 | |

The best rule skips only 6 buys, 4 of them in June 2025 (−$16.65): the same June 2025 episode as TRX's best futures
rule. 14 of 96 rules beat no filter.

## Verdict: rejected.

## TRX summary: all four ideas plus the earlier coins' leads

| Test | Honest result | Verdict |
|---|---:|---|
| Fear & Greed, full search (81 rules) | −$8.74 (0/80 rules beat no filter) | rejected |
| SOL low-funding rule, unchanged | −$37.34 | fails |
| Futures, full search (77 rules) | +$1.36 (noise; best rule = June 2025) | rejected |
| Breadth, full search (94 rules) | −$5.85 (0/94 rules beat no filter) | rejected |
| ETH 4h-volume rule, unchanged | −$32.42 | fails |
| Volume windows, full search (96 rules) | −$39.22 (best rule = June 2025) | rejected |

TRX wins about 93% of its buys whatever the market looks like, so there is nothing for a filter to remove.
