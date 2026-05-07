-- Batman Lab — PostgreSQL Schema v1.0
-- Run: psql batman_lab < database/schema.sql

-- ─────────────────────── OPPORTUNITIES ───────────────────────
CREATE TABLE IF NOT EXISTS opportunities (
    id SERIAL PRIMARY KEY,
    opp_id VARCHAR(30) UNIQUE NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cycle_id VARCHAR(16),  -- audit Section C #9: engine cycle correlation id
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

-- For installations created before audit Section C #9, add the column idempotently.
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS cycle_id VARCHAR(16);

CREATE INDEX IF NOT EXISTS idx_opps_ts ON opportunities(ts DESC);
CREATE INDEX IF NOT EXISTS idx_opps_scanner ON opportunities(scanner_type);
CREATE INDEX IF NOT EXISTS idx_opps_viable ON opportunities(viable) WHERE viable = TRUE;
CREATE INDEX IF NOT EXISTS idx_opps_asset ON opportunities(asset);
CREATE INDEX IF NOT EXISTS idx_opps_cycle_id ON opportunities(cycle_id);

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
    cycle_id VARCHAR(16),  -- audit Section C #9: matches opportunities.cycle_id
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

ALTER TABLE engine_runs ADD COLUMN IF NOT EXISTS cycle_id VARCHAR(16);

CREATE INDEX IF NOT EXISTS idx_engine_runs_ts ON engine_runs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_engine_runs_cycle_id ON engine_runs(cycle_id);

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

-- ─────────────────────── PORTFOLIO POSITIONS (Portfolio OS v1) ───────────────────────
-- Added: 2026-03-26
-- Single canonical table for all asset classes.
-- hodl_positions / venture_positions / portfolio_balances remain intact (read-only legacy).
-- Run migration: python tools/portfolio_migrate_legacy.py --dry-run

CREATE TABLE IF NOT EXISTS portfolio_positions (
    id                     SERIAL PRIMARY KEY,
    position_id            VARCHAR(50)   UNIQUE NOT NULL,
    -- Convention: PP-{TICKER}-{SOURCE}-{legacy_id:03d}
    -- e.g. PP-AAPL-GBM-001, PP-BTC-BINANCE-001, PP-CETES28D-CETESDIRECTO-001

    -- Two-level classification
    asset_class            VARCHAR(20)   NOT NULL
        CHECK (asset_class IN (
            'crypto', 'venture', 'equity', 'fund',
            'fixed_income', 'real_estate', 'cash', 'other'
        )),
    instrument_type        VARCHAR(30)   NOT NULL,
    -- Valid pairs enforced in Python layer (database/portfolio.py):
    --   crypto        → spot | staking | lp_token | defi
    --   venture       → pre_tge | early_token | presale | vested
    --   equity        → common_stock | adr | preferred_stock
    --   fund          → etf | index_fund | mutual_fund
    --   fixed_income  → cetes | government_bond | corporate_bond | sofipo | cd | money_market
    --   real_estate   → fibra | reit | direct
    --   cash          → checking | savings | stablecoin | wallet
    --   other         → commodity | collectible | structured | mixed

    -- Identity
    ticker                 VARCHAR(30)   NOT NULL,
    name                   VARCHAR(100),
    source                 VARCHAR(40)   NOT NULL,
    -- e.g. binance | gbm | web3_manual | nu | cetesdirecto | manual | broker

    -- Position size (always in native currency)
    quantity               DECIMAL(24,8) NOT NULL,
    native_currency        VARCHAR(5)    NOT NULL DEFAULT 'USD',

    -- Cost basis — native currency, supplied by caller, NEVER computed here
    -- Cash-like rule (asset_class = cash):
    --   quantity = balance, avg_entry_price_native = 1.0, cost_basis_native = quantity
    cost_basis_native      DECIMAL(18,4) NOT NULL,
    avg_entry_price_native DECIMAL(18,8),

    -- FX convention: 1 unit of native_currency = fx_rate_entry USD
    --   USD positions:  fx_rate_entry = 1.0  (exact, no approximation)
    --   MXN positions:  fx_rate_entry = 0.05  (~20 MXN/USD, approximated at entry)
    --   EUR positions:  fx_rate_entry = 1.08  (approximated at entry)
    fx_rate_entry          DECIMAL(14,8) NOT NULL DEFAULT 1.0,

    -- Current price and FX (native currency) — NULL until first external update
    current_price_native   DECIMAL(18,8),
    fx_rate_current        DECIMAL(14,8),

    -- Fixed income only — NULL for all other asset classes
    annual_yield_pct       DECIMAL(6,4),
    maturity_date          DATE,

    -- Lifecycle
    status                 VARCHAR(20)   NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'closed', 'exited')),
    notes                  TEXT,

    -- Flexible bag for per-class extra fields:
    -- crypto/venture: tp levels, stop_loss, chain, wallet, dexscreener
    -- legacy migration: {legacy_table, legacy_id}
    metadata               JSONB         NOT NULL DEFAULT '{}',

    created_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pp_asset_class     ON portfolio_positions(asset_class);
