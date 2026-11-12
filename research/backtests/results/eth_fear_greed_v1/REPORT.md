# ETH + Crypto Fear & Greed Index (24 Oct 2026)

Script: `scripts/eth_fear_greed.py` (data: `data/fear_greed/fng_daily.csv`, alternative.me, 739/740 days covered).
ETH only, compounding money rule: $300, 3 x $100, 4th lot at $400, 5th at $500, then +$20 per lot per $100.
Every deployed ETH entry and exit is unchanged; a rule can only skip a buy. The value stamped day D is used from 00:05 UTC.
Full tables: `tables.txt`.

## Verdict: rejected. Nothing to deploy.

| | Profit | Trades | Win | Drawdown |
|---|---:|---:|---:|---:|
| No filter (control) | +$356.51 | 457 | 86.7% | −12.9% |
| Best on full history: skip if F&G rose ≥15 in 7 days | +$382.73 | 432 | 87.5% | −13.1% |
| Honest walk-forward (rule picked on prior 6 months, used blind next quarter) | **−$66.24** vs control | | | better 1/6, worse 4/6 |
| Choose on one year, test on the other | −$115.64 / −$2.51 | | | |

- Average loss is the same at every index level (−4.3% to −4.7%). The index does not make losses smaller.
- By level: extreme fear 91% win, fear 92%, **neutral 77%**, greed 87%, extreme greed 80%. The only weak band is the middle one, which is noise, not a tradable rule.
- The best rule's 34 skipped trades lost only −$2.70 in total at a 79% win rate. Its +$26 comes mostly from freeing lots in one month (Oct 2025), and the honest walk-forward picked it in only 3 of 6 quarters.
- Excluding high-greed or extreme-fear buys always cost money (for example, skip >65: −$53; skip <20: −$60).
