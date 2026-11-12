-- Z-Bot database schema: what `alembic upgrade head` builds on an empty database.
--
-- A new install runs this file once and is then marked as being at the migration named in BASELINE_REVISION
-- (migrations/env.py); later migrations, if any, run on top. Existing databases never run it: they upgrade through
-- migrations/history/ instead. tests/test_schema_baseline.py checks that both paths give exactly the same schema.
--
-- Generated from a database built by the migrations (pg_dump --schema-only), with session settings and comments removed.

CREATE TABLE account_snapshots (
    "timestamp" timestamp with time zone NOT NULL,
    open_position_value_usd numeric(20,8) NOT NULL,
    open_position_cost_usd numeric(20,8) NOT NULL,
    open_positions smallint NOT NULL,
    total_value_usd numeric(20,8) NOT NULL,
    realized_pnl_usd numeric(20,8) NOT NULL,
    unrealized_pnl_usd numeric(20,8) NOT NULL,
    strategy_pnl_usd numeric(20,8) NOT NULL,
    drawdown_pct numeric(16,8) NOT NULL,
    usdt_fees_usd numeric(20,8) NOT NULL,
    bnb_fees_usd numeric(20,8) NOT NULL,
    slippage_usd numeric(20,8) NOT NULL,
    coins jsonb DEFAULT '{}'::jsonb NOT NULL,
    usdt_free numeric(20,8) DEFAULT '0'::numeric NOT NULL,
    usdt_locked numeric(20,8) DEFAULT '0'::numeric NOT NULL,
    bnb_free numeric(28,12) DEFAULT '0'::numeric NOT NULL,
    bnb_value_usd numeric(20,8) DEFAULT '0'::numeric NOT NULL,
    allocated_usd numeric(20,8) DEFAULT '0'::numeric NOT NULL,
    wallet_value_usd numeric(20,8) DEFAULT '0'::numeric NOT NULL,
    trading_mode character varying(12) DEFAULT 'shadow'::character varying NOT NULL,
    fees_usd numeric(20,8) DEFAULT '0'::numeric NOT NULL
);

CREATE TABLE candles_1m (
    symbol character varying(24) NOT NULL,
    open_time timestamp with time zone NOT NULL,
    open numeric(24,10) NOT NULL,
    high numeric(24,10) NOT NULL,
    low numeric(24,10) NOT NULL,
    close numeric(24,10) NOT NULL,
    volume numeric(32,12) NOT NULL,
    source character varying(40) NOT NULL,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    close_time timestamp with time zone,
    quote_volume numeric(32,12),
    trade_count integer,
    source_event_time timestamp with time zone,
    CONSTRAINT ck_candles_ohlc CHECK (((low <= open) AND (low <= close) AND (high >= open) AND (high >= close))),
    CONSTRAINT ck_candles_positive CHECK (((open > (0)::numeric) AND (high > (0)::numeric) AND (low > (0)::numeric) AND (close > (0)::numeric))),
    CONSTRAINT ck_candles_quote_volume_nonnegative CHECK (((quote_volume IS NULL) OR (quote_volume >= (0)::numeric))),
    CONSTRAINT ck_candles_trade_count_nonnegative CHECK (((trade_count IS NULL) OR (trade_count >= 0))),
    CONSTRAINT ck_candles_volume_nonnegative CHECK ((volume >= (0)::numeric))
);

CREATE TABLE coin_allocations (
    symbol character varying(24) NOT NULL,
    revision integer DEFAULT 1 NOT NULL,
    request_id character varying(64),
    updated_at timestamp with time zone NOT NULL,
    trading_enabled boolean DEFAULT true NOT NULL,
    pullback_enabled boolean DEFAULT true NOT NULL,
    pyramid_enabled boolean DEFAULT false NOT NULL,
    dip_enabled boolean DEFAULT true NOT NULL,
    breakout_enabled boolean DEFAULT true NOT NULL
);

