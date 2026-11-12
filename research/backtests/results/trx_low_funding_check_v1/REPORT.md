# SOL's low-funding rule on TRX, unchanged (25 Oct 2026)

Script: `FG_COIN=TRX scripts/low_funding_rule_check.py`. Data: `data/trx_futures` (802/802 days, downloaded 25 Oct).
Rule fixed on SOL: skip a buy when 24h-average funding is in its trailing-90-day bottom 20%. Run on TRX before any
TRX futures search. TRX alone, $300, 3 x $100 → 5 x $100 → +$20 per lot. Full output: `tables.txt`.

## Verdict: fails on TRX.

| | TRX |
|---|---:|
| No rule | +$250.30 |
| With SOL's rule | +$212.95 (**−$37.34**) |
| Skipped TRX buys | 41 trades, **95% win**, +$40.22 |
| One-year starts better | 0/12 |
| Six-month starts better | 1/18 |
| Quarters better / worse | 1 / 6 |
| Year 1 / year 2 | −$13.05 / −$12.63 |
| At 10+10 bps costs | −$19.80 |

On TRX, low-funding buys are among its best (95% winners), the opposite of SOL (45%). The rule does not carry over.
