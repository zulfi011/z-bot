# AAVE + market breadth across 40 large coins: full search (25 Oct 2026)

Test: `FG_COIN=AAVE scripts/eth_breadth.py`, identical to the other coins. AAVE only, 3 x $100 → 5 x $100 → +$20 per
lot; 94 skip rules. Full tables: `tables.txt`.

## Verdict: rejected.

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$126.59 | 79.5% | −$36.07 (−10.2%) |
| Best on full history: skip when >95% of coins are above their 30-day average | +$136.61 | 81.2% | **−$45.46 (−14.5%)** |
| Honest walk-forward | **−$41.69** vs no filter | | better 1/6, worse 4/6 |
| Choose on one year, test on the other | −$15.05 / −$35.25 | | |

- Only 3 of 94 rules beat no filter. The best one skips 21 buys (−$12.55), but they swing between big wins and losses
  (Nov 2024 +$18.70, Sep 2026 −$16.65), it loses in year 1 (−$3.85), and it makes the worst drop deeper.
- No breadth level separates AAVE's losing buys. Average loss is −3.9% to −4.2% at every level.
