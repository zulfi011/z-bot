# ETH spot volume over 4h / 12h / 24h / 3-day windows (24 Oct 2026)

Scripts: `scripts/eth_volume_windows.py` (ETH search) and `scripts/volume4h_rule_check.py` (fixed rule on other coins,
results in `results/volume4h_rule_check_v1`). Measures, using only the minutes before the buy: USDT volume and trade
count over the window against the coin's 30-day normal, and the taker-buy share. 96 skip rules. Money rule: $300,
3 x $100 → 5 x $100 → +$20 per lot per $100. Full tables: `tables.txt`.

## Verdict: strongest ETH result so far, but it does not carry over to any other coin. Not deployed.

**On ETH:** skip a buy when trades in the last 4 hours are more than 1.5× normal.

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$356.51 | 86.7% | −$51.66 (−12.9%) |
| Skip if 4h trades > 1.5× normal | **+$413.57** | 89.1% | −$47.61 (−8.6%) |

- Picked by BOTH year splits on its own (chosen on year 1 → +$26.67 in year 2; chosen on year 2 → +$30.64 in year 1).
- Better in 12/12 one-year starts and 16/18 six-month starts; held fixed, better in 6 of 8 quarters.
- Every nearby threshold is also positive (USDT volume 1.25×: +$11, 1.5×: +$47, 2×: +$30, 2.5×: +$14).
- The 75 skipped buys won 76% (right at break-even) and lost −$24 in total, spread over 18 months.
- The walk-forward over all 96 rules is flat (−$0.57), because 6 months of training keeps picking other rules.

**Same rule, unchanged, on the other coins:**

| | Profit change | Skipped buys: win, profit | One-year starts better |
|---|---:|---|---:|
| SOL | −$28.62 | 78%, +$23 | 0/12 |
| TRX | −$32.42 | 91%, +$34 | 0/12 |
| AAVE | −$4.39 | 79%, +$37 | 8/12 |
| BTC | −$38.02 | 87%, +$42 | 0/12 |
| 5-coin shared pot | **−$97.35** | 80%, +$129 | 2/12 |

On the other four coins, the busy-hours buys are good ones. So either busy hours hurt only ETH, or the ETH result is
luck. These data can't tell which; only fresh ETH data (after Sep 2026) can.