CREATE INDEX IF NOT EXISTS idx_pp_status          ON portfolio_positions(status)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_pp_ticker          ON portfolio_positions(ticker);
CREATE INDEX IF NOT EXISTS idx_pp_source          ON portfolio_positions(source);
CREATE INDEX IF NOT EXISTS idx_pp_instrument_type ON portfolio_positions(instrument_type);

-- ─────────────────────── PORTFOLIO VIEWS (v1) ───────────────────────

-- Full consolidated position list.
-- current_value_usd fallback hierarchy:
--   Tier 1: price known + fx_current known  → quantity × price × fx_current
--   Tier 2: no price   + fx_current known   → cost_basis_native × fx_current  (approximate)
--   Tier 3: no price,  no fx_current        → cost_basis_native × fx_entry    (entry cost floor)
CREATE OR REPLACE VIEW v_portfolio_consolidated AS
WITH valued AS (
    SELECT
        *,
        cost_basis_native * fx_rate_entry                                   AS cost_basis_usd,
        quantity * current_price_native                                      AS current_value_native,
        CASE
            WHEN current_price_native IS NOT NULL AND fx_rate_current IS NOT NULL
                THEN quantity * current_price_native * fx_rate_current
            WHEN current_price_native IS NULL AND fx_rate_current IS NOT NULL
                THEN cost_basis_native * fx_rate_current
            ELSE
                cost_basis_native * fx_rate_entry
        END                                                                  AS current_value_usd
    FROM portfolio_positions
    WHERE status = 'active'
),
portfolio_total AS (
    SELECT SUM(current_value_usd) AS total_usd FROM valued
)
SELECT
    v.position_id,
    v.asset_class,
    v.instrument_type,
    v.ticker,
    v.name,
    v.source,
    v.quantity,
    v.native_currency,
    v.cost_basis_native,
    ROUND(v.cost_basis_usd::DECIMAL, 2)                                      AS cost_basis_usd,
    v.avg_entry_price_native,
    v.current_price_native,
    v.fx_rate_entry,
    v.fx_rate_current,
    ROUND(v.current_value_native::DECIMAL, 4)                                AS current_value_native,
    ROUND(v.current_value_usd::DECIMAL, 2)                                   AS current_value_usd,
    ROUND((v.current_value_usd - v.cost_basis_usd)::DECIMAL, 2)             AS unrealized_pnl_usd,
    CASE WHEN v.cost_basis_usd > 0
        THEN ROUND(
            (v.current_value_usd - v.cost_basis_usd) / v.cost_basis_usd * 100,
        2)
        ELSE 0
    END                                                                      AS unrealized_pnl_pct,
    CASE WHEN t.total_usd > 0
        THEN ROUND(v.current_value_usd / t.total_usd * 100, 2)
        ELSE 0
    END                                                                      AS allocation_pct,
    v.annual_yield_pct,
    v.maturity_date,
    v.notes,
    v.metadata,
    v.updated_at
FROM valued v
CROSS JOIN portfolio_total t
ORDER BY v.current_value_usd DESC;

