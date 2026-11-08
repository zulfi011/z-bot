# Stage 1.5 Step 5 — Exit and Holding Time

## Frozen scope and execution

This step keeps the deduplicated episodes, first-touch and 30-minute bullish-candle entries, and Step 3 market context unchanged across all 81 configurations. It compares eight fixed holding periods, seven profit targets with a 24-hour cap, and four trailing exits activated at +2.5%. Every exit is tested without a stop and with the Step 4 4% stop candidate.

Time exits use the close of the final raw minute. Profit targets fill at the better of the target or a gap-up minute open. The 4% stop fills at the worse of its threshold or a gap-down minute open. A target and stop reached in the same minute use the stop result and remain marked ambiguous. Trailing begins only after the +2.5% activation minute closes and uses the peak from completed minutes, preventing intraminute high/low ordering from creating optimistic exits.

All returns are gross single-opportunity outcomes. Fees, slippage beyond gap handling, position overlap, sizing, and portfolio capital are not modeled.

## Reference fixed holding periods

| period | strategy | return_mean_pct | return_median_pct | expected_shortfall_10_pct | mean_change_vs_hold_pp | tail_change_vs_hold_pp | median_duration_minutes | profit_target_exit_pct | trailing_stop_exit_pct | protective_stop_exit_pct |
|---|---|---|---|---|---|---|---|---|---|---|
| all | time_15_no_stop | 0.0036 | 0.0076 | -0.7629 | -0.3328 | 6.1411 | 15.0000 | 0.0000 | 0.0000 | 0.0000 |
| all | time_15_stop_4 | 0.0020 | 0.0076 | -0.7791 | -0.3344 | 6.1249 | 15.0000 | 0.0000 | 0.0000 | 0.0873 |
| all | time_30_no_stop | 0.0013 | 0.0000 | -1.0545 | -0.3351 | 5.8495 | 30.0000 | 0.0000 | 0.0000 | 0.0000 |
| all | time_30_stop_4 | -0.0050 | 0.0000 | -1.0919 | -0.3414 | 5.8121 | 30.0000 | 0.0000 | 0.0000 | 0.1747 |
| all | time_60_no_stop | 0.0334 | 0.0067 | -1.4493 | -0.3030 | 5.4547 | 60.0000 | 0.0000 | 0.0000 | 0.0000 |
| all | time_60_stop_4 | 0.0186 | 0.0057 | -1.4894 | -0.3177 | 5.4146 | 60.0000 | 0.0000 | 0.0000 | 0.6987 |
| all | time_120_no_stop | 0.0250 | 0.0385 | -2.0837 | -0.3114 | 4.8203 | 120.0000 | 0.0000 | 0.0000 | 0.0000 |
| all | time_120_stop_4 | 0.0170 | 0.0342 | -2.0857 | -0.3193 | 4.8183 | 120.0000 | 0.0000 | 0.0000 | 1.1354 |
| all | time_240_no_stop | 0.0476 | 0.0756 | -2.9423 | -0.2888 | 3.9617 | 240.0000 | 0.0000 | 0.0000 | 0.0000 |
| all | time_240_stop_4 | 0.0492 | 0.0722 | -2.8324 | -0.2871 | 4.0717 | 240.0000 | 0.0000 | 0.0000 | 2.8821 |
| all | time_480_no_stop | 0.0716 | 0.1597 | -4.2054 | -0.2648 | 2.6986 | 480.0000 | 0.0000 | 0.0000 | 0.0000 |
| all | time_480_stop_4 | 0.0905 | 0.1540 | -3.7530 | -0.2459 | 3.1510 | 480.0000 | 0.0000 | 0.0000 | 7.5109 |
| all | time_720_no_stop | 0.1382 | 0.3075 | -5.0381 | -0.1982 | 1.8660 | 720.0000 | 0.0000 | 0.0000 | 0.0000 |
| all | time_720_stop_4 | 0.1686 | 0.2938 | -4.0000 | -0.1678 | 2.9040 | 720.0000 | 0.0000 | 0.0000 | 11.2664 |
| all | time_1440_no_stop | 0.3364 | 0.3749 | -6.9040 | 0.0000 | 0.0000 | 1440.0000 | 0.0000 | 0.0000 | 0.0000 |
| all | time_1440_stop_4 | 0.4232 | 0.2961 | -4.0000 | 0.0869 | 2.9040 | 1440.0000 | 0.0000 | 0.0000 | 22.1834 |
| earlier | time_15_no_stop | -0.0000 | 0.0021 | -0.8270 | -0.3545 | 6.6617 | 15.0000 | 0.0000 | 0.0000 | 0.0000 |
| earlier | time_15_stop_4 | -0.0033 | 0.0021 | -0.8596 | -0.3578 | 6.6291 | 15.0000 | 0.0000 | 0.0000 | 0.1761 |
| earlier | time_30_no_stop | 0.0005 | -0.0072 | -1.0561 | -0.3540 | 6.4326 | 30.0000 | 0.0000 | 0.0000 | 0.0000 |
| earlier | time_30_stop_4 | -0.0123 | -0.0081 | -1.1305 | -0.3667 | 6.3582 | 30.0000 | 0.0000 | 0.0000 | 0.3521 |
| earlier | time_60_no_stop | 0.0430 | -0.0305 | -1.3765 | -0.3115 | 6.1122 | 60.0000 | 0.0000 | 0.0000 | 0.0000 |
| earlier | time_60_stop_4 | 0.0115 | -0.0323 | -1.4741 | -0.3430 | 6.0146 | 60.0000 | 0.0000 | 0.0000 | 0.3521 |
| earlier | time_120_no_stop | -0.0054 | -0.0407 | -2.1751 | -0.3599 | 5.3135 | 120.0000 | 0.0000 | 0.0000 | 0.0000 |
| earlier | time_120_stop_4 | -0.0334 | -0.0417 | -2.2959 | -0.3878 | 5.1928 | 120.0000 | 0.0000 | 0.0000 | 1.2324 |
| earlier | time_240_no_stop | 0.0424 | 0.0185 | -2.9931 | -0.3120 | 4.4956 | 240.0000 | 0.0000 | 0.0000 | 0.0000 |
| earlier | time_240_stop_4 | 0.0193 | 0.0089 | -3.0317 | -0.3352 | 4.4570 | 240.0000 | 0.0000 | 0.0000 | 3.8732 |
| earlier | time_480_no_stop | 0.0154 | -0.0522 | -4.3506 | -0.3391 | 3.1381 | 480.0000 | 0.0000 | 0.0000 | 0.0000 |
| earlier | time_480_stop_4 | 0.0144 | -0.0591 | -3.8174 | -0.3400 | 3.6713 | 480.0000 | 0.0000 | 0.0000 | 7.9225 |
| earlier | time_720_no_stop | 0.1829 | 0.1851 | -5.5496 | -0.1715 | 1.9391 | 720.0000 | 0.0000 | 0.0000 | 0.0000 |
| earlier | time_720_stop_4 | 0.2205 | 0.1433 | -4.0000 | -0.1340 | 3.4887 | 720.0000 | 0.0000 | 0.0000 | 11.7958 |
| earlier | time_1440_no_stop | 0.3545 | 0.0857 | -7.4887 | 0.0000 | 0.0000 | 1440.0000 | 0.0000 | 0.0000 | 0.0000 |
| earlier | time_1440_stop_4 | 0.4624 | -0.0605 | -4.0000 | 0.1079 | 3.4887 | 1440.0000 | 0.0000 | 0.0000 | 24.4718 |
| later | time_15_no_stop | 0.0071 | 0.0122 | -0.6915 | -0.3114 | 5.5895 | 15.0000 | 0.0000 | 0.0000 | 0.0000 |
| later | time_15_stop_4 | 0.0071 | 0.0122 | -0.6915 | -0.3114 | 5.5895 | 15.0000 | 0.0000 | 0.0000 | 0.0000 |
| later | time_30_no_stop | 0.0021 | 0.0147 | -1.0402 | -0.3165 | 5.2408 | 30.0000 | 0.0000 | 0.0000 | 0.0000 |
| later | time_30_stop_4 | 0.0021 | 0.0147 | -1.0402 | -0.3165 | 5.2408 | 30.0000 | 0.0000 | 0.0000 | 0.0000 |
| later | time_60_no_stop | 0.0239 | 0.0258 | -1.5156 | -0.2946 | 4.7654 | 60.0000 | 0.0000 | 0.0000 | 0.0000 |
| later | time_60_stop_4 | 0.0257 | 0.0258 | -1.4986 | -0.2929 | 4.7824 | 60.0000 | 0.0000 | 0.0000 | 1.0399 |
| later | time_120_no_stop | 0.0549 | 0.0815 | -1.9672 | -0.2637 | 4.3138 | 120.0000 | 0.0000 | 0.0000 | 0.0000 |
| later | time_120_stop_4 | 0.0667 | 0.0815 | -1.8496 | -0.2519 | 4.4314 | 120.0000 | 0.0000 | 0.0000 | 1.0399 |
| later | time_240_no_stop | 0.0526 | 0.1394 | -2.8877 | -0.2660 | 3.3933 | 240.0000 | 0.0000 | 0.0000 | 0.0000 |
| later | time_240_stop_4 | 0.0787 | 0.1394 | -2.6279 | -0.2398 | 3.6531 | 240.0000 | 0.0000 | 0.0000 | 1.9064 |
| later | time_480_no_stop | 0.1269 | 0.2873 | -4.0592 | -0.1917 | 2.2218 | 480.0000 | 0.0000 | 0.0000 | 0.0000 |
| later | time_480_stop_4 | 0.1653 | 0.2873 | -3.6653 | -0.1533 | 2.6157 | 480.0000 | 0.0000 | 0.0000 | 7.1057 |
| later | time_720_no_stop | 0.0941 | 0.3506 | -4.5257 | -0.2245 | 1.7553 | 720.0000 | 0.0000 | 0.0000 | 0.0000 |
| later | time_720_stop_4 | 0.1175 | 0.3506 | -4.0000 | -0.2011 | 2.2810 | 720.0000 | 0.0000 | 0.0000 | 10.7452 |
| later | time_1440_no_stop | 0.3185 | 0.5125 | -6.2810 | 0.0000 | 0.0000 | 1440.0000 | 0.0000 | 0.0000 | 0.0000 |
| later | time_1440_stop_4 | 0.3847 | 0.5125 | -4.0000 | 0.0661 | 2.2810 | 1440.0000 | 0.0000 | 0.0000 | 19.9307 |

