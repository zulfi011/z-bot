# ETH overfitting-risk audit

## Verdict: NOT INDEPENDENTLY VALIDATED

The strategy remains profitable in the historical robustness checks, but the search history is too large and the genuinely new forward sample is currently empty. No new ETH rule should be promoted from these data alone.

## Search registry

- Registered research groups: **26**.
- Recorded raw rule evaluations: **1,238,087**.
- Registry fingerprint: `37a010bda268ac96dd4b0bf71b2424d9517cd56187cc32e0fe9df2b4272e03e1`.
- These are raw evaluations, not independent trials; many rules are closely related.

## Statistical diagnostics

- Six-block CSCV estimate: **0.0% PBO** across 20 symmetric splits.
- DSR sensitivity with only 32 assumed independent trials: **0.5%**.
- DSR sensitivity using all 475,200 historical grid rows as independent: **5.35e-21**.
- The DSR result is a sensitivity diagnostic, not a definitive estimate: there are only six return blocks and the real independent-trial count is unknown.
- The 0% CSCV estimate is also not proof against overfitting; six blocks give only 20 splits and all blocks have already influenced research.

## Contiguous-block uncertainty

| Method | 95% lower | Median | 95% upper |
|---|---:|---:|---:|
| Three-month blocks | $145.47 | $432.10 | $877.36 |
| Twelve-episode blocks | $153.02 | $434.76 | $861.20 |

Both intervals remain positive, which supports the existence of a historical edge. They do not erase selection bias.

## Parameter plateau

| Dimension | Profitable full | Profitable in both halves | Full-profit range |
|---|---:|---:|---:|
| stop_pct | 7/8 | 6/8 | $-7.88 to $134.05 |
| zone_pct | 4/5 | 3/5 | $-2.69 to $134.05 |
| average_days | 3/5 | 3/5 | $-33.37 to $134.05 |
| signal_minutes | 3/3 | 3/3 | $104.58 to $134.05 |
| activation_giveback_pair | 11/11 | 11/11 | $79.86 to $134.05 |

The result has useful neighbouring plateaus, but the selected zone width and activation/giveback pair sit at the tested boundary. Future searches must widen the range before treating the single best point as stable.

## Holdout and data status

- August 1–September 10, 2026 is now named **post-selection research data** and removed from acceptance gates.
- New forward months completed after the freeze: **0 of 3 required**.
- Earliest possible decision under the frozen rule: **2027-01-01**.
- Local clean minute history begins **2024-09-01**. No older prolonged ETH bear market is available locally.

## Decision

Keep the live strategy unchanged. Continue paper/live observation without tuning against the protected forward months. Do not accept another strategy change until at least three untouched full UTC months are available, and obtain older clean ETH minute history before claiming cross-cycle robustness.