CREATE TABLE control_requests (
    request_id character varying(64) NOT NULL,
    kind character varying(24) NOT NULL,
    amount_usd numeric(20,8),
    position_id character varying(120),
    status character varying(16) NOT NULL,
    reason character varying(200),
    requested_at timestamp with time zone NOT NULL,
    processed_at timestamp with time zone,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    symbol character varying(24),
    CONSTRAINT ck_control_requests_kind CHECK (kind IN ('allocation', 'manual_buy', 'close_position', 'coin_pause', 'coin_resume', 'trading_mode')),
    CONSTRAINT ck_control_requests_status CHECK (status IN ('pending', 'applied', 'rejected'))
);

CREATE TABLE daily_averages (
    symbol character varying(24) NOT NULL,
    effective_at timestamp with time zone NOT NULL,
    completed_through date NOT NULL,
    average_7d numeric,
    average_15d numeric,
    average_30d numeric,
    calculated_at timestamp with time zone DEFAULT now() NOT NULL,
    signal_average_days smallint,
    signal_average numeric(24,12)
);

CREATE TABLE engine_state (
    key character varying(100) NOT NULL,
    value jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE exchange_events (
    id bigint NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    symbol character varying(24) NOT NULL,
    action character varying(32) NOT NULL,
    position_id character varying(120),
    client_order_id character varying(64),
    exchange_order_id character varying(64),
    request jsonb DEFAULT '{}'::jsonb NOT NULL,
    response jsonb DEFAULT '{}'::jsonb NOT NULL,
    ok boolean DEFAULT true NOT NULL
);

CREATE SEQUENCE exchange_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE exchange_events_id_seq OWNED BY exchange_events.id;

CREATE TABLE execution_observations (
    id bigint NOT NULL,
    symbol character varying(24) NOT NULL,
    position_id character varying(120),
    side character varying(8) NOT NULL,
    status character varying(32) NOT NULL,
    decision_at timestamp with time zone,
    requested_at timestamp with time zone,
    completed_at timestamp with time zone,
    best_bid numeric(24,10),
    best_ask numeric(24,10),
    expected_next_open numeric(24,10),
    actual_average_fill numeric(24,10),
    order_latency_ms numeric(20,3),
    fee_asset character varying(16),
    fee_usd numeric(20,8),
    fee_rate_bps numeric(16,6),
    price_impact_bps numeric(16,6),
    next_open_slippage_bps numeric(16,6),
    exchange_order_id character varying(64),
    client_order_id character varying(64),
    recovered_retry boolean DEFAULT false NOT NULL,
    rejection_reason text,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_execution_observations_side CHECK (side IN ('buy', 'sell'))
);

CREATE SEQUENCE execution_observations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE execution_observations_id_seq OWNED BY execution_observations.id;

CREATE TABLE monitoring_alerts (
    alert_key character varying(100) NOT NULL,
    severity character varying(16) NOT NULL,
    status character varying(16) NOT NULL,
    title character varying(160) NOT NULL,
    message text NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone,
    CONSTRAINT ck_alert_severity CHECK (severity IN ('info', 'warning', 'critical')),
    CONSTRAINT ck_alert_status CHECK (status IN ('active', 'resolved'))
);

CREATE TABLE orders (
    order_id character varying(140) NOT NULL,
    position_id character varying(120) NOT NULL,
    side character varying(8) NOT NULL,
    status character varying(16) NOT NULL,
    requested_at timestamp with time zone NOT NULL,
    raw_price numeric(24,10) NOT NULL,
    fill_price numeric(24,10) NOT NULL,
    quantity numeric(28,12) NOT NULL,
    notional_usd numeric(20,8) NOT NULL,
    fee_usd numeric(20,8) NOT NULL,
    fee_asset character varying(8) NOT NULL,
    fee_bnb numeric(28,12) DEFAULT '0'::numeric NOT NULL,
    slippage_usd numeric(20,8) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    exchange_order_id character varying(64),
    client_order_id character varying(64),
    order_type character varying(24),
    fee_asset_quantity numeric(28,12)
);

CREATE TABLE positions (
    position_id character varying(120) NOT NULL,
    signal_id character varying(120),
    entry_source character varying(16) NOT NULL,
    lot_number smallint NOT NULL,
    status character varying(16) NOT NULL,
    entry_time timestamp with time zone NOT NULL,
    raw_entry_price numeric(24,10) NOT NULL,
    entry_fill_price numeric(24,10) NOT NULL,
    quantity numeric(28,12) NOT NULL,
    allocation_usd numeric(20,8) NOT NULL,
    entry_fee_usd numeric(20,8) NOT NULL,
    entry_fee_asset character varying(8) NOT NULL,
    entry_fee_bnb numeric(28,12) DEFAULT '0'::numeric NOT NULL,
    bars_held integer DEFAULT 0 NOT NULL,
    trailing_active boolean DEFAULT false NOT NULL,
    peak_price numeric(24,10),
    exit_time timestamp with time zone,
    raw_exit_price numeric(24,10),
    exit_fill_price numeric(24,10),
    exit_fee_usd numeric(20,8),
    exit_fee_asset character varying(8),
    exit_fee_bnb numeric(28,12),
    exit_cash_usd numeric(20,8),
    exit_reason character varying(40),
    realized_pnl_usd numeric(20,8),
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    trailing_started_at timestamp with time zone,
    symbol character varying(24) NOT NULL,
    entry_order_id character varying(64),
    stop_order_id character varying(64),
    stop_price numeric(24,10),
    exit_order_id character varying(64),
    quantity_sold numeric(28,12),
    trend_exit_active boolean DEFAULT false NOT NULL,
    trend_exit_pending boolean DEFAULT false NOT NULL,
    parent_position_id character varying(120),
    CONSTRAINT ck_positions_positive CHECK (((quantity > (0)::numeric) AND (allocation_usd > (0)::numeric))),
    CONSTRAINT ck_positions_status CHECK (status IN ('open', 'closed'))
);

CREATE TABLE signals (
    signal_id character varying(120) NOT NULL,
    episode_id character varying(120) NOT NULL,
    strategy_id character varying(80) NOT NULL,
    signal_time timestamp with time zone NOT NULL,
    entry_time timestamp with time zone,
    status character varying(40) NOT NULL,
    reason character varying(100),
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE system_events (
    id bigint NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    level character varying(16) NOT NULL,
    component character varying(40) NOT NULL,
    event_type character varying(80) NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL
);

ALTER TABLE system_events ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME system_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE touch_episodes (
    episode_id character varying(120) NOT NULL,
    strategy_id character varying(80) NOT NULL,
    symbol character varying(24) NOT NULL,
    touch_time timestamp with time zone NOT NULL,
    average_value numeric(24,12) NOT NULL,
    status character varying(40) NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE trades (
    trade_id character varying(140) NOT NULL,
    position_id character varying(120) NOT NULL,
    entry_source character varying(16) NOT NULL,
    entry_time timestamp with time zone NOT NULL,
    exit_time timestamp with time zone NOT NULL,
    quantity numeric(28,12) NOT NULL,
    allocation_usd numeric(20,8) NOT NULL,
    entry_fill_price numeric(24,10) NOT NULL,
    exit_fill_price numeric(24,10) NOT NULL,
    entry_fee_usd numeric(20,8) NOT NULL,
    exit_fee_usd numeric(20,8) NOT NULL,
    bnb_fees_usd numeric(20,8) NOT NULL,
    slippage_usd numeric(20,8) NOT NULL,
    exit_reason character varying(40) NOT NULL,
    duration_minutes integer NOT NULL,
    net_return_pct numeric(16,8) NOT NULL,
    net_pnl_usd numeric(20,8) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    symbol character varying(24) NOT NULL,
    exit_mode character varying(10)
);

ALTER TABLE ONLY exchange_events ALTER COLUMN id SET DEFAULT nextval('exchange_events_id_seq'::regclass);

ALTER TABLE ONLY execution_observations ALTER COLUMN id SET DEFAULT nextval('execution_observations_id_seq'::regclass);

ALTER TABLE ONLY account_snapshots
    ADD CONSTRAINT account_snapshots_pkey PRIMARY KEY ("timestamp");

ALTER TABLE ONLY candles_1m
    ADD CONSTRAINT candles_1m_pkey PRIMARY KEY (symbol, open_time);

ALTER TABLE ONLY coin_allocations
    ADD CONSTRAINT coin_allocations_pkey PRIMARY KEY (symbol);

ALTER TABLE ONLY control_requests
    ADD CONSTRAINT control_requests_pkey PRIMARY KEY (request_id);

ALTER TABLE ONLY daily_averages
    ADD CONSTRAINT daily_averages_pkey PRIMARY KEY (symbol, effective_at);

ALTER TABLE ONLY engine_state
    ADD CONSTRAINT engine_state_pkey PRIMARY KEY (key);

ALTER TABLE ONLY exchange_events
    ADD CONSTRAINT exchange_events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY execution_observations
    ADD CONSTRAINT execution_observations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY monitoring_alerts
    ADD CONSTRAINT monitoring_alerts_pkey PRIMARY KEY (alert_key);

ALTER TABLE ONLY orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (order_id);

ALTER TABLE ONLY positions
    ADD CONSTRAINT positions_pkey PRIMARY KEY (position_id);

ALTER TABLE ONLY positions
    ADD CONSTRAINT positions_signal_id_key UNIQUE (signal_id);

ALTER TABLE ONLY signals
    ADD CONSTRAINT signals_episode_id_key UNIQUE (episode_id);

ALTER TABLE ONLY signals
    ADD CONSTRAINT signals_pkey PRIMARY KEY (signal_id);

ALTER TABLE ONLY system_events
    ADD CONSTRAINT system_events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY touch_episodes
    ADD CONSTRAINT touch_episodes_pkey PRIMARY KEY (episode_id);

ALTER TABLE ONLY trades
    ADD CONSTRAINT trades_pkey PRIMARY KEY (trade_id);

ALTER TABLE ONLY trades
    ADD CONSTRAINT trades_position_id_key UNIQUE (position_id);

ALTER TABLE ONLY orders
    ADD CONSTRAINT uq_orders_position_side UNIQUE (position_id, side);

CREATE INDEX ix_candles_1m_open_time ON candles_1m USING btree (open_time);

CREATE INDEX ix_control_requests_status ON control_requests USING btree (status, requested_at);

CREATE INDEX ix_exchange_events_timestamp ON exchange_events USING btree ("timestamp");

CREATE INDEX ix_execution_observations_client_order ON execution_observations USING btree (client_order_id);

CREATE INDEX ix_execution_observations_symbol_completed ON execution_observations USING btree (symbol, completed_at);

CREATE INDEX ix_monitoring_alerts_status ON monitoring_alerts USING btree (status, severity);

CREATE UNIQUE INDEX ix_orders_client_order_id ON orders USING btree (client_order_id) WHERE (client_order_id IS NOT NULL);

CREATE INDEX ix_positions_parent ON positions USING btree (parent_position_id);

CREATE INDEX ix_positions_symbol_status ON positions USING btree (symbol, status);

CREATE INDEX ix_signals_entry_time ON signals USING btree (entry_time);

CREATE INDEX ix_system_events_timestamp ON system_events USING btree ("timestamp");

CREATE INDEX ix_touch_episodes_touch_time ON touch_episodes USING btree (touch_time);

CREATE INDEX ix_trades_exit_time ON trades USING btree (exit_time);

ALTER TABLE ONLY orders
    ADD CONSTRAINT orders_position_id_fkey FOREIGN KEY (position_id) REFERENCES positions(position_id);

ALTER TABLE ONLY positions
    ADD CONSTRAINT positions_signal_id_fkey FOREIGN KEY (signal_id) REFERENCES signals(signal_id);

ALTER TABLE ONLY signals
    ADD CONSTRAINT signals_episode_id_fkey FOREIGN KEY (episode_id) REFERENCES touch_episodes(episode_id);

ALTER TABLE ONLY trades
    ADD CONSTRAINT trades_position_id_fkey FOREIGN KEY (position_id) REFERENCES positions(position_id);
