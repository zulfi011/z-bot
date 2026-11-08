# All 10 coins — candidates on identical rules (best → worst)

Exact Stage 3 replay (`scripts/compare_all_coins.py`) of each coin's candidate from its full research, $300 each,
full $100 lots, at most 3 open, no time exit. Full = Oct 2024 – Jul 2026, earlier = to Aug 2025, later = Sep 2025 –
Jul 2026, unseen = Aug 1 – Sep 9 2026 (SOL's archive ends Sep 9, so every coin is cut there). Normal costs 10 bps
fee + 2 bps slippage; BNB 7.5/2; stress 15/5. Walk-forward and nearby-settings results come from each coin's report.

| Rank | Coin | Full | Earlier | Later | Unseen | BNB full | Stress full | Stress later | Max DD | PF | Walk-forward | Nearby settings |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | **ETH** (live) | +$134.05 | +$83.42 | +$47.83 | +$6.71 | +$145.95 | +$66.10 | +$28.47 | −8.98% | 1.86 | +$23.82 | Hold |
| 2 | **AAVE** | +$77.23 | +$39.51 | +$33.91 | −$0.22 | +$96.70 | +$17.29 | +$17.39 | −9.96% | 1.47 | −$34.87 | Zone holds; only 10-day avg; 46 robust combos |
| 3 | **SOL** (live) | +$47.14 | +$17.81 | +$29.34 | +$6.08 | +$57.32 | +$3.27 | +$6.28 | −7.54% | 1.36 | not run | 12-day only |
| 4 | LINK | +$88.29 | +$55.35 | +$30.20 | −$18.38 | +$100.74 | +$38.51 | +$10.60 | −13.30% | 1.56 | −$117.27 | Fails |
| 5 | BTC (live) | +$71.92 | +$59.23 | +$11.73 | −$13.38 | +$81.41 | +$37.33 | −$5.19 | −8.28% | 1.64 | −$19.80 | Fails |
| 6 | LTC | +$53.79 | +$28.13 | +$7.95 | −$6.31 | +$64.72 | +$23.02 | −$3.56 | −10.42% | 1.31 | −$90.19 | 7-day only; 10 robust combos |
| 7 | DOT | +$27.35 | +$7.99 | +$19.36 | −$15.08 | +$34.16 | +$1.85 | −$2.34 | −8.03% | 1.32 | −$45.01 | 10-day only |
| 8 | BNB | +$36.98 | +$31.34 | +$1.45 | +$13.70 | +$50.21 | −$6.53 | −$7.00 | −17.99% | 1.15 | −$15.64 | Fails |
| 9 | NEAR | +$26.32 | +$4.73 | +$21.59 | −$13.37 | +$39.17 | −$32.63 | −$16.19 | −11.07% | 1.12 | −$107.31 | Fails |
| 10 | AVAX | +$94.62 | −$9.52 | +$109.23 | −$14.26 | +$128.78 | −$9.97 | +$74.61 | −20.48% | 1.25 | +$2.36 | No consistent setting |

How the order was decided: first, profitable in both periods; then whether it survives stress costs (especially
the later period); then the unseen weeks, nearby settings and walk-forward; full-period profit breaks ties. AVAX has
the second-highest full-period profit but loses in the earlier period and at stress costs, and 82% of its profit is
one month. BNB's positive unseen weeks reflect BNB's Aug–Sep rally (99 of its top 100 settings were positive there).

## Portfolio view (monthly P&L by exit month)

AAVE's monthly results are uncorrelated or negatively correlated with the live coins (SOL −0.27, ETH +0.10, BTC
−0.19). Worst cumulative dip in dollars: SOL+ETH −$15.69 (on $600), SOL+ETH+BTC −$25.52 (on $900), SOL+ETH+AAVE
−$28.07 (on $900), all four −$29.98 (on $1,200). Losing months: SOL 8, ETH 6, BTC 6, AAVE 8, LINK 5 of 23.

## Recommendation

Add **AAVE** to paper trading as the fourth coin. It is the only new coin that is profitable in both periods,
still profitable in the later period at stress costs, flat (not negative) on the unseen weeks, and whose zone can
move without breaking it. Watch its two weak points in paper trading: only the 10-day average works, and the −4%
stop means one loss erases about four wins. LINK is the next best but lost $117 in walk-forward and $18 on the
unseen weeks; keep it as a later option. The rest are not worth paper-trading capital on this evidence.
