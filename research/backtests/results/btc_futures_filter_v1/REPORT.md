# BTC + futures positioning (25 Oct 2026)

Data: `data/btc_futures` (802/802 days, 2,406 funding settlements), downloaded 25 Oct. BTC only, 3 x $100 → 5 x $100 →
+$20 per lot. Full tables: `tables.txt` here and in `results/btc_low_funding_check_v1`.

## 1. SOL's low-funding rule, unchanged (unbiased check)

Skip when 24h-average funding is in its trailing-90-day bottom 20%: **−$11.86** on BTC. The 29 skipped buys won 79%
(+$11.37). Better in 5/12 one-year starts and 2/8 quarters. Fails.

## 2. BTC's own full search (`FG_COIN=BTC scripts/eth_futures_filter.py`, 77 rules)

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$71.65 | 79.3% | −$29.51 (−7.9%) |
| Best on full history: skip when the LATEST funding is in its bottom 20% | +$91.73 | 82.5% | −$30.47 |
| Honest walk-forward | **−$23.02** vs no filter | | better 0/6, worse 5/6 |
| Choose on one year, test on the other | +$9.57 / −$4.53 | | |

## Verdict: rejected.

- The best rule is a near-twin of SOL's: latest funding instead of the 24h average. But the two disagree on BTC: the
  latest-funding version skips buys that lost −$16.46 (60% win), while the 24h-average version skips buys that made
  +$11.37 (79% win). Most of the latest-funding gain is one month (Feb 2025, −$18.99), and held fixed it is better in
  only 3 of 6 test quarters (2 worse).
- When the honest walk-forward picked this rule (twice), it lost money both times (−$7.92, −$3.26).
- 16 of 77 rules beat no filter. Average loss is −2.6% to −3.2% everywhere.

**Low funding across coins so far** (24h-average bottom 20%, i.e. SOL's rule): SOL +$24 (found there), TRX −$37,
BTC −$12. The "latest funding" variant: SOL +$18, BTC +$20. Not a consistent, tradeable effect.
