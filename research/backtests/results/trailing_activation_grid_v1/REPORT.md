# Stage 2 Trailing Exit Freeze Analysis

## Purpose and method

This analysis tests whether trailing should replace the frozen +4% profit target. It covers all 15 combinations of 3.0%, 3.5%, and 4.0% activation with 10%, 15%, 20%, 25%, and 30% giveback of open profit. Every variant retains the −4% hard stop, 24-hour cap, realistic 10 bps fee and 2 bps adverse slippage per side, conservative raw 1-minute execution, and one chronological position.

The activation candle cannot trigger the trail. If activation and the hard stop occur in the same minute, the stop wins. After activation, the trail uses the peak known before the current candle. These rules avoid assuming an unknown intraminute price order.

## Primary results

| Activation | Giveback | Earlier trades | Earlier mean | Later trades | Later mean | Combined mean | Profit factor | Max drawdown |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fixed +4% | — | 42 | +0.353% | 40 | +0.368% | +0.360% | 1.325 | −17.73% |
| 3.0% | 10% | 47 | +0.295% | 40 | +0.282% | +0.289% | 1.271 | −17.16% |
| 3.0% | 15% | 47 | +0.254% | 40 | +0.243% | +0.249% | 1.234 | −16.90% |
| 3.0% | 20% | 47 | +0.185% | 40 | +0.212% | +0.197% | 1.185 | −17.53% |
| 3.0% | 25% | 47 | +0.143% | 40 | +0.205% | +0.171% | 1.161 | −18.51% |
| 3.0% | 30% | 47 | +0.066% | 40 | +0.169% | +0.114% | 1.107 | −19.48% |
| 3.5% | 10% | 45 | +0.390% | 40 | +0.241% | +0.320% | 1.290 | −16.44% |
| 3.5% | 15% | 45 | +0.375% | 40 | +0.301% | +0.340% | 1.308 | −16.56% |
| 3.5% | 20% | 45 | +0.421% | 40 | +0.273% | +0.351% | 1.318 | −16.70% |
| 3.5% | 25% | 45 | +0.508% | 40 | +0.316% | +0.418% | 1.378 | −16.85% |
| 3.5% | 30% | 45 | +0.500% | 40 | +0.274% | +0.394% | 1.356 | −16.99% |
| 4.0% | 10% | 42 | +0.367% | 40 | +0.378% | +0.372% | 1.336 | −17.73% |
| 4.0% | 15% | 42 | +0.369% | 40 | +0.347% | +0.358% | 1.323 | −17.73% |
| 4.0% | 20% | 42 | +0.393% | 40 | +0.294% | +0.345% | 1.311 | −17.73% |
| 4.0% | 25% | 42 | +0.453% | 40 | +0.338% | +0.397% | 1.358 | −18.15% |
| 4.0% | 30% | 42 | +0.456% | 40 | +0.295% | +0.377% | 1.340 | −18.83% |

## Interpretation

The 3.5%/25% variant had the highest combined mean, but it weakened from +0.508% earlier to +0.316% later, below the fixed exit's +0.368%. Wider 4% trails similarly gained earlier and lost later while increasing drawdown.

Only 4% activation with 10% giveback improved mean return in both periods. The improvement was very small: +0.014 percentage points earlier and +0.010 later. Its 95% difference intervals were −0.059 to +0.094 and −0.056 to +0.117, so the observed gain is indistinguishable from noise. The control showed the same weak direction, but its intervals also crossed zero.

All primary variants had positive medians and profit factors above one, yet none showed a confidently positive improvement over the fixed target. The fixed baseline itself was reproduced exactly from Stage 1.5.

## Freeze decision

Freeze the **4% activation / 10% giveback** trail for the primary strategy. It is the only trailing variant that improved mean return in both historical periods. Reaching +4% now activates the trail instead of immediately selling. The control retains its fixed +4% take-profit.

The improvement is small and its confidence intervals include zero, so the evidence does not prove that trailing is superior. This uncertainty remains part of the frozen decision and must be checked with unseen Stage 3 paper-trading data.
