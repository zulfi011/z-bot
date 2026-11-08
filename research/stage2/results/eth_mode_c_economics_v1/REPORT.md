# ETH Mode C marginal-economics experiment

## Original baseline

**$430.16 profit · 459 trades · 85.4% headline wins · $-4.55 average loss · -9.66% drawdown**

Mode C itself filled **45 trades**, earned **$30.79**, averaged **$0.68 per trade**, and had **6 protective stops**.

| Variant | Total profit | Change vs original | Trades | Mode C trades | Mode C profit | Win rate | Avg loss | Drawdown | WF change | WF improved | Blocks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| mode_c_one_lot_per_frozen_band | $431.81 | $+1.65 | 456 (-3) | 41 | $29.20 | 85.5% | $-4.56 | -9.66% | $+1.65 | 1/6 | 4 |
| mode_c_fresh_band_after_failed_breakout | $430.16 | $+0.00 | 459 (+0) | 45 | $30.79 | 85.4% | $-4.55 | -9.66% | $+0.00 | 0/6 | 0 |
| mode_c_failed_breakout_cooldown_6h | $430.16 | $+0.00 | 459 (+0) | 45 | $30.79 | 85.4% | $-4.55 | -9.66% | $+0.00 | 0/6 | 0 |
| mode_c_no_active_dip_pullback_episode | $427.46 | $-2.70 | 457 (-2) | 41 | $24.15 | 85.3% | $-4.55 | -9.66% | $-2.70 | 0/6 | 4 |
| without_mode_c | $403.20 | $-26.97 | 416 (-43) | 0 | $0.00 | 85.3% | $-4.64 | -10.67% | $-18.88 | 1/6 | 0 |

## Decision

**Keep Mode C unchanged.** None of the restrictions passed the robustness gates.

Removing Mode C changed total portfolio profit by **$-26.97**, not simply -$30.79, because freed ETH slots admitted replacement Dip/Pullback signals.

The August–September 2026 period remains post-selection data and is not used for acceptance.
