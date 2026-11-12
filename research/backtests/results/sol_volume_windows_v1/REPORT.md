# SOL spot volume over 4h / 12h / 24h / 3-day windows (25 Oct 2026)

Test: `FG_COIN=SOL scripts/eth_volume_windows.py`, identical to the ETH test. SOL 1-minute candles already on disk.
SOL only, 3 x $100 → 5 x $100 → +$20 per lot; 96 skip rules (USDT volume and trade count vs 30-day normal, taker-buy
share). Full tables: `tables.txt`.

## Verdict: rejected. The clearest "no" of the four SOL tests.

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$91.72 | 75.8% | −$27.32 (−9.1%) |
| Best on full history: skip if 4h USDT volume < 0.5× normal | +$96.28 | 76.6% | −$22.41 (−7.4%) |
| Honest walk-forward (picked on the prior 6 months, used blind next quarter) | **−$57.48** vs no filter | | better 0/6, worse 6/6 |
| Choose on one year, test on the other | −$9.46 / −$1.58 | | |
| ETH's rule (skip if 4h trades > 1.5× normal), unchanged | −$28.62 | | 0/12 one-year starts |

- The best rule adds only +$4.56. No window or measure separates SOL's losing buys, and the average loss is −2.2% to
  −2.8% everywhere.
- On SOL the busy 4-hour stretches are not bad (4h USDT volume >2× normal: 12 trades, 92% win). So the ETH "busy hours"
  rule does not apply here.

## SOL summary: all four data ideas

| Idea | Best rule on full history | Honest walk-forward | Verdict |
|---|---|---:|---|
| Fear & Greed | skip extreme greed, +$24 (all Oct–Dec 2024) | −$47.34 | rejected |
| Futures positioning | skip when funding is in its bottom 20%, +$24 (12/12 one-year starts) | −$12.27 | lead, re-check on TRX/AAVE/BTC |
| Market breadth | skip when the market is overheated, +$15 (Nov–Dec 2024) | −$39.35 | rejected |
| Volume windows | skip quiet 4h, +$4.56 | −$57.48 | rejected |
