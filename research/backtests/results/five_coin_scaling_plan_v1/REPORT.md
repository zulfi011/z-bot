# Five-coin shared-pot scaling plan (local only)

## Model

One $300 wallet is shared by ETH, TRX, BTC, AAVE and SOL. It begins with three $100 slots. At each $100 marked-equity high-water milestone it unlocks a further $100 slot until cap N. After N, the post-slot share says what fraction of each further $100 profit is distributed evenly across N requested lots: 100% means 5 slots go from $100 to $120 after the next $100 profit; at 6 slots it becomes $116.67. Actual spend always uses remaining free cash when it is smaller.

The grid tested N=3…10 and post-slot distribution shares of 0%, 50%, 75%, and 100%. Plans are ranked by positive walk-forward periods, then combined walk-forward profit, then profit/drawdown.

## Selected robust plan

**3_slots_share_100pct**: $902.55 profit, 822 trades, 82.6% win rate, -15.23% maximum drawdown, and $397.89 combined walk-forward profit across 6/6 positive windows.

Baseline (stay at 3×$100): $461.32 profit, -12.10% drawdown, $388.46 walk-forward profit.

The full matrix is in `all_plans.csv`; this is research only and does not modify the live bot.
