# ETH canonical baseline v1

This is an ETH-only local research control. It does not connect to Binance, a server, or the live database.

## Acceptance

**PASS** — the canonical engine reproduced the frozen ETH-v5 control inside the configured tolerance.

| Metric | Result |
|---|---:|
| Trades | 459 |
| Won / lost | 392 / 67 |
| Win rate | 85.40% |
| Net profit | $430.1634 |
| Average win | $1.8751 |
| Average loss | $-4.5505 |
| Profit factor | 2.411 |
| Hourly mark-to-market drawdown | -9.6622% |
| Candidate signals | 606 |
| Blocked candidates | 147 |

## Entry-family contribution

| source | trades | wins | win_rate_pct | net_profit | average_win | average_loss |
|---|---|---|---|---|---|---|
| breakout | 45 | 39 | 86.6667 | 30.7869 | 1.3531 | -3.6639 |
| dip | 309 | 266 | 86.0841 | 213.9092 | 1.5522 | -4.6275 |
| pullback | 105 | 87 | 82.8571 | 185.4674 | 3.0964 | -4.6622 |

## Evaluation windows

| window | initial_capital | ending_equity | net_profit | return_pct | trades | wins | losses | win_rate_pct | average_win | average_loss | profit_factor | maximum_drawdown_pct | maximum_drawdown_usd | blocked_candidates | endpoint_closed_trades | candidate_count | ending_wallet |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| full | 500.0000 | 930.1634 | 430.1634 | 86.0327 | 459 | 392 | 67 | 85.4031 | 1.8751 | -4.5505 | 2.4109 | -9.6622 | -48.6618 | 147 | 1 | 606 | 930.1634 |
| earlier | 500.0000 | 795.9341 | 295.9341 | 59.1868 | 247 | 203 | 44 | 82.1862 | 2.4223 | -4.4499 | 2.5114 | -9.6622 | -48.6618 | 86 | 3 | 333 | 795.9341 |
| later | 500.0000 | 641.5753 | 141.5753 | 28.3151 | 212 | 189 | 23 | 89.1509 | 1.2874 | -4.4237 | 2.3915 | -6.8207 | -43.3374 | 61 | 1 | 273 | 641.5753 |
| post_selection_2026_08_09 | 500.0000 | 515.5186 | 15.5186 | 3.1037 | 47 | 41 | 6 | 87.2340 | 0.6554 | -1.8919 | 2.3671 | -3.8111 | -19.9628 | 36 | 0 | 83 | 515.5186 |
| wf0_test | 500.0000 | 736.6882 | 236.6882 | 47.3376 | 72 | 65 | 7 | 90.2778 | 4.0930 | -4.1941 | 9.0619 | -5.0059 | -31.2379 | 31 | 1 | 103 | 736.6882 |
| wf1_test | 500.0000 | 547.5731 | 47.5731 | 9.5146 | 76 | 65 | 11 | 85.5263 | 1.5055 | -4.5715 | 1.9460 | -6.4893 | -36.6533 | 15 | 0 | 91 | 547.5731 |
| wf2_test | 500.0000 | 513.5517 | 13.5517 | 2.7103 | 42 | 37 | 5 | 88.0952 | 0.9693 | -4.4626 | 1.6074 | -3.9607 | -20.2426 | 1 | 0 | 43 | 513.5517 |
| wf3_test | 500.0000 | 561.2689 | 61.2689 | 12.2538 | 53 | 48 | 5 | 90.5660 | 1.7205 | -4.2629 | 3.8745 | -4.6122 | -26.7111 | 9 | 0 | 62 | 561.2689 |
| wf4_test | 500.0000 | 506.5940 | 6.5940 | 1.3188 | 62 | 51 | 11 | 82.2581 | 1.1153 | -4.5715 | 1.1311 | -7.0237 | -38.2697 | 48 | 0 | 110 | 506.5940 |
| wf5_test | 500.0000 | 544.4673 | 44.4673 | 8.8935 | 36 | 35 | 1 | 97.2222 | 1.3610 | -3.1692 | 15.0311 | -1.2262 | -6.7557 | 3 | 1 | 39 | 544.4673 |

## Rules enforced by this engine

- Complete shared-wallet replay; no editing of an old trade ledger.
- Stable same-minute ordering.
- Trades are truncated and liquidated at the last completed minute of each evaluation window.
- Hourly mark-to-market equity includes unrealized P&L.
- Every candidate rejected for slot or cash constraints is logged.
- All future ETH experiments must compare against this unchanged control.

Configuration: `eth_canonical_v1`.
