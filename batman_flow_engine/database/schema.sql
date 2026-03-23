-- Batman Lab — PostgreSQL Schema v1.0
-- Run: psql batman_lab < database/schema.sql

-- ─────────────────────── OPPORTUNITIES ───────────────────────
CREATE TABLE IF NOT EXISTS opportunities (
    id SERIAL PRIMARY KEY,
    opp_id VARCHAR(30) UNIQUE NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scanner_type CHAR(2) NOT NULL,
    scanner_id VARCHAR(30) NOT NULL,
    asset VARCHAR(10) NOT NULL DEFAULT 'USDT',
    market VARCHAR(10),
    venue VARCHAR(50),
    buy_price DECIMAL(18,8),
    sell_price DECIMAL(18,8),
    spot_price DECIMAL(18,8),
    gross_spread_pct DECIMAL(8,4),
    total_friction_pct DECIMAL(8,4),
    edge_net DECIMAL(8,4),
    viable BOOLEAN DEFAULT FALSE,
    depth_estimate DECIMAL(18,2),
    observe_only BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opps_ts ON opportunities(ts DESC);
CREATE INDEX IF NOT EXISTS idx_opps_scanner ON opportunities(scanner_type);
CREATE INDEX IF NOT EXISTS idx_opps_viable ON opportunities(viable) WHERE viable = TRUE;
CREATE INDEX IF NOT EXISTS idx_opps_asset ON opportunities(asset);

-- ─────────────────────── TRADES ───────────────────────
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(30) UNIQUE NOT NULL,
    agent VARCHAR(20) NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    opp_id VARCHAR(30),
    asset VARCHAR(10) NOT NULL,
    market VARCHAR(10),
    side VARCHAR(4) NOT NULL,
    price DECIMAL(18,8) NOT NULL,
    quantity DECIMAL(18,8) NOT NULL,
    fee DECIMAL(18,8) DEFAULT 0,
    pnl DECIMAL(18,8),
    status VARCHAR(20) DEFAULT 'executed',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trades_agent ON trades(agent);
CREATE INDEX IF NOT EXISTS idx_trades_ts ON trades(ts DESC);

-- ─────────────────────── HODL POSITIONS ───────────────────────
CREATE TABLE IF NOT EXISTS hodl_positions (
    id SERIAL PRIMARY KEY,
    token VARCHAR(10) NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    quantity DECIMAL(18,8) NOT NULL,
    avg_buy_price DECIMAL(18,8) NOT NULL,
    current_price DECIMAL(18,8),
    take_profit_1 DECIMAL(18,8),
    take_profit_2 DECIMAL(18,8),
    take_profit_3 DECIMAL(18,8),
    stop_loss DECIMAL(18,8),
    trailing_stop_pct DECIMAL(5,2) DEFAULT 15.0,
    peak_price DECIMAL(18,8),
    tp1_hit BOOLEAN DEFAULT FALSE,
    tp2_hit BOOLEAN DEFAULT FALSE,
    tp3_hit BOOLEAN DEFAULT FALSE,
    status VARCHAR(20) DEFAULT 'active',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hodl_status ON hodl_positions(status);

-- ─────────────────────── VENTURE POSITIONS ───────────────────────
CREATE TABLE IF NOT EXISTS venture_positions (
    id SERIAL PRIMARY KEY,
    token VARCHAR(20) NOT NULL,
    chain VARCHAR(20) NOT NULL,
    wallet_address VARCHAR(100),
    dexscreener_pair VARCHAR(100),
    quantity DECIMAL(24,8) NOT NULL,
    avg_buy_price DECIMAL(18,12),
    current_price DECIMAL(18,12),
    liquidity_usd DECIMAL(18,2),
    exit_2x BOOLEAN DEFAULT FALSE,
    exit_5x BOOLEAN DEFAULT FALSE,
    exit_10x BOOLEAN DEFAULT FALSE,
    status VARCHAR(20) DEFAULT 'active',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_venture_status ON venture_positions(status);

-- ─────────────────────── PORTFOLIO BALANCES ───────────────────────
CREATE TABLE IF NOT EXISTS portfolio_balances (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(30) NOT NULL,
    instrument VARCHAR(50) NOT NULL,
    balance DECIMAL(18,2) NOT NULL,
    currency VARCHAR(5) DEFAULT 'MXN',
    interest_rate DECIMAL(8,4),
    last_income DECIMAL(18,2),
    category VARCHAR(20) NOT NULL DEFAULT 'other',
    snapshot_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_date ON portfolio_balances(snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_platform ON portfolio_balances(platform);

-- ─────────────────────── SCANNER RUNS ───────────────────────
CREATE TABLE IF NOT EXISTS scanner_runs (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scanner_type CHAR(2) NOT NULL,
    scanner_name VARCHAR(50),
    duration_sec DECIMAL(8,2),
    opportunities_found INTEGER DEFAULT 0,
    viable_found INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'ok',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scanner_runs_ts ON scanner_runs(ts DESC);

-- ─────────────────────── ENGINE RUNS ───────────────────────
CREATE TABLE IF NOT EXISTS engine_runs (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_sec DECIMAL(8,2),
    equities_total INTEGER,
    equities_ok INTEGER,
    crypto_total INTEGER,
    crypto_ok INTEGER,
    regime VARCHAR(20),
    dq_score DECIMAL(5,4),
    corr_stress DECIMAL(5,4),
    errors INTEGER DEFAULT 0,
    full_report JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_engine_runs_ts ON engine_runs(ts DESC);

-- ─────────────────────── ALERTS ───────────────────────
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source VARCHAR(30) NOT NULL,
    severity VARCHAR(10) NOT NULL DEFAULT 'info',
    title VARCHAR(200) NOT NULL,
    message TEXT,
    acknowledged BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_ack ON alerts(acknowledged) WHERE acknowledged = FALSE;

-- ─────────────────────── VIEWS ───────────────────────

CREATE OR REPLACE VIEW v_viable_opportunities AS
SELECT opp_id, ts, scanner_type, asset, market, venue,
       buy_price, sell_price, edge_net, viable, depth_estimate, metadata
FROM opportunities
WHERE viable = TRUE AND ts > NOW() - INTERVAL '24 hours'
ORDER BY edge_net DESC;

CREATE OR REPLACE VIEW v_portfolio_overview AS
SELECT category, SUM(balance) as total_balance,
       COUNT(*) as instrument_count, AVG(interest_rate) as avg_rate
FROM portfolio_balances
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM portfolio_balances)
GROUP BY category ORDER BY total_balance DESC;

CREATE OR REPLACE VIEW v_daily_pnl AS
SELECT agent, DATE(ts) as trade_date, COUNT(*) as trade_count,
       SUM(pnl) as total_pnl, AVG(pnl) as avg_pnl
FROM trades WHERE pnl IS NOT NULL
GROUP BY agent, DATE(ts) ORDER BY trade_date DESC;

CREATE OR REPLACE VIEW v_scanner_performance AS
SELECT scanner_type, COUNT(*) as total_runs,
       AVG(duration_sec) as avg_duration,
       SUM(opportunities_found) as total_opps,
       SUM(viable_found) as total_viable, SUM(errors) as total_errors
FROM scanner_runs WHERE ts > NOW() - INTERVAL '7 days'
GROUP BY scanner_type ORDER BY total_viable DESC;

CREATE OR REPLACE VIEW v_hodl_alerts AS
SELECT token, exchange, quantity, avg_buy_price, current_price,
    ROUND(((current_price - avg_buy_price) / NULLIF(avg_buy_price, 0) * 100)::DECIMAL, 2) as unrealized_pnl_pct,
    take_profit_1, take_profit_2, take_profit_3, stop_loss,
    trailing_stop_pct, peak_price,
    CASE
        WHEN current_price IS NULL THEN 'NO_PRICE'
        WHEN current_price <= stop_loss THEN 'STOP_LOSS_HIT'
        WHEN peak_price > 0 AND current_price < peak_price * (1 - trailing_stop_pct/100) THEN 'TRAILING_STOP'
        WHEN current_price >= take_profit_3 AND NOT tp3_hit THEN 'TP3_HIT'
        WHEN current_price >= take_profit_2 AND NOT tp2_hit THEN 'TP2_HIT'
        WHEN current_price >= take_profit_1 AND NOT tp1_hit THEN 'TP1_HIT'
        ELSE 'HOLD'
    END as signal
FROM hodl_positions WHERE status = 'active';