-- Allocation summary by asset class bucket.
CREATE OR REPLACE VIEW v_portfolio_by_class AS
WITH valued AS (
    SELECT
        asset_class,
        cost_basis_native * fx_rate_entry                                   AS cost_basis_usd,
        CASE
            WHEN current_price_native IS NOT NULL AND fx_rate_current IS NOT NULL
                THEN quantity * current_price_native * fx_rate_current
            WHEN current_price_native IS NULL AND fx_rate_current IS NOT NULL
                THEN cost_basis_native * fx_rate_current
            ELSE
                cost_basis_native * fx_rate_entry
        END                                                                  AS current_value_usd
    FROM portfolio_positions
    WHERE status = 'active'
),
portfolio_total AS (
    SELECT SUM(current_value_usd) AS total_usd FROM valued
)
SELECT
    v.asset_class,
    COUNT(*)                                                                  AS positions,
    ROUND(SUM(v.cost_basis_usd)::DECIMAL, 2)                                 AS total_cost_basis_usd,
    ROUND(SUM(v.current_value_usd)::DECIMAL, 2)                              AS total_current_value_usd,
    ROUND(SUM(v.current_value_usd - v.cost_basis_usd)::DECIMAL, 2)          AS total_unrealized_pnl_usd,
    ROUND(
        SUM(v.current_value_usd) / NULLIF(t.total_usd, 0) * 100,
    2)                                                                        AS allocation_pct
FROM valued v
CROSS JOIN portfolio_total t
GROUP BY v.asset_class, t.total_usd
ORDER BY total_current_value_usd DESC;

-- ─────────────────────── ASSETS ───────────────────────
-- Added: 2026-03-26
-- Minimal ticker registry. One row per unique instrument in portfolio_positions.
-- Populated automatically on upsert in database/portfolio.py.
-- Does NOT store prices (those live in portfolio_positions.current_price_native).

CREATE TABLE IF NOT EXISTS assets (
    id               SERIAL       PRIMARY KEY,
    ticker           VARCHAR(30)  UNIQUE NOT NULL,
    name             VARCHAR(100),
    asset_class      VARCHAR(20),          -- mirrors portfolio_positions.asset_class
    primary_exchange VARCHAR(40),          -- e.g. binance, gbm, cetesdirecto
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assets_asset_class ON assets(asset_class);

-- ─────────────────────── RISK SCORES ───────────────────────
-- Added: 2026-03-26
-- One row per engine cycle. Written by engine.py after COMMANDER gate.
-- Scores: 0.0–1.0 where 1.0 = best outcome (low risk / high quality).
--
-- 6-score framework:
--   operational_readiness    — dq_score × 0.6 + gordon_ok × 0.4
--   concentration_risk       — 1.0 − HHI (portfolio_positions)
--   technical_risk           — ALFRED dq_score (data reliability)
--   governance_risk          — GORDON gate result (1.0 = OK, 0.5 = ALERT, 0.0 = BLOCKED)
--   market_behavior          — regime-based (1.0 = NORMAL, 0.5 = STRESS, 0.1 = PANIC)
--   financial_attractiveness — equities/crypto data completeness ratio (proxy until scanner wiring)
--
-- composite_score: weighted average of available scores (weights defined in engine.py)

CREATE TABLE IF NOT EXISTS risk_scores (
    id                       SERIAL      PRIMARY KEY,
    ts                       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cycle_id                 VARCHAR(30),             -- ISO timestamp of the engine cycle

    -- 6-score framework
    operational_readiness    DECIMAL(5,4),
    concentration_risk       DECIMAL(5,4),
    technical_risk           DECIMAL(5,4),
    governance_risk          DECIMAL(5,4),
    market_behavior          DECIMAL(5,4),
    financial_attractiveness DECIMAL(5,4),

    composite_score          DECIMAL(5,4),

    -- Auditable inputs stored alongside scores
    dq_score                 DECIMAL(5,4),
    gordon_status            VARCHAR(10),
    regime_label             VARCHAR(30),
    viable_pct               DECIMAL(5,4),            -- reserved for future scanner wiring
    top_position_pct         DECIMAL(5,4),            -- largest single position share
    hhi                      DECIMAL(8,6),            -- Herfindahl-Hirschman Index

    metadata                 JSONB       NOT NULL DEFAULT '{}',
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_scores_ts ON risk_scores(ts DESC);
