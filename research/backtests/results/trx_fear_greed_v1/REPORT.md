# TRX + Crypto Fear & Greed Index (25 Oct 2026)

Test: `FG_COIN=TRX scripts/eth_fear_greed.py`, identical to the ETH and SOL tests. TRX only, 3 x $100 → 5 x $100 → +$20
per lot; 81 skip rules. Full tables: `tables.txt`.

## Verdict: rejected. Not one rule beats doing nothing.

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$250.30 | 92.7% | −$25.67 (−4.6%) |
| Best rule on full history | no filter itself (0 of 80 rules beat it) | | |
| Honest walk-forward | −$8.74 vs no filter | | better 0/6, worse 4/6 |
| Choose on one year, test on the other | $0.00 / −$50.31 | | |

- TRX wins at every mood level: extreme fear 94%, fear 97%, neutral 92%, greed 89%, extreme greed 100% (3 trades).
- Average loss is −3.2% to −3.5% everywhere. With a 93% win rate there is almost nothing for a filter to remove.
