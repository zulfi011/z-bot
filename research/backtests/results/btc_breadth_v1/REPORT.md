# BTC + market breadth across 40 large coins: full search (25 Oct 2026)

Test: `FG_COIN=BTC scripts/eth_breadth.py`, identical to the other coins. BTC only, 3 x $100 → 5 x $100 → +$20 per lot;
94 skip rules. Full tables: `tables.txt`.

## Verdict: rejected.

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$71.65 | 79.3% | −$29.51 (−7.9%) |
| Best on full history: skip when fewer than 10% of coins rose over the week | +$80.04 | 81.1% | −$21.93 (−5.9%) |
| Honest walk-forward | **−$6.57** vs no filter | | better 1/6, worse 3/6 |
| Choose on one year, test on the other | −$5.95 / −$50.74 | | |

- BTC behaves the opposite way to ETH and SOL. Its best buys come when the market is hot (>80% of coins above their
  7-day average: 87% win, +$45; median coin up >10%: 93% win, +$54), and its weak ones in a weak market. So the useful
  direction here is "skip in a washed-out market", not "skip when overheated".
- The best rule skips 23 buys (65% win, −$8.55), but held fixed it changes only one of six test quarters (+$6.38 in
  Apr–Jun 2025). Year 2 profit is $2.22 with or without it.
- 14 of 94 rules beat no filter.
