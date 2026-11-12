# Out-of-sample check of the ETH "market overheated" breadth rule (24 Oct 2026)

Script: `scripts/breadth_rule_check.py`. One rule, fixed before any other coin was looked at, with no threshold
search: **skip a buy when more than 90% of the 40 breadth coins closed above their 15-day average.** Money rule as
in the ETH test: $300, 3 x $100 → 5 x $100 → +$20 per lot per $100. Oct 2024 – Sep 10 2026. Full tables: `tables.txt`.

## Verdict: it does not carry over. The ETH result was luck. Rejected.

| | Profit change | Skipped trades: win rate, their profit | One-year starts better | Quarters better / worse |
|---|---:|---|---:|---:|
| SOL alone | +$11.84 | 64%, −$9.87 | 3/12 (median −$5) | 3 / 3 |
| TRX alone | **−$47.05** | 95%, +$44.18 | 0/12 | 0 / 7 |
| AAVE alone | **−$37.33** | 81%, +$28.57 | 4/12 | 3 / 4 |
| BTC alone | **−$55.94** | 93%, +$67.02 | 0/12 | 2 / 5 |
| ETH alone (where it was found) | +$21.98 | 78%, −$0.64 | 11/12 | 4 / 3 |
| 5-coin shared pot | **−$120.60** | 84%, +$88.30 | 2/12 | 3 / 4 |

- On TRX, BTC and AAVE the "overheated market" buys are among their best: 95%, 93% and 81% winners. Skipping them throws profit away.
- Only SOL gains, and even there it loses in most one-year starts.
- In the five-coin pot the rule costs $121 (15% of profit). It lowers the worst drop (−$58 vs −$74) only because less money is at work.

This closes the three entry-confidence data ideas (Fear & Greed, futures positioning, market breadth): none of them improves the strategy.
