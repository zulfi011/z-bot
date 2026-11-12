# ETH canonical experiment engine v1

This local-only runner freezes the deployed ETH-v5 historical control before new exit, episode, allocation,
hours, or sizing experiments are introduced. It does not import another coin's strategy and does not connect to
Binance, Lightsail, or the live database.

From `stage2_backtesting`:

```bash
.env/bin/python -m experiments.eth_canonical_v1.run
.env/bin/python -m experiments.eth_canonical_v1.failure_exit
.env/bin/python -m experiments.eth_canonical_v1.repeated_exposure
.env/bin/python -m experiments.eth_canonical_v1.allocation
.env/bin/python -m experiments.eth_canonical_v1.concentration
.env/bin/python -m experiments.eth_canonical_v1.overfitting
.env/bin/python -m experiments.eth_canonical_v1.trade_quality
.env/bin/python -m experiments.eth_canonical_v1.fee_floor
.env/bin/python -m experiments.eth_canonical_v1.risk_throttle
.env/bin/python -m experiments.eth_canonical_v1.portfolio_risk
.env/bin/python -m experiments.eth_canonical_v1.mode_c_economics
.env/bin/python -m experiments.eth_canonical_v1.pullback_revalidation
.env/bin/python -m experiments.eth_canonical_v1.blocked_hours
.env/bin/python -m experiments.eth_canonical_v1.equal_stop_risk
.env/bin/python -m experiments.eth_canonical_v1.execution_calibration
.env/bin/python -m experiments.eth_canonical_v1.confirmation_quality
.env/bin/python -m experiments.eth_canonical_v1.delayed_stop_tightening
.env/bin/python -m experiments.eth_canonical_v1.setup_stop_risk
.env/bin/python -m experiments.eth_canonical_v1.pullback_quality
.env/bin/python -m experiments.eth_canonical_v1.mode_c_retest
.env/bin/python -m experiments.eth_canonical_v1.volatility_sizing
.env/bin/python -m experiments.eth_canonical_v1.protective_reentry
.env/bin/python scripts/download_eth_futures_crowding.py
.env/bin/python -m experiments.eth_canonical_v1.futures_crowding
.env/bin/python scripts/download_eth_forward_data.py
.env/bin/python -m experiments.eth_canonical_v1.forward_challengers
.env/bin/python -m experiments.eth_canonical_v1.time_to_arm
.env/bin/python -m experiments.eth_canonical_v1.mfe_mae_path
.env/bin/python -m experiments.eth_canonical_v1.monthly_compounding
.env/bin/python -m experiments.eth_canonical_v1.continuous_compounding
.env/bin/python -m experiments.eth_canonical_v1.manual_ratchet_compounding
.env/bin/python -m experiments.eth_canonical_v1.drop_rebound_mode_b
.env/bin/python -m experiments.eth_canonical_v1.drop_rebound_addon_quality
.env/bin/python -m experiments.eth_canonical_v1.drop_rebound_uptrend
.env/bin/python -m experiments.eth_canonical_v1.drop_rebound_uptrend_loosened
.env/bin/python -m experiments.eth_canonical_v1.drop_rebound_min_net_floor
.env/bin/python -m experiments.eth_canonical_v1.drop_rebound_giveback
.env/bin/python -m experiments.eth_canonical_v1.drop_rebound_higher_low
.env/bin/python -m experiments.eth_canonical_v1.drop_rebound_volatility
.env/bin/python -m experiments.eth_canonical_v1.drop_rebound_failed_bounce_exit
.env/bin/python -m experiments.eth_canonical_v1.drop_rebound_episode_limit
.env/bin/python -m pytest tests/test_eth_canonical_engine.py -q
```

Generated artifacts are written to `results/eth_canonical_v1/`. A run is accepted only if its full-window
metrics reproduce the frozen baseline in `config/experiments/eth_canonical_v1.json`.

Before running a new ETH rule, add it to `config/experiments/eth_research_registry_v1.csv` with
`status=frozen` and `preregistered=true`. After viewing results, update its status but never delete the row.
The August–September 2026 data is post-selection research data and cannot be used as unseen acceptance evidence.

The portfolio-risk command includes unchanged BTC, SOL and AAVE strategies only to measure ETH inside a shared
wallet. It does not tune or deploy those coins.