## Reference profit-target exits

| period | strategy | return_mean_pct | return_median_pct | expected_shortfall_10_pct | mean_change_vs_hold_pp | tail_change_vs_hold_pp | median_duration_minutes | profit_target_exit_pct | trailing_stop_exit_pct | protective_stop_exit_pct |
|---|---|---|---|---|---|---|---|---|---|---|
| all | target_1_no_stop | 0.1136 | 1.0000 | -4.7724 | -0.2228 | 2.1316 | 314.0000 | 76.4192 | 0.0000 | 0.0000 |
| all | target_1_stop_4 | 0.0797 | 1.0000 | -4.0000 | -0.2567 | 2.9040 | 277.0000 | 75.5459 | 0.0000 | 13.3624 |
| all | target_2_no_stop | 0.3165 | 2.0000 | -5.3062 | -0.0198 | 1.5978 | 923.0000 | 58.4279 | 0.0000 | 0.0000 |
| all | target_2_stop_4 | 0.2639 | 2.0000 | -4.0000 | -0.0725 | 2.9040 | 660.0000 | 57.4672 | 0.0000 | 17.2052 |
| all | target_2_5_no_stop | 0.3234 | 2.5000 | -5.8375 | -0.0129 | 1.0665 | 1422.0000 | 50.3930 | 0.0000 | 0.0000 |
| all | target_2_5_stop_4 | 0.3015 | 1.8197 | -4.0000 | -0.0349 | 2.9040 | 865.0000 | 49.3450 | 0.0000 | 18.9520 |
| all | target_3_no_stop | 0.3363 | 1.0542 | -5.9565 | -0.0000 | 0.9476 | 1440.0000 | 42.1834 | 0.0000 | 0.0000 |
| all | target_3_stop_4 | 0.3209 | 0.9572 | -4.0000 | -0.0154 | 2.9040 | 1066.0000 | 41.3974 | 0.0000 | 20.0873 |
| all | target_4_no_stop | 0.3583 | 0.6620 | -6.5014 | 0.0219 | 0.4026 | 1440.0000 | 30.3930 | 0.0000 | 0.0000 |
| all | target_4_stop_4 | 0.4021 | 0.5741 | -4.0000 | 0.0658 | 2.9040 | 1402.0000 | 30.2183 | 0.0000 | 21.4847 |
| all | target_5_no_stop | 0.3011 | 0.4454 | -6.9040 | -0.0353 | 0.0000 | 1440.0000 | 19.5633 | 0.0000 | 0.0000 |
| all | target_5_stop_4 | 0.3828 | 0.4198 | -4.0000 | 0.0465 | 2.9040 | 1440.0000 | 19.4760 | 0.0000 | 22.0961 |
| earlier | target_1_no_stop | 0.0941 | 1.0000 | -5.1245 | -0.2604 | 2.3642 | 260.0000 | 77.6408 | 0.0000 | 0.0000 |
| earlier | target_1_stop_4 | 0.0573 | 1.0000 | -4.0000 | -0.2972 | 3.4887 | 236.0000 | 76.0563 | 0.0000 | 14.6127 |
| earlier | target_2_no_stop | 0.2263 | 2.0000 | -5.7224 | -0.1282 | 1.7663 | 854.5000 | 60.7394 | 0.0000 | 0.0000 |
| earlier | target_2_stop_4 | 0.1656 | 2.0000 | -4.0000 | -0.1889 | 3.4887 | 634.0000 | 58.9789 | 0.0000 | 19.5423 |
| earlier | target_2_5_no_stop | 0.2981 | 2.5000 | -5.7378 | -0.0564 | 1.7508 | 1214.5000 | 54.2254 | 0.0000 | 0.0000 |
| earlier | target_2_5_stop_4 | 0.2102 | 2.5000 | -4.0000 | -0.1442 | 3.4887 | 764.5000 | 52.2887 | 0.0000 | 20.9507 |
| earlier | target_3_no_stop | 0.3279 | 1.3678 | -5.7420 | -0.0265 | 1.7466 | 1440.0000 | 45.5986 | 0.0000 | 0.0000 |
| earlier | target_3_stop_4 | 0.2369 | 0.9497 | -4.0000 | -0.1176 | 3.4887 | 983.5000 | 44.0141 | 0.0000 | 21.4789 |
| earlier | target_4_no_stop | 0.2186 | 0.2942 | -6.7123 | -0.1358 | 0.7764 | 1440.0000 | 31.3380 | 0.0000 | 0.0000 |
| earlier | target_4_stop_4 | 0.2412 | 0.1251 | -4.0000 | -0.1133 | 3.4887 | 1332.5000 | 30.9859 | 0.0000 | 23.2394 |
| earlier | target_5_no_stop | 0.1104 | 0.1201 | -7.4887 | -0.2440 | 0.0000 | 1440.0000 | 20.0704 | 0.0000 | 0.0000 |
| earlier | target_5_stop_4 | 0.2081 | -0.0125 | -4.0000 | -0.1464 | 3.4887 | 1440.0000 | 19.8944 | 0.0000 | 24.2958 |
| later | target_1_no_stop | 0.1328 | 1.0000 | -4.3998 | -0.1858 | 1.8812 | 376.0000 | 75.2166 | 0.0000 | 0.0000 |
| later | target_1_stop_4 | 0.1017 | 1.0000 | -4.0000 | -0.2169 | 2.2810 | 326.0000 | 75.0433 | 0.0000 | 12.1317 |
| later | target_2_no_stop | 0.4054 | 2.0000 | -4.7957 | 0.0868 | 1.4853 | 1051.0000 | 56.1525 | 0.0000 | 0.0000 |
| later | target_2_stop_4 | 0.3607 | 2.0000 | -4.0000 | 0.0421 | 2.2810 | 686.0000 | 55.9792 | 0.0000 | 14.9047 |
| later | target_2_5_no_stop | 0.3483 | 1.4484 | -5.8766 | 0.0298 | 0.4044 | 1440.0000 | 46.6205 | 0.0000 | 0.0000 |
| later | target_2_5_stop_4 | 0.3913 | 1.4323 | -4.0000 | 0.0727 | 2.2810 | 931.0000 | 46.4471 | 0.0000 | 16.9844 |
| later | target_3_no_stop | 0.3446 | 1.0264 | -6.1317 | 0.0261 | 0.1493 | 1440.0000 | 38.8215 | 0.0000 | 0.0000 |
| later | target_3_stop_4 | 0.4037 | 1.0264 | -4.0000 | 0.0851 | 2.2810 | 1169.0000 | 38.8215 | 0.0000 | 18.7175 |
| later | target_4_no_stop | 0.4957 | 0.8454 | -6.2618 | 0.1771 | 0.0192 | 1440.0000 | 29.4627 | 0.0000 | 0.0000 |
| later | target_4_stop_4 | 0.5606 | 0.8454 | -4.0000 | 0.2420 | 2.2810 | 1440.0000 | 29.4627 | 0.0000 | 19.7574 |
| later | target_5_no_stop | 0.4887 | 0.7326 | -6.2810 | 0.1702 | 0.0000 | 1440.0000 | 19.0641 | 0.0000 | 0.0000 |
| later | target_5_stop_4 | 0.5549 | 0.7326 | -4.0000 | 0.2363 | 2.2810 | 1440.0000 | 19.0641 | 0.0000 | 19.9307 |

