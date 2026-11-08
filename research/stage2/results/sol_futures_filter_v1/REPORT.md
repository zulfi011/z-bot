# SOL + futures positioning: funding, open interest, long/short ratios (25 Oct 2026)

Data: `data/sol_futures` (Binance archive: 802/802 days of 5-minute metrics, 2,406 funding settlements, Jul 2024 –
Sep 2026), downloaded with `scripts/download_eth_futures_crowding.py --symbol SOLUSDT`. Test:
`FG_COIN=SOL scripts/eth_futures_filter.py`, identical to the ETH test. SOL only, 3 x $100 → 5 x $100 → +$20 per lot;
12 features as trailing-90-day percentiles; 77 skip rules. Full tables: `tables.txt`.

## Verdict: not proven. One SOL-only lead, kept for a fixed re-check.

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$91.72 | 75.8% | −$27.32 (−9.1%) |
| Best on full history: skip when 24h-average funding is in its bottom 20% | **+$115.95** | 79.2% | −$25.67 (−8.5%) |
| Honest walk-forward (picked on the prior 6 months, used blind next quarter) | **−$12.27** vs no filter | | better 2/6, worse 2/6 |
| Choose on one year, test on the other | −$3.50 / +$6.12 | | |

**The lead: don't buy SOL when funding is unusually low** (futures traders leaning short, or not paying to be long).
- Those buys won only 45% (29 trades, −$24.75), and the losses are spread over 10 different months.
- Better in 12/12 one-year starts and 16/18 six-month starts, and positive in both halves.
- The close cousin "latest funding in its bottom 20%" also works: +$17.62, 12/12, 18/18.
- Weaknesses:
  - The bottom-10% version adds only +$4, and the bottom-5% version +$0.15. The effect sits in a narrow band.
  - 29 trades is a small sample.
  - The honest walk-forward lost −$12. After the first quarter it kept picking this rule (+$4 in the last quarter), but its first pick was another rule (−$15).
  - On ETH the same rule is weak and mixed: +$3.54 in total, −$19 in year 1, +$25 in year 2.

Everything else: average loss is −2.2% to −2.7% in every bucket, and 12 of 77 rules beat no filter, about chance.

**Pre-registered for later:** "skip when 24h-average funding is in its trailing-90-day bottom 20%" will be applied
unchanged to TRX, AAVE and BTC when their futures data is tested. If it holds there, it is real.
