# SOL vs ETH vs BTC — candidates on identical rules (best → worst)

Exact Stage 3 replay (`scripts/compare_coins.py`), $300 each, full $100 lots, at most 3 open, no time exit.
Full = Oct 2024 – Jul 2026, earlier = to Aug 2025, later = Sep 2025 – Jul 2026, unseen = Aug 1 – Sep 9 2026.

| Rank | Coin | Rules | Full | Earlier | Later | Unseen | Stress full | Stress later | Max DD | PF | Win rate | Walk-forward | Nearby settings |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | ETH | 5m, 7d, ±0.5%, −3.5%, +1.315%/30%, skip 06–12 | +$134.05 | +$83.42 | +$47.83 | +$6.71 | +$66.10 | +$28.47 | −8.98% | 1.86 | 83% | +$23.82 | Hold (±0.4–0.55%, 6–8 days, 1/3/5m) |
| 2 | SOL | 3m, 12d, ±0.5%, −2%, +1.251%/12%, skip 06–12 | +$47.14 | +$17.81 | +$29.34 | +$6.08 | +$3.27 | +$6.28 | −7.54% | 1.36 | 74% | not run | Fragile (11 and 13 days lose) |
| 3 | BTC | 5m, 5d, ±0.2%, −3%, +1.257%/14%, above 30-day, skip 06–12 | +$71.92 | +$59.23 | +$11.73 | −$13.38 | +$37.33 | −$5.19 | −8.28% | 1.64 | 81% | −$19.80 | Fails (4/6 days, ±0.15/±0.25% lose later) |

With BNB fees (0.075%): ETH +$145.95, BTC +$81.41, SOL +$57.32.

Why BTC ranks below SOL despite more full-period profit: 82% of BTC's profit came from the earlier period,
it is negative in the later period at stress costs and on the unseen weeks, walk-forward selection lost money,
and no nearby setting survives. SOL is smaller but positive in every window at normal costs, including unseen.

Portfolio view (monthly P&L by exit month, 21 months): correlation SOL–ETH 0.32, SOL–BTC 0.06, ETH–BTC 0.18.
Losing months: SOL 8, ETH 6, BTC 6. Share of profit in the best month: SOL 25%, ETH 50% (May 2025), BTC 42%.
Worst cumulative dip: SOL+ETH −$15.69; SOL+ETH+BTC −$25.52 (adding BTC deepens it).