## Reference +2.5%-activated trailing exits

| period | strategy | return_mean_pct | return_median_pct | expected_shortfall_10_pct | mean_change_vs_hold_pp | tail_change_vs_hold_pp | median_duration_minutes | profit_target_exit_pct | trailing_stop_exit_pct | protective_stop_exit_pct |
|---|---|---|---|---|---|---|---|---|---|---|
| all | trail_20_no_stop | 0.3104 | 1.9269 | -5.8375 | -0.0260 | 1.0665 | 1440.0000 | 0.0000 | 49.4323 | 0.0000 |
| all | trail_20_stop_4 | 0.2864 | 1.6375 | -4.0000 | -0.0499 | 2.9040 | 882.0000 | 0.0000 | 48.5590 | 18.9520 |
| all | trail_30_no_stop | 0.2689 | 1.7560 | -5.8375 | -0.0674 | 1.0665 | 1440.0000 | 0.0000 | 47.1616 | 0.0000 |
| all | trail_30_stop_4 | 0.2478 | 1.6375 | -4.0000 | -0.0886 | 2.9040 | 913.0000 | 0.0000 | 46.2882 | 18.9520 |
| all | trail_40_no_stop | 0.3334 | 1.5192 | -5.8375 | -0.0030 | 1.0665 | 1440.0000 | 0.0000 | 42.2707 | 0.0000 |
| all | trail_40_stop_4 | 0.3148 | 1.5053 | -4.0000 | -0.0215 | 2.9040 | 1075.0000 | 0.0000 | 41.3974 | 18.9520 |
| all | trail_50_no_stop | 0.3354 | 1.2849 | -5.8375 | -0.0010 | 1.0665 | 1440.0000 | 0.0000 | 37.6419 | 0.0000 |
| all | trail_50_stop_4 | 0.3197 | 1.2721 | -4.0000 | -0.0167 | 2.9040 | 1221.0000 | 0.0000 | 36.7686 | 18.9520 |
| earlier | trail_20_no_stop | 0.2944 | 2.0289 | -5.7378 | -0.0600 | 1.7508 | 1268.5000 | 0.0000 | 53.1690 | 0.0000 |
| earlier | trail_20_stop_4 | 0.2020 | 2.0185 | -4.0000 | -0.1524 | 3.4887 | 792.0000 | 0.0000 | 51.5845 | 20.9507 |
| earlier | trail_30_no_stop | 0.2162 | 1.7921 | -5.7378 | -0.1383 | 1.7508 | 1335.0000 | 0.0000 | 50.8803 | 0.0000 |
| earlier | trail_30_stop_4 | 0.1290 | 1.7724 | -4.0000 | -0.2255 | 3.4887 | 836.5000 | 0.0000 | 49.2958 | 20.9507 |
| earlier | trail_40_no_stop | 0.2924 | 1.5507 | -5.7378 | -0.0620 | 1.7508 | 1440.0000 | 0.0000 | 45.5986 | 0.0000 |
| earlier | trail_40_stop_4 | 0.2100 | 1.5252 | -4.0000 | -0.1445 | 3.4887 | 972.5000 | 0.0000 | 44.0141 | 20.9507 |
| earlier | trail_50_no_stop | 0.4075 | 1.3123 | -5.7378 | 0.0530 | 1.7508 | 1440.0000 | 0.0000 | 39.4366 | 0.0000 |
| earlier | trail_50_stop_4 | 0.3303 | 1.2872 | -4.0000 | -0.0242 | 3.4887 | 1137.5000 | 0.0000 | 37.8521 | 20.9507 |
| later | trail_20_no_stop | 0.3261 | 1.3305 | -5.8766 | 0.0076 | 0.4044 | 1440.0000 | 0.0000 | 45.7539 | 0.0000 |
| later | trail_20_stop_4 | 0.3695 | 1.3152 | -4.0000 | 0.0509 | 2.2810 | 952.0000 | 0.0000 | 45.5806 | 16.9844 |
| later | trail_30_no_stop | 0.3208 | 1.3305 | -5.8766 | 0.0023 | 0.4044 | 1440.0000 | 0.0000 | 43.5009 | 0.0000 |
| later | trail_30_stop_4 | 0.3647 | 1.3152 | -4.0000 | 0.0461 | 2.2810 | 1038.0000 | 0.0000 | 43.3276 | 16.9844 |
| later | trail_40_no_stop | 0.3737 | 1.3305 | -5.8766 | 0.0551 | 0.4044 | 1440.0000 | 0.0000 | 38.9948 | 0.0000 |
| later | trail_40_stop_4 | 0.4180 | 1.3152 | -4.0000 | 0.0995 | 2.2810 | 1239.0000 | 0.0000 | 38.8215 | 16.9844 |
| later | trail_50_no_stop | 0.2644 | 1.2578 | -5.8766 | -0.0541 | 0.4044 | 1440.0000 | 0.0000 | 35.8752 | 0.0000 |
| later | trail_50_stop_4 | 0.3093 | 1.2538 | -4.0000 | -0.0093 | 2.2810 | 1326.0000 | 0.0000 | 35.7019 | 16.9844 |

