# Concurrent Positions and Trade Size

## Purpose

This experiment jointly tested how many SOL spot positions may be open and how much of a $100 account to allocate to each entry. It replayed every completed primary and control signal chronologically with the frozen fees, slippage, stop, trail, and timeout rules. No leverage or borrowing was allowed.

## Grid

- Maximum simultaneous positions: 1, 2, 3, 4, or 5
- Fixed allocation: $10, $20, $25, $33.33, $50, or $100
- Equity allocation: 10%, 20%, 25%, 33.33%, 50%, or 100%
- Risk allocation: 0.5%, 1%, or 2% of account equity at the planned stop
- Earlier, later, and full-history samples were evaluated separately

## Selected Rule

The selected rule is **a maximum of two open positions with 25% of current equity per entry**. From $100, the first trade uses $25. If another valid signal arrives while that trade remains open, a second $25 lot may open. Further signals are ignored until a slot becomes available. Each lot keeps its own stop, trail, and 24-hour timer.

Across the full history, this setting opened 152 trades and finished at $108.35, a +8.35% result after costs. Book drawdown was -11.20%. Both independent periods were positive: +3.77% earlier and +4.41% later.

For comparison, one 25% position opened 82 trades and finished at $107.69 with -4.70% book drawdown. Two positions captured 70 additional entries and added $0.66 of final profit, while accepting materially higher drawdown.

## Why More Than Two Positions Were Rejected

With 25% equity per entry, three positions reduced the full-history return to +5.50% and increased book drawdown to -15.95%. Four positions returned only +2.61%, drew down -20.97%, and lost 0.26% in the earlier period.

The entries all buy SOL in the same direction, often close together. Additional positions stack the same market risk rather than diversify it.

## Validation and Limit

All 450 combinations passed cash and no-leverage checks. The one-position replay exactly matched the prior sizing result. Drawdown here uses cash plus entry cost for open lots; minute-by-minute unrealized gains and losses will be added in Stage 2 account tracking.
