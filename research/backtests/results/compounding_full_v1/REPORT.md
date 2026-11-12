# Compounding plan vs live money rule (re-check of compounding_strategy.md)

Scripts: `scripts/compounding_build_candidates.py`, `scripts/compounding_full_analysis.py`, `scripts/compounding_honest_tests.py`.
Same five deployed rule books (SOL now with its break-even floor), one $300 wallet, first come first served,
7.5 bps fee + 2 bps slippage per side, Oct 1 2024 – Sep 10 2026, hourly mark-to-market drawdown.

- **LIVE**: today's code. Per-coin lots (ETH 5, others 3) of $100, no global cap, and the last buy takes whatever cash is left. Profits stay in the wallet, so live already adds more $100 lots as cash grows.
- **PLAN**: from the document. 3 slots, then 4 at $400 and 5 at $500; after that each extra $100 adds $20 to every lot.

| | Live | Plan |
|---|---:|---:|
| Profit, full 23 months | +$657 | +$792 |
| Max drawdown | −$54 (−13.2%) | −$74 (−14.9%) |
| Profit per $ of drawdown | **12.2** | 10.7 |
| Average money in open trades | $191 | $259 |
| 12-month runs (12 start dates): plan beats live | – | 7/12, median +$7, worst −$28 |
| 6-month runs (18 start dates): plan beats live | – | **3/18**, median −$6 |
| Costs 10+10 bps | +$314 | +$367 |

All of the plan's extra profit comes after Oct 2025, once the account had already grown. In year one it matched or trailed live.
Live with $140 lots makes +$760 at −15.7%, close to the plan, so the gain comes from having more money in trades, not from a better rule.
The document's own grid run actually picked **3 slots** (+$964, −15.5%, lots up to $433), not 5. It is even more concentrated, and it loses to live in 13 of 18 six-month runs.

**Verdict:** the plan does not beat live. It turns the same signals into bigger bets once the account is up. That pays over a long winning stretch, but over 6–12 months it is a coin flip or worse, and it always has a deeper drawdown.

## ETH alone, starting at 3 x $100 (`scripts/compounding_eth_only.py`, outputs in `eth_only/`)

| | Plan 3→5 then +$20 | Fixed 3x$100 | Live ETH (5 lots, cash-limited) |
|---|---:|---:|---:|
| Profit, Oct 2024 – Sep 10 2026 | +$357 | +$295 | +$360 |
| Max drawdown | −$52 (−12.9%) | −$39 (−12.9%) | −$43 (−12.9%) |
| 12-month starts, plan wins | – | 11/12 | **0/12** |
| 6-month starts, plan wins | – | 6/18 | 2/18 |

Growth steps: $400 on 2025-05-09 (4 lots), $500 on 2025-08-22 (5 lots), $600 on 2026-04-22 (5 x $120). Nothing more by Sep 2026.
The plan beats a frozen 3 x $100, but not the live rule, which already spends every free dollar as profit builds.

## Ideal N and ideal lot increase (17 Oct 2026, `scripts/compounding_ideal_n_step*.py`, outputs in `ideal_n_step/`)

108 plans (N = 3–12 lots, then +$0…$50 per lot for each further $100), full history, 12/6-month starts,
choose-one-year/test-the-other, 10+10 bps costs.

- **Ideal N = 5.** Lot 4 adds +$84, lot 5 adds +$57 for only $1.58 more drawdown. Lot 6 and above add little (+$21, +$18 …) and $7 more drawdown. A $300 account never reaches lot 6 within any 12-month run.
- **Increase after 5: +$20 (spends exactly the new $100).** Full-history profit/DD rises to a flat ridge at +$25…+$40 (10.9–11.0 vs 10.7). That rests on one price path, because no 12-month run gets past $600. +$50 breaks (−$92 drawdown).
- Honest selection by profit picks the most aggressive plan in both years (both years were up). By profit/drawdown it picks LIVE (earlier) or N4 +$35 (later).
- Live is still the most efficient: profit/DD 12.2 vs 10.7 for N5 +$20.

Per coin (N5 +$20 vs live): TRX +$281 vs +$213, ETH +$224 vs +$234, AAVE +$148 vs +$94, BTC +$78 vs +$47, SOL +$60 vs +$70. The 5-lot cap means fewer trades (ETH takes 46% of its signals vs 61% on live).

## Which coins in the shared pot (17 Oct 2026, `scripts/compounding_coin_sets.py`, outputs in `coin_sets/`)

All 31 combinations, under the 5-lot +$20 plan and under fixed 5 x $100 (the answer is the same for both).
- All five is best: +$792, ahead of every subset, and no hand-picked subset beat it out-of-sample (4/4 selection tests lost to all five).
- Taking each coin out: TRX −$339, ETH −$253, AAVE −$152, BTC −$57, SOL −$32. ETH and TRX are the core. BTC and SOL are small but positive, and dropping them barely lowers the drawdown.
- Closest rival is ETH+TRX+AAVE+SOL (+$735, −11.8% vs −14.9%). It beats all five in 8/12 twelve-month and 10/18 six-month starts, so dropping BTC is a reasonable lower-drawdown choice. Not proven better.

## ETH + TRX + AAVE only (17 Oct 2026, outputs in `ideal_n_step_eth_trx_aave/`)

Same 108-plan grid and tests, run on the three coins only. Ideal is still 5 lots then +$20.
- 3 coins: +$668, DD −$71 (−11.9%), profit/DD 9.4, 12-month median +$260, 6-month median +$122.
- 5 coins: +$792, DD −$74 (−14.9%), profit/DD 10.7, 12-month median +$306, 6-month median +$132.
- The 3-coin pot is only ahead at 10+10 bps costs (+$380 vs +$367). It does not improve the result.
