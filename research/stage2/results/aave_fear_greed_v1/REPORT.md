# AAVE + Crypto Fear & Greed Index: full search (25 Oct 2026)

Test: `FG_COIN=AAVE scripts/eth_fear_greed.py`, identical to the other four coins. AAVE only, 3 x $100 → 5 x $100 →
+$20 per lot; 81 skip rules. Full tables: `tables.txt`.

## Verdict: rejected.

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$126.59 | 79.5% | −$36.07 (−10.2%) |
| Best on full history: skip after a 10-point drop in the index over 3 days | +$134.49 | 80.8% | −$31.95 (−10.0%) |
| Honest walk-forward | **−$30.52** vs no filter | | better 0/6, worse 4/6 |
| Choose on one year, test on the other | −$7.04 / −$39.27 | | |

- The best rules add under $8 and are inconsistent: the best rule loses in year 1 (−$6.55) and gains in year 2 (+$11.37).
- AAVE does best in fear (extreme fear 91% win, fear 85%) and worst in the neutral band (71%, −$8.22), the same
  middle-band pattern as ETH, SOL and BTC. A middle band is not a usable rule.
- Average loss is −4.0% to −4.2% at every level.
