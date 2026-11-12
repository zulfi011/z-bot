# TRX + futures positioning: full search (25 Oct 2026)

Test: `FG_COIN=TRX scripts/eth_futures_filter.py`, identical to ETH and SOL. Data: `data/trx_futures`. TRX only,
3 x $100 → 5 x $100 → +$20 per lot; 12 features as trailing-90-day percentiles; 77 skip rules. Full tables: `tables.txt`.
The fixed SOL low-funding rule was checked first (`results/trx_low_funding_check_v1`): −$37.34.

## Verdict: rejected.

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$250.30 | 92.7% | −$25.67 (−4.6%) |
| Best on full history: skip when OI rise minus price change (24h) is in its top 5% | +$266.42 | 93.9% | −$25.67 |
| Honest walk-forward | +$1.36 vs no filter | | better 2/6, worse 3/6 |
| Choose on one year, test on the other | −$2.52 / −$0.78 | | |

- The best rule skips only 8 buys, and 7 of them were in June 2025 (−$14). One episode. It changes nothing in four of
  the six test quarters.
- 12 of 77 rules beat no filter, about chance. TRX wins 83–100% in every bucket, so there is little to filter.
- Low funding is not a warning sign on TRX: SOL's bottom-20% rule loses $37 here, and the buys it skips are 95% winners.
