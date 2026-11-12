# AAVE spot volume over 4h / 12h / 24h / 3-day windows (25 Oct 2026)

AAVE only, 3 x $100 → 5 x $100 → +$20 per lot. Full tables: `tables.txt` here and in `results/aave_fixed_volume_rules_v1`.

## 1. Earlier coins' volume rules, unchanged (`FG_COIN=AAVE scripts/fixed_volume_rule_check.py`)

| Rule | Profit change | Skipped buys: win, profit | One-year starts better |
|---|---:|---|---:|
| ETH busy-4h (skip if 4h trades > 1.5×) | −$4.39 | 79%, +$36.59 | 8/12 |
| BTC quiet-4h (skip if 4h trades < 0.75×) | **−$51.11** | 81%, +$59.59 | 0/12 |

Both fail. ETH's rule helps in 8 of 12 one-year starts, but the total is negative and the skipped buys are winners.

## 2. AAVE's own full search (`FG_COIN=AAVE scripts/eth_volume_windows.py`, 96 rules)

| | Profit |
|---|---:|
| No filter | +$126.59 |
| Best on full history: skip if 12h taker-buy share > 0.52 | +$130.63 (+$4.04) |
| Rules beating no filter | 2 of 96 |
| Honest walk-forward | **−$53.19** (better 1/6, worse 5/6) |
| Choose on one year, test on the other | −$15.65 / −$9.22 |

## Verdict: rejected. AAVE's volume carries no signal.
