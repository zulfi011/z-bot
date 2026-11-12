# BTC + Crypto Fear & Greed Index: full search (25 Oct 2026)

Test: `FG_COIN=BTC scripts/eth_fear_greed.py`, identical to ETH, SOL and TRX. BTC only, 3 x $100 → 5 x $100 → +$20 per
lot; 81 skip rules. Full tables: `tables.txt`.

## Verdict: rejected.

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$71.65 | 79.3% | −$29.51 (−7.9%) |
| Best on full history: skip after a 25-point weekly drop in the index | +$74.82 (+$3.16, 1 trade skipped) | 79.7% | −$29.51 |
| Honest walk-forward | **−$17.62** vs no filter | | better 1/6, worse 3/6 |
| Choose on one year, test on the other | $0.00 / −$55.94 | | |

- Only 1 of 80 rules beats no filter, by removing a single trade.
- BTC's best buys are in **extreme greed** (96% win, +$38.59), the opposite of SOL. Its weakest band is neutral (68%,
  −$6.77), a middle band and not a usable rule.
- Average loss is −3.0% to −3.2% at every level.
