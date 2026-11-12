# TRX + market breadth across 40 large coins: full search (25 Oct 2026)

Test: `FG_COIN=TRX scripts/eth_breadth.py`, identical to ETH and SOL (same 40-coin data). TRX only, 3 x $100 → 5 x $100
→ +$20 per lot; 94 skip rules. Full tables: `tables.txt`.

## Verdict: rejected. Not one rule beats doing nothing.

| | Profit | Win |
|---|---:|---:|
| No filter | +$250.30 | 92.7% |
| Rules beating no filter on full history | **0 of 94** | |
| Honest walk-forward | −$5.85 vs no filter | better 0/6, worse 1/6 |
| Choose on one year, test on the other | $0.00 / −$3.54 | |

- TRX wins 82–100% at every breadth level, and "overheated market" buys are among its best (96% win when >80% of coins
  are above their 7-day average). ETH's fixed overheated rule already lost $47 on TRX on 24 Oct.
