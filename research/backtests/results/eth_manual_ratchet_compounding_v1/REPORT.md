# ETH manual upward-ratchet compounding replay

## Result

| sizing | profit | ending_equity | return_pct | trades | average_order | minimum_order | maximum_order | average_loss | drawdown_pct | drawdown_usd | profit_to_drawdown |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed_$100_control | 430.1634 | 930.1634 | 86.0327 | 459 | 99.6178 | 67.7100 | 100.0000 | -4.5505 | -9.6622 | -48.6618 | 8.8399 |
| manual_upward_ratchet | 561.2216 | 1061.2216 | 112.2443 | 459 | 147.0309 | 67.7100 | 200.0000 | -6.3723 | -9.6622 | -86.1818 | 6.5121 |

## Exact model tested

- Start with a **$500 ETH pot** and five **$100** configured lots.
- Once marked ETH-pot equity first reaches $600, the simulated manual setting becomes **5 × $120**. At $700 it becomes **5 × $140**, then continues in $100 / $20 steps.
- The configured size **never falls** after a loss.
- Each actual entry uses the lesser of that configured size and the actual free shared cash. Thus, after closed losses leave only $80 once four lots are funded, the fifth order is $80.
- Existing open lots are never resized. No leverage or borrowing is allowed.

The ratchet produced **$131.06** more full-period profit, improved **1/6** walk-forward test windows, and changed the combined walk-forward result by **$12.81**.

There were **9** filled entries that used the smaller shared-cash remainder rather than the configured lot. Their smallest order was **$67.71**.

This is a sizing comparison, not proof of a stronger entry/exit strategy. The key decision measure is whether the additional profit justifies the larger absolute drawdown.
