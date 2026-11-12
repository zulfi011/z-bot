# ETH + market breadth across 40 large coins (24 Oct 2026)

Script: `scripts/eth_breadth.py`. Data: `data/breadth/raw`, Binance spot daily candles for 40 coins that were large
caps in mid-2024 (1,110 of 1,120 monthly files; only LINK's last 4 months and TON's pre-listing months are missing,
and 38–40 coins have data every day). Measures: % of coins above their 30/15/7-day average, % up over 7 days,
median 7-day return, and the 7-day change in 30-day breadth. Values use completed days only, from 00:05 UTC the next
day. ETH only, compounding 3 x $100 → 5 x $100 → +$20 per lot per $100; 94 skip rules. Full tables: `tables.txt`.

## Verdict: not deployable. One lead worth re-checking on new data later.

| | Profit | Win | Worst drop |
|---|---:|---:|---:|
| No filter | +$356.51 | 86.7% | −$51.66 (−12.9%) |
| Best on full history: skip when >95% of coins are above their 15-day average | +$387.66 | 88.1% | −$36.65 (−10.4%) |
| Honest walk-forward over all 94 rules | **−$45.08** vs no filter | | better 1/6, worse 5/6 |
| Walk-forward over only the "market overheated" rules (chosen after seeing results, so flattering) | +$2.02 | | better 1/6, worse 4/6 |
| Choose on one year, test on the other | −$6.33 / −$44.53 | | |

**The lead: skip buying when the whole market is overheated.** That means >90–95% of coins above their 7- or 15-day average, or a median coin up >10% in a week.
- Those buys win only 70% (below ETH's ~76% break-even) and lost −$22.68 over 47 trades, spread across six different months, not one.
- These rules beat no filter in 11–12 of 12 one-year starts and 13–14 of 18 six-month starts. They help in both halves, help at 10+10 bps costs, and cut the worst dollar drop from −$52 to about −$36.
- The same theme showed up weakly with Fear & Greed (skip after a 15-point weekly rise: +$26).
- **But:** the profit gain jumps around with the exact threshold (15-day breadth >85%: +$3; >90%: +$22; >95%: +$31), and a rule chosen in advance never reliably beat no filter. On this data it can't be told apart from luck.

Other levels show nothing: average loss is −4.2% to −4.7% at every breadth level, and weak breadth (a falling market) is not worse for ETH buys.