The comparison baseline is holding without a stop for 1,440 minutes. Expected shortfall is the mean of the worst 10% of outcomes. Positive tail change means the exit reduced those losses relative to the baseline.

## Cross-grid later-period evidence

| strategy | exit_family | configurations | configs_positive_mean | configs_mean_improved | configs_tail_improved | median_mean_change_vs_hold_pp | median_tail_change_vs_hold_pp | median_duration_minutes |
|---|---|---|---|---|---|---|---|---|
| target_5_no_stop | profit_target | 81 | 39 | 55 | 7 | 0.0244 | 0.0000 | 1440.0000 |
| trail_40_no_stop | trailing | 81 | 34 | 53 | 57 | 0.0337 | 0.0596 | 1440.0000 |
| time_240_stop_4 | fixed_time | 81 | 30 | 49 | 81 | 0.0626 | 2.9972 | 240.0000 |
| trail_40_stop_4 | trailing | 81 | 36 | 48 | 63 | 0.0252 | 1.5704 | 1440.0000 |
| target_5_stop_4 | profit_target | 81 | 38 | 48 | 63 | 0.0082 | 1.5704 | 1440.0000 |
| time_60_no_stop | fixed_time | 81 | 29 | 47 | 81 | 0.0742 | 4.1112 | 60.0000 |
| time_60_stop_4 | fixed_time | 81 | 31 | 47 | 81 | 0.0742 | 4.1102 | 60.0000 |
| time_120_stop_4 | fixed_time | 81 | 36 | 47 | 81 | 0.0662 | 3.5911 | 120.0000 |
| time_120_no_stop | fixed_time | 81 | 37 | 47 | 81 | 0.0631 | 3.5507 | 120.0000 |
| time_240_no_stop | fixed_time | 81 | 23 | 47 | 81 | 0.0496 | 2.8054 | 240.0000 |
| time_15_stop_4 | fixed_time | 81 | 36 | 46 | 81 | 0.0821 | 4.8693 | 15.0000 |
| time_30_stop_4 | fixed_time | 81 | 26 | 46 | 81 | 0.0775 | 4.5670 | 30.0000 |
| time_30_no_stop | fixed_time | 81 | 25 | 46 | 81 | 0.0757 | 4.5670 | 30.0000 |
| trail_20_no_stop | trailing | 81 | 35 | 46 | 57 | 0.0115 | 0.0596 | 1440.0000 |
| time_15_no_stop | fixed_time | 81 | 36 | 45 | 81 | 0.0821 | 4.8693 | 15.0000 |
| trail_30_no_stop | trailing | 81 | 35 | 45 | 57 | 0.0143 | 0.0596 | 1440.0000 |
| trail_50_no_stop | trailing | 81 | 34 | 44 | 57 | 0.0102 | 0.0596 | 1440.0000 |
| time_480_stop_4 | fixed_time | 81 | 29 | 43 | 81 | 0.0410 | 2.1296 | 480.0000 |
| trail_30_stop_4 | trailing | 81 | 35 | 43 | 63 | 0.0051 | 1.5704 | 1440.0000 |
| time_720_stop_4 | fixed_time | 81 | 25 | 41 | 81 | 0.0035 | 1.6396 | 720.0000 |

