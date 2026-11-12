# BTC spot volume over 4h / 12h / 24h / 3-day windows (25 Oct 2026)

BTC only, 3 x $100 → 5 x $100 → +$20 per lot. Full tables: `tables.txt`.

## 1. ETH's 4h rule, unchanged (unbiased check)

Skip when trades in the last 4h are more than 1.5× normal (`results/volume4h_rule_check_v1`): **−$38.02** on BTC.
The 52 skipped buys won 87% (+$41.73). Better in 0/12 one-year starts and 2/8 quarters. Fails.

## 2. BTC's own full search (`FG_COIN=BTC scripts/eth_volume_windows.py`, 96 rules)

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$71.65 | 79.3% | −$29.51 (−7.9%) |
| Best on full history: skip when trades in the last 4h are **below 0.75×** normal (a quiet market) | **+$103.17** | 85.8% | −$18.12 (−4.8%) |
| Honest walk-forward | +$1.03 vs no filter | | better 1/6, worse 3/6 |
| Choose on one year, test on the other | +$11.31 / −$23.15 | | |

## Verdict: not deployable. One BTC lead, the opposite of ETH's.

**The lead: on BTC, skip buys when the market has been unusually quiet for 4 hours.**
- The 61 skipped buys won only 61% (below BTC's ~71% break-even) and lost −$27.02. The losses are spread over 16
  different months, not one episode.
- Positive in both years (+$2.75 in year 1, +$25.56 in year 2) and better in 10/12 one-year starts. Held fixed it is
  better in 4 of 6 test quarters (1 worse), and it cuts the worst drop from −$29.51 to −$18.12.
- Nearby settings mostly agree: trades below 0.6× +$18, 0.9× +$14; USDT volume below 0.5× +$26, 0.6× +$19.
- **But** the honest walk-forward is flat (+$1.03). It picked this rule twice: −$6.69, then +$11.35.

ETH is the reverse: on ETH, unusually BUSY 4-hour stretches are the bad ones. So there is no common "volume rule" across
coins. If kept, it is a BTC-only hypothesis.

**Pre-registered for AAVE:** "skip when trades in the last 4h are below 0.75× normal" will be run unchanged on AAVE first.

## BTC summary: all four ideas plus the earlier coins' leads

| Test | Honest result | Verdict |
|---|---:|---|
| Fear & Greed, full search (81 rules) | −$17.62 | rejected |
| SOL low-funding rule, unchanged | −$11.86 | fails |
| Futures, full search (77 rules) | −$23.02 | rejected |
| Breadth, full search (94 rules) | −$6.57 | rejected |
| ETH 4h-volume rule, unchanged | −$38.02 | fails |
| Volume windows, full search (96 rules) | +$1.03; quiet-4h lead +$31.52 on full history | lead, not proven |
