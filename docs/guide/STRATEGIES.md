# Strategies

Z-Bot buys spot coins (no leverage, no shorting) and sells them again. Every coin follows the same building blocks
with its own settings. This page is generated from the strategy files the bot runs
(`engine/*_strategy.json`), so it always matches the code.

## Ways in (how it buys)

| | Way in | In one line | Default |
|---|---|---|---|
| **D** | <a id="dip"></a>**Dip** | The price dips into the coin's average while the trend allows it, and a green candle confirms. | On — the tested core |
| **Q** | <a id="breakout"></a>**Quiet-band breakout** | The price breaks above a quiet, narrow range it has been stuck in. | On — the tested core |
| **P** | <a id="pullback"></a>**Pullback** | In a clean uptrend, a short dip below the trend line, bought when it turns back up. | On (ETH only) |
| **+** | <a id="add-ons"></a>**Add-ons** | One more lot on a lot that is already winning, while the climb holds. | Off (SOL only) |
| **B** | <a id="buy-now"></a>**Buy now** | You buy one lot yourself from the dashboard. | — |

Every way in buys from the same **shared pot** of lots, first come first served. The dip and the breakout can be
switched off per coin, but they are the setup the coin was tested with.

## Ways out (how it sells)

| Way out | In one line |
|---|---|
| <a id="stop-loss"></a>**Stop-loss** | If the price falls a set % below the buy, the lot is sold. The stop sits on Binance itself from the first minute. |
| <a id="trailing-stop"></a>**Trailing stop** | Once a lot is up a set %, a stop follows the best price and sells after a set share of the gain is given back. |
| <a id="trend-ride"></a>**Trend ride** | A lot bought in a clean uptrend (7-day > 15-day > 30-day average) is held while the price stays above a trend line, and sold when a minute closes below it. |
| <a id="break-even-floor"></a>**Break-even floor** | When a trend-ride lot starts taking profit, its stop moves up to the buy price plus costs, so it can no longer close at a loss. |

How a lot will sell is fixed the moment it is bought.

## Per coin

### Solana (SOL)

| Rule | Setting |
|---|---|
| Average | 12-day simple average of daily closes |
| Dip: buys when | the price rises from below into ±0.5% of the average, then a green 3-min candle confirms within 30 min |
| Skips buying when | the 7-, 15- and 30-day averages are stacked downward (a strong downtrend), or between 06:00 and 12:00 UTC |
| Quiet-band breakout | after 24h inside a band no wider than 2%, a close above the band buys at the next minute |
| Breakout lots sell | stop −4%, take profit from +1.283%, keep 78% of the best gain |
| Add-ons (optional, off by default) | while a lot is winning, add one more every +0.5%, up to 2 |
| Stop-loss | −2% below the buy price, parked on Binance |
| Takes profit | from +1.251%: a trailing stop keeps 88% of the best gain |
| Trend ride | a lot bought in a clean uptrend is instead held while the price stays above the 8h trend line, with a break-even floor once it is in profit |
| Costs assumed | 0.075% fee per side with BNB (0.1% without), plus 0.02% slippage |

### Ethereum (ETH)

| Rule | Setting |
|---|---|
| Average | 7-day simple average of daily closes |
| Dip: buys when | the price rises from below into ±0.5% of the average, then a green 5-min candle confirms within 30 min |
| Skips buying when | the 7-, 15- and 30-day averages are stacked downward (a strong downtrend), or between 06:00 and 12:00 UTC |
| Quiet-band breakout | after 24h inside a band no wider than 2.5%, a close above the band buys if the price is still above it 30 min later |
| Breakout lots sell | stop −3.5%, take profit from +1.283%, keep 78% of the best gain |
| Pullback | in a clean uptrend, after 3h under the 24h line, the first close back above it buys |
| Stop-loss | −4.5% below the buy price, parked on Binance |
| Takes profit | from +1.315%: a trailing stop keeps 70% of the best gain |
| Trend ride | a lot bought in a clean uptrend is instead held while the price stays above the 16h trend line, with a break-even floor once it is in profit |
| Costs assumed | 0.075% fee per side with BNB (0.1% without), plus 0.02% slippage |

### Bitcoin (BTC)

| Rule | Setting |
|---|---|
| Average | 5-day simple average of daily closes |
| Dip: buys when | the price rises from below into ±0.2% of the average, then a green 5-min candle confirms within 30 min |
| Skips buying when | the 7-, 15- and 30-day averages are stacked downward (a strong downtrend), or between 06:00 and 12:00 UTC |
| Extra dip rule | the confirming candle must close above the 30-day average |
| Stop-loss | −3% below the buy price, parked on Binance |
| Takes profit | from +1.257%: a trailing stop keeps 86% of the best gain |
| Costs assumed | 0.075% fee per side with BNB (0.1% without), plus 0.02% slippage |

### Aave (AAVE)

| Rule | Setting |
|---|---|
| Average | 10-day simple average of daily closes |
| Dip: buys when | the price rises from below into ±0.1% of the average, then a green 3-min candle confirms within 30 min |
| Skips buying when | the 7-, 15- and 30-day averages are stacked downward (a strong downtrend), or between 06:00 and 12:00 UTC |
| Quiet-band breakout | after 12h inside a band no wider than 2%, a close above the band buys if the price is still above it 60 min later |
| Breakout lots sell | stop −3.5%, take profit from +1.283%, keep 78% of the best gain |
| Stop-loss | −4% below the buy price, parked on Binance |
| Takes profit | from +1.75%: a trailing stop keeps 80% of the best gain |
| Costs assumed | 0.075% fee per side with BNB (0.1% without), plus 0.02% slippage |

### Tron (TRX)

| Rule | Setting |
|---|---|
| Average | 12-day simple average of daily closes |
| Dip: buys when | the price rises from below into ±0.1% of the average, then a green 1-min candle confirms within 30 min |
| Skips buying when | the 7-, 15- and 30-day averages are stacked downward (a strong downtrend) |
| Extra dip rule | the confirming candle must close above the 30-day average, by at most 10% |
| Quiet-band breakout | after 40h inside a band no wider than 2%, a close above the band buys if the price is still above it 3 min later |
| Breakout lots sell | stop −3%, take profit from +1.283%, keep 78% of the best gain |
| Stop-loss | −4% below the buy price, parked on Binance |
| Takes profit | from +1.245%: a trailing stop keeps 90% of the best gain |
| Costs assumed | 0.075% fee per side with BNB (0.1% without), plus 0.02% slippage |

---

Settings were chosen from backtests on Binance 1-minute data and then checked on periods the search never saw. How
that was done, and what did not work, is in [Research](RESEARCH.md). Past results do not predict future ones.