Configurations share episodes and price paths, so the grid count is a consistency check rather than 81 independent experiments.

## Stability screen

99 combinations pass the descriptive screen: at least 100 entries per period, positive mean and median in both periods, and improvement over the 24-hour hold in both mean and worst-decile outcome in both periods. The leading 15 by later-period mean improvement are shown.

| asset | timeframe | average_type | touch_zone | policy | segment | strategy | entries_earlier | entries_later | return_mean_pct_earlier | return_mean_pct_later | mean_change_vs_hold_pp_earlier | mean_change_vs_hold_pp_later | tail_change_vs_hold_pp_later | positive_block_ci_both |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETHUSDT | 5m | 7d | 1.5000 | bullish_candle_30m | bullish_regime | target_1_no_stop | 340 | 169 | 0.0328 | 0.3807 | 0.0034 | 0.6079 | 1.7731 | False |
| ETHUSDT | 5m | 7d | 1.5000 | first_touch_0m | bullish_regime | target_1_no_stop | 363 | 179 | 0.0298 | 0.3382 | 0.0326 | 0.5679 | 1.5401 | False |
| ETHUSDT | 5m | 7d | 1.5000 | bullish_candle_30m | bullish_regime | target_1_5_stop_4 | 340 | 169 | 0.0310 | 0.2824 | 0.0016 | 0.5096 | 0.8449 | False |
| ETHUSDT | 5m | 7d | 1.5000 | bullish_candle_30m | bullish_regime | target_1_5_no_stop | 340 | 169 | 0.0640 | 0.2759 | 0.0345 | 0.5031 | 0.7264 | False |
| ETHUSDT | 5m | 7d | 1.5000 | first_touch_0m | bullish_regime | target_1_5_stop_4 | 363 | 179 | 0.0039 | 0.2721 | 0.0066 | 0.5018 | 0.6962 | False |
| ETHUSDT | 5m | 7d | 1.5000 | first_touch_0m | bullish_regime | target_1_5_no_stop | 363 | 179 | 0.0788 | 0.2545 | 0.0816 | 0.4843 | 0.5218 | False |
| ETHUSDT | 3m | 7d | 1.5000 | first_touch_0m | bullish_regime | target_1_5_no_stop | 465 | 236 | 0.0047 | 0.3007 | 0.0041 | 0.3899 | 0.4929 | False |
| BTCUSDT | 1m | 30d | 1.5000 | first_touch_0m | bullish_regime | target_1_no_stop | 208 | 211 | 0.3369 | 0.4946 | 0.0008 | 0.3681 | 0.7068 | False |
| BTCUSDT | 1m | 30d | 1.5000 | bullish_candle_30m | bullish_regime | target_1_no_stop | 200 | 204 | 0.3604 | 0.4833 | 0.0348 | 0.3356 | 0.6891 | False |
| ETHUSDT | 3m | 15d | 0.5000 | bullish_candle_30m | all_entries | trail_50_stop_4 | 660 | 683 | 0.4535 | 0.3815 | 0.0252 | 0.2747 | 2.4949 | False |
| ETHUSDT | 5m | 7d | 1.5000 | bullish_candle_30m | bullish_regime | time_480_stop_4 | 340 | 169 | 0.1775 | 0.0393 | 0.1481 | 0.2665 | 1.8685 | False |
| ETHUSDT | 5m | 7d | 1.5000 | bullish_candle_30m | bullish_regime | time_120_no_stop | 340 | 169 | 0.0583 | 0.0266 | 0.0289 | 0.2538 | 2.9352 | False |
| ETHUSDT | 5m | 7d | 1.5000 | bullish_candle_30m | bullish_regime | time_480_no_stop | 340 | 169 | 0.1922 | 0.0258 | 0.1627 | 0.2530 | 1.7345 | False |
| ETHUSDT | 5m | 7d | 1.5000 | bullish_candle_30m | bullish_regime | time_120_stop_4 | 340 | 169 | 0.0509 | 0.0230 | 0.0215 | 0.2502 | 2.8991 | False |
| SOLUSDT | 5m | 15d | 1.0000 | first_touch_0m | all_entries | trail_50_stop_4 | 615 | 648 | 0.1963 | 0.1521 | 0.0037 | 0.2477 | 3.8002 | False |

