# Stage 2 Step 11: Primary vs Control

## Purpose

This step compares the primary and control strategies in separate earlier and later periods. Each period restarts with $100. Every cost scenario rebuilds entry fills, exit thresholds, stops, trailing behavior, position selection, and account equity from raw one-minute candles.

Five execution assumptions were tested, from the frozen baseline of 10 bps fee and 2 bps slippage per side through a severe stress of 20 bps fee and 10 bps slippage per side.

## Key Results

| Costs per side | Strategy | Earlier return | Later return | Full return | Full profit factor |
|---|---|---:|---:|---:|---:|
| Baseline: 10 fee / 2 slippage | Primary | +3.76% | +4.41% | +8.33% | 1.18 |
| Baseline: 10 fee / 2 slippage | Control | +1.14% | +1.58% | +2.74% | 1.04 |
| Conservative: 15 fee / 5 slippage | Primary | +0.62% | +1.61% | +2.25% | 1.05 |
| Conservative: 15 fee / 5 slippage | Control | -2.91% | -1.89% | -4.74% | 0.93 |
| Severe: 20 fee / 10 slippage | Primary | -3.41% | -2.83% | -6.15% | 0.87 |
| Severe: 20 fee / 10 slippage | Control | -7.59% | -5.93% | -13.08% | 0.82 |

The primary produced a higher return than the control in all 15 matched comparisons: five cost scenarios across full, earlier, and later samples. Under baseline costs, it made $8.33 versus the control's $2.74 and had a smaller maximum drawdown: -12.16% versus -15.24%.

## Interpretation

The primary remained positive in both periods through the conservative 15/5 bps assumption. However, its conservative full-history profit fell to only $2.25 and its profit factor fell to 1.05, which is close to break-even. Both strategies failed the severe stress.

## Validation

Each scenario rebuilt 909 complete signal outcomes from raw candles; one data-end signal remained incomplete. The baseline exactly reproduced Step 9. Every run enforced two positions, 25% equity per entry, spot cash limits, and no leverage.

## Simple Explanation

Imagine increasing the cost of every purchase and sale. With normal costs, the primary changed $100 into $108.33. With conservative costs, it changed $100 into only $102.25. The control lost money under those same conservative costs.

The simple result is: **the primary is clearly better than the control and stayed profitable in both historical periods under reasonable conservative costs. Its remaining profit is small, and very high costs turn it into a losing strategy, so the edge is real in this test but fragile.**
