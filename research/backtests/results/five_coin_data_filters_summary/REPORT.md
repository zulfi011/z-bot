# Four market-data ideas on all five coins: summary (25 Oct 2026)

Each coin was traded alone with the same money rule ($300, 3 x $100 → 5 x $100 → +$20 per lot per $100), its deployed
entries and exits unchanged; a filter could only skip a buy. Oct 2024 – Sep 10 2026. For every coin and idea: a full
rule search (81 / 77 / 94 / 96 rules), then honest tests. Leads from earlier coins were also re-run unchanged.

**Honest walk-forward** = rule chosen on the previous 6 months, used blind in the next quarter, six quarters, versus no
filter. Each coin's folder is `results/<coin>_<idea>_v1/REPORT.md`.

## 1. Each coin's own full search: honest walk-forward result

| Coin | Fear & Greed | Futures (funding, OI, long/short) | Market breadth (40 coins) | Volume windows (4h–3d) |
|---|---:|---:|---:|---:|
| ETH | −$66.24 | −$14.72 | −$45.08 | −$0.57 |
| SOL | −$47.34 | −$12.27 | −$39.35 | −$57.48 |
| TRX | −$8.74 | +$1.36 | −$5.85 | −$39.22 |
| BTC | −$17.62 | −$23.02 | −$6.57 | +$1.03 |
| AAVE | −$30.52 | −$28.90 | −$41.69 | −$53.19 |

18 of 20 negative. The two positives (+$1.36, +$1.03) are noise. Together: **−$536**.

## 2. Leads found on one coin, re-run unchanged on the others

| Lead (where found, full-history gain) | Applied unchanged to | Result |
|---|---|---|
| ETH: skip if 4h trades > 1.5× normal (+$57) | SOL, TRX, BTC, AAVE | −$28.62, −$32.42, −$38.02, −$4.39 → **0/4** |
| ETH: skip if >90% of coins above 15d average (+$22) | SOL, TRX, BTC, AAVE | +$11.84, −$47.05, −$55.94, −$37.33 → 1/4 |
| SOL: skip if 24h funding in bottom 20% (+$24) | TRX, BTC, AAVE | −$37.34, −$11.86, −$31.21 → **0/3** |
| BTC: skip if 4h trades < 0.75× normal (+$32) | AAVE | −$51.11 → **0/1** |

1 success out of 12 transfers, and that one (SOL breadth) lost in most one-year starts.

## 3. What the data says

- **Average loss never changes.** On every coin and every bucket of every measure, the average losing trade is the
  same size (ETH ≈ −4.5%, SOL ≈ −2.2%, TRX ≈ −3.3%, BTC ≈ −3.1%, AAVE ≈ −4.1%). That is the protective stop. Market
  mood, futures positioning, breadth and volume change how OFTEN a coin loses a little, never how MUCH.
- **Coins react in opposite ways.** BTC buys best when the market is hot and greedy; SOL buys worst then. ETH's bad
  buys come in busy hours, BTC's in quiet ones. TRX wins about 93% whatever the conditions. No single rule fits all,
  which is why every transfer failed.
- **Single-coin "wins" are usually one episode.** SOL Nov–Dec 2024, TRX June 2025, BTC Feb 2025, AAVE July 2026.

## 4. Verdict

**Nothing to deploy. Keep the live strategy as it is.**

Three single-coin hypotheses remain. None passed the honest test, and each failed on every other coin it was tried on:
- ETH busy-4h: skip if 4h trades > 1.5× normal (+$57 on ETH; both year splits picked it on their own; walk-forward −$0.57).
- BTC quiet-4h: skip if 4h trades < 0.75× normal (+$32 on BTC; both years positive; walk-forward +$1.03).
- SOL low funding: skip if 24h-average funding is in its 90-day bottom 20% (+$24 on SOL; 12/12 one-year starts; walk-forward −$12.27).

The only fair way to settle them is to apply each, on its own coin only, exactly as fixed to new data after 10 Sep 2026, for example
in shadow mode, once a few months of trades have accumulated. Re-searching thresholds on the same history would only
find more luck.
