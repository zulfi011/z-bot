# SOL + market breadth across 40 large coins (25 Oct 2026)

Test: `FG_COIN=SOL scripts/eth_breadth.py`, identical to the ETH test (same 40-coin breadth data, no new download).
SOL only, 3 x $100 → 5 x $100 → +$20 per lot; 94 skip rules. Full tables: `tables.txt`.

## Verdict: rejected.

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$91.72 | 75.8% | −$27.32 (−9.1%) |
| Best on full history: skip if the median coin rose >10% in 7 days | +$106.60 | 77.4% | −$19.02 (−5.8%) |
| Honest walk-forward (picked on the prior 6 months, used blind next quarter) | **−$39.35** vs no filter | | better 0/6, worse 4/6 |
| Choose on one year, test on the other | −$7.80 / +$2.79 | | |

- Every "market overheated" rule that looks good on SOL gets its gain from one episode, Nov–Dec 2024. The best rule's 34
  skipped buys (62% win, −$15.79) are 26 in Nov–Dec 2024 and 8 in Sep 2026, and it changes nothing in five of the six
  test quarters. These rules beat no filter in only ~3 of 12 one-year starts.
- That is the same stretch that made Fear & Greed's "extreme greed" skip look good on SOL. It is one bad run, counted twice.
- Average loss is −2.2% to −2.8% at every breadth level. 23 of 94 rules beat no filter on full history, all from that episode.
