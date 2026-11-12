# SOL + Crypto Fear & Greed Index (24 Oct 2026)

Same script and setup as the ETH test: `FG_COIN=SOL scripts/eth_fear_greed.py`. SOL only, $300 as 3 x $100 → 5 x $100
→ +$20 per lot per $100; deployed SOL rules unchanged; 81 skip rules. Full tables: `tables.txt`.

## Verdict: rejected.

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$91.72 | 75.8% | −$27.32 (−9.1%) |
| Best on full history: skip if F&G > 75 (extreme greed) | +$115.45 | 78.5% | −$19.02 (−5.6%) |
| Honest walk-forward (picked on the prior 6 months, used blind next quarter) | **−$47.34** vs no filter | | better 2/6, worse 4/6 |
| Choose on one year, test on the other | $0.00 / $0.00 | | |

- SOL buys in extreme greed were bad: 27 trades, 48% win, −$23.83. But **all 27 were in Oct–Dec 2024**. After that,
  no SOL buy happened in extreme greed, so the rule changes nothing in any later quarter (one-year starts better: 3/12).
  It is one episode, not a pattern that could be checked again.
- Neutral (45–55) was also weak (71% win, −$2.64), as on ETH. That is a middle band, not a usable rule.
- Average loss is −2.2% to −2.6% at every level.
