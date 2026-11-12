# ETH blocked-entry-hours revalidation

## Original baseline

**$430.16 profit · 459 trades · 85.4% headline wins · 71.0% economic winners · $-4.55 average loss · -9.66% drawdown**

## Fixed choices

| Entry-hours rule | Profit | Change | Trades | Headline wins | Economic wins | Avg loss | Drawdown | WF change | WF improved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| block_06_12 (control) | $430.16 | $+0.00 | 459 (+0) | 85.4% | 71.0% | $-4.55 | -9.66% | $+0.00 | 0/6 |
| all_hours | $429.77 | $-0.39 | 540 (+81) | 85.0% | 69.4% | $-4.50 | -9.65% | $-6.92 | 2/6 |
| block_12_18 | $413.13 | $-17.04 | 437 (-22) | 85.8% | 70.3% | $-4.49 | -11.85% | $-15.68 | 3/6 |
| block_00_06 | $362.30 | $-67.86 | 446 (-13) | 84.1% | 68.8% | $-4.49 | -7.81% | $-68.38 | 1/6 |
| block_18_24 | $339.74 | $-90.43 | 441 (-18) | 84.4% | 68.3% | $-4.46 | -9.20% | $-87.19 | 2/6 |

## Entry-time attribution with all hours enabled

| Entry UTC bucket | Trades | Profit | Win rate | Average P&L | Average loss |
|---|---:|---:|---:|---:|---:|
| 00-06 | 127 | $104.14 | 89.0% | $0.82 | $-4.59 |
| 06-12 | 133 | $44.20 | 83.5% | $0.33 | $-4.32 |
| 12-18 | 153 | $116.29 | 82.4% | $0.76 | $-4.53 |
| 18-24 | 127 | $165.14 | 85.8% | $1.30 | $-4.61 |

These outcomes are grouped by the hour the trade began. A later loss remains attributed to its original entry bucket.

## Six-month training selection

| Test window | Choice selected on prior 6 months | Training profit | Test profit | Current-block test | Change |
|---|---|---:|---:|---:|---:|
| wf0_test | all_hours | $28.30 | $240.66 | $236.69 | $+3.98 |
| wf1_test | all_hours | $254.69 | $67.51 | $47.57 | $+19.94 |
| wf2_test | all_hours | $305.90 | $-4.41 | $13.55 | $-17.96 |
| wf3_test | all_hours | $63.64 | $54.78 | $61.27 | $-6.49 |
| wf4_test | block_06_12 | $74.82 | $6.59 | $6.59 | $+0.00 |
| wf5_test | block_06_12 | $67.86 | $44.47 | $44.47 | $+0.00 |

The causal selector chose {"all_hours": 4, "block_06_12": 2}. Its combined test profit was **$409.60**, versus **$410.14** for always blocking 06–12 UTC, a change of **$-0.54**.

## Decision

**Keep the current 06–12 UTC block unless both the fixed comparisons and the causal selector support a replacement.** A block that wins only on full-history hindsight is historical noise, not a deployment candidate. The August–September 2026 period remains post-selection data and is excluded from acceptance.