0 screened combinations also have a positive exploratory seven-day block interval in both periods. Intervals are not adjusted for the many exit choices and do not establish an independent trading edge.

## Validation and preservation

The run evaluates 300,626 inherited episode-entry rows. Direct scalar replays independently verify fixed-time endpoints, target and stop ordering, gap fills, trailing activation, prior-peak trails, duration, and incomplete-window handling. Candidate identity, entry price, 24-hour baseline, nested time completeness, output round trips, and summary cardinality are also checked.

Before/after SHA-256 confirms 411 prior files are unchanged. All outputs are isolated under Step 5 paths.

## Step 5 decision

For SOL / 15D / 5m / ±0.5%, retain the 24-hour hold as the primary exit. No alternative passes the stability screen for this reference setup. Shorter fixed holds sharply reduce mean return. A +4% target with the 4% stop is strong later (+0.561% mean versus +0.319% holding) but weak earlier (+0.241% versus +0.354%). The 50% giveback trail without a stop shows the reverse: it improves earlier (+0.407% versus +0.354%) but falls behind later (+0.264% versus +0.319%). These reversals reject both as reference exit rules for now.

Keep the 4% stop with the 24-hour hold as a risk-control variant, not the primary exit: it raises reference mean in both periods and limits the worst observed outcomes, but its earlier median is slightly negative. In the bullish reference segment, the unchanged 24-hour hold without a stop remains strongest overall.

Other configurations are not discarded. ETH / 15D / ±0.5% with a +2.5%-activated 50% giveback trail and 4% stop passes the descriptive screen on 1m, 3m, and 5m data. On ETH 5m, mean return is +0.500% earlier and +0.310% later, versus +0.408% and +0.086% for holding. SOL / 15D / 5m / ±1.0% with the same exit also passes. Carry these as secondary candidates into final robustness testing.

Across the full study, 99 combinations pass the descriptive screen but none has a positive block interval in both periods. Therefore no refined exit is final, and the secondary candidates require dependence, cost, and sensitivity checks before Stage 2.

This run stops after exit and holding-time analysis. No final strategy selection or Stage 2 implementation is performed.

## Artifacts

`exit_summary.csv` contains all strategies, periods, and segments. `stability_screen.csv` and `cross_grid_effects.csv` contain robustness checks. Per-dataset Parquet files retain episode-level outcomes. `validation.csv` and `SUCCESS.json` record audit completion. Run `python -B -m src.research.stage15_exit.run` to reproduce into a new directory.
