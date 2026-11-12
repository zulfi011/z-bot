# AAVE + futures positioning (25 Oct 2026)

Data: `data/aave_futures` (802/802 days, 2,406 funding settlements), downloaded 25 Oct. AAVE only, 3 x $100 → 5 x $100
→ +$20 per lot. Full tables: `tables.txt` here and in `results/aave_low_funding_check_v1`.

## 1. SOL's low-funding rule, unchanged (unbiased check)

Skip when 24h-average funding is in its trailing-90-day bottom 20%: **−$31.21** on AAVE. The 67 skipped buys won 82%
(+$41.52). Better in 0/12 one-year starts and 3/8 quarters, and the worst drop deepens (−$48 vs −$36). Fails.
The SOL rule has now failed on all three other coins it was tested on: TRX −$37, BTC −$12, AAVE −$31.

## 2. AAVE's own full search (`FG_COIN=AAVE scripts/eth_futures_filter.py`, 77 rules)

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$126.59 | 79.5% | −$36.07 (−10.2%) |
| Best on full history: skip when open interest FELL most in the last hour (bottom 10%) | +$157.71 | 82.8% | −$33.24 |
| Honest walk-forward | **−$28.90** vs no filter | | better 0/6, worse 5/6 |
| Choose on one year, test on the other | −$14.51 / −$14.84 | | |

## Verdict: rejected.

- The best rule's 47 skipped buys (62% win, −$23.10) look spread out, but $19.50 of the loss is one month (July 2026),
  and held fixed it is worse in 2 of 6 test quarters. The 5% version of the same rule adds +$22 but loses in 7 of 12
  one-year starts.
- 22 of 77 rules beat no filter on full history, but the walk-forward never picked a winner (0/6), and both year-split
  picks lost about $15.
- Average loss is −4.0% to −4.2% in every bucket.
