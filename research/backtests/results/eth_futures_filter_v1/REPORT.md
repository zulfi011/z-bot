# ETH + futures positioning: funding, open interest, long/short ratios (24 Oct 2026)

Script: `scripts/eth_futures_filter.py`. Data: `data/eth_futures_crowding` (Binance 5-minute metrics and 8-hourly
funding, Jul 2024 – Sep 2026). ETH only, compounding 3 x $100 → 5 x $100 → +$20 per lot per $100; the deployed rules
are unchanged and a filter can only skip a buy. There are 12 features, each turned into its percentile within the
trailing 90 days (causal), and 77 skip rules (top/bottom 5/10/20% of each feature, plus 5 "crowding" combinations).
Full tables: `tables.txt`.

## Verdict: rejected. Nothing to deploy.

| | Profit | Win | Drawdown |
|---|---:|---:|---:|
| No filter | +$356.51 | 86.7% | −12.9% (−$51.66) |
| Best on full history: skip when 24h-average funding is in its top 10% | +$374.88 | 88.1% | −7.0% (−$36.43) |
| Honest walk-forward (picked on the prior 6 months, used blind next quarter) | **−$14.72** vs no filter | | better 1/6, worse 5/6 |
| Choose on one year, test on the other | +$5.12 / −$19.51 | | |

- 12 of 77 rules beat no filter on full history, which is about what chance gives.
- Average loss is −3.8% to −4.7% in every quintile of every feature. Positioning does not shrink losses.
- One weak signal: buys in the top fifth of funding win 78%, against 87–93% elsewhere. But the top-10%-funding trades lost only −$7.95 in total, and −$27 of that was one month (Oct 2024). The drawdown improvement is that one episode, when the account was smallest. Held fixed over the six test quarters, the rule adds ~$0 in five of them and +$9.78 in one.
- Top-20% funding trades made +$20.55 together, so skipping them costs money.
