# ETH equal-planned-stop-risk sizing experiment

## Original fixed-$100 baseline

**$430.16 profit · 459 trades · 85.4% headline wins · $-4.55 average loss · -9.66% drawdown**

## Same $500 cash, no leverage or borrowing

| Sizing | Profit | Change | Trades | Win rate | Avg win | Avg loss | Drawdown | WF change | WF improved | Avg protective loss | Historical gap loss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| risk_4_50_cap_130 | $438.52 | $+8.35 | 459 (+0) | 85.4% | $1.91 | $-4.64 | -9.64% | $+5.45 | 5/6 | $4.64 | $0.00 |
| fixed_100_control (control) | $430.16 | $+0.00 | 459 (+0) | 85.4% | $1.88 | $-4.55 | -9.66% | $+0.00 | 0/6 | $4.55 | $0.00 |
| risk_4_00_cap_115 | $392.82 | $-37.34 | 459 (+0) | 85.4% | $1.71 | $-4.13 | -8.62% | $-39.78 | 1/6 | $4.13 | $0.00 |
| risk_3_50_cap_100 | $343.72 | $-86.45 | 459 (+0) | 85.4% | $1.49 | $-3.61 | -7.56% | $-86.07 | 0/6 | $3.61 | $0.00 |

## Actual order allocation

| Sizing | Entry family | Average order | Average planned stop risk | Profit contribution |
|---|---|---:|---:|---:|
| fixed_100_control | breakout | $100.00 | $3.50 | $30.79 |
| fixed_100_control | dip | $99.64 | $4.48 | $213.91 |
| fixed_100_control | pullback | $99.39 | $4.47 | $185.47 |
| risk_3_50_cap_100 | breakout | $100.00 | $3.50 | $30.79 |
| risk_3_50_cap_100 | dip | $77.78 | $3.50 | $168.56 |
| risk_3_50_cap_100 | pullback | $77.78 | $3.50 | $144.37 |
| risk_4_00_cap_115 | breakout | $114.29 | $4.00 | $35.18 |
| risk_4_00_cap_115 | dip | $88.89 | $4.00 | $192.65 |
| risk_4_00_cap_115 | pullback | $88.89 | $4.00 | $164.99 |
| risk_4_50_cap_130 | breakout | $128.57 | $4.50 | $39.58 |
| risk_4_50_cap_130 | dip | $99.56 | $4.48 | $213.46 |
| risk_4_50_cap_130 | pullback | $99.40 | $4.47 | $185.47 |

Orders can be smaller than their target when the shared cash wallet is partly occupied. They can never exceed available cash.

## Extra gap-through-stop stress

| Sizing | Additional adverse stop gap | Profit | Change from own unstressed result | Drawdown |
|---|---:|---:|---:|---:|
| fixed_100_control | +25 bps | $414.14 | $-16.02 | -10.27% |
| fixed_100_control | +50 bps | $398.11 | $-32.05 | -10.90% |
| risk_3_50_cap_100 | +25 bps | $331.15 | $-12.57 | -7.93% |
| risk_3_50_cap_100 | +50 bps | $318.58 | $-25.14 | -8.31% |
| risk_4_00_cap_115 | +25 bps | $378.46 | $-14.36 | -9.06% |
| risk_4_00_cap_115 | +50 bps | $364.09 | $-28.73 | -9.49% |
| risk_4_50_cap_130 | +25 bps | $422.08 | $-16.44 | -10.13% |
| risk_4_50_cap_130 | +50 bps | $405.64 | $-32.88 | -10.69% |

## Decision

**Advance `risk_4_50_cap_130` to forward testing, but do not deploy yet.**

Historical stop exits already use the worse of the stop level and the next tradable open. The separate +25/+50 bps cases show how every protective stop behaves under additional adverse execution.
