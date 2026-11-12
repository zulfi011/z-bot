# ETH live-execution calibration

## Observation status

**INSUFFICIENT — Need 30 complete real ETH fills; found 0**

No usable local export of real Lightsail ETH fills is available yet. Therefore the table below is **provisional sensitivity**, not an observed median, p90 or worst result. The runner will automatically replace it with observed percentiles after at least 30 complete ETH fills are exported.

## Cost recalculation

| Scenario | Evidence | Fee/side bps | Slippage/side bps | Round trip bps | Profit | Change | Avg loss | Drawdown |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| current_bnb_model | provisional | 7.50 | 2.00 | 19.0 | $430.16 | $+0.00 | $-4.55 | -9.66% |
| usdt_fee_current_slippage | provisional | 10.00 | 2.00 | 24.0 | $408.66 | $-21.51 | $-4.60 | -10.02% |
| provisional_5bps_slippage | provisional | 7.50 | 5.00 | 25.0 | $396.16 | $-34.01 | $-4.57 | -10.58% |
| provisional_10bps_slippage_usdt_fee | provisional | 10.00 | 10.00 | 40.0 | $323.36 | $-106.80 | $-4.67 | -11.19% |
| provisional_20bps_slippage_usdt_fee | provisional | 10.00 | 20.00 | 60.0 | $205.98 | $-224.18 | $-4.74 | -13.55% |

Every row rebuilds the break-even floor from that scenario's fee and slippage, then replays the same five-slot ETH strategy with full window-end truncation.

## Decision

**No live strategy conclusion yet.** Deploy the telemetry migration/code separately when approved, collect at least 30 real ETH fills, export them, and rerun this experiment.

Do not describe the provisional 5/10/20 bps cases as measured live execution.
