SELECT symbol, side, status, decision_at, best_bid, best_ask, expected_next_open,
       actual_average_fill, order_latency_ms, fee_asset, fee_rate_bps,
       price_impact_bps, next_open_slippage_bps, client_order_id,
       exchange_order_id, recovered_retry, rejection_reason
FROM execution_observations
WHERE symbol = 'ETHUSDT'
ORDER BY COALESCE(completed_at, decision_at), id;
