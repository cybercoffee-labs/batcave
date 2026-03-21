# Small Report Analysis

## Report Comparison

**Small Report:** `2026-03-04_04-52-51.json` (172 lines, ~1.7KB)
**Normal Report:** `2026-03-04_22-20-20.json` (532 lines, ~16KB)

## Root Cause

The small report was generated during a data outage at **04:52 AM UTC**. All equities returned `status: "no_daily"` and all crypto requests failed with Binance API errors.

## Missing Fields in Small Report

### Equities Section
**Normal report has:**
- `px` (current price)
- `ret_1d` (1-day return)
- `ret_intra` (intraday return)
- `vol_z` (volatility z-score)
- `rvol` (relative volume)
- `dollar_vol` (dollar volume)
- `rv20_ann` (20-day realized volatility annualized)
- `status: "ok"` or `status: "ok_daily"`

**Small report has:**
- Only `symbol` and `status: "no_daily"`
- All other fields missing due to market being closed (pre-market hours)

### Crypto Section
**Normal report has:**
- Full metrics including prices, spreads, depths, volumes, etc.

**Small report has:**
- Only `error` messages for all crypto assets
- Binance API was unreachable or timing out

### Portfolio Section
**Normal report has:**
- Actual portfolio metrics and projections

**Small report has:**
- `status: "no_data"` (no portfolio calculated due to missing equity data)

### Stress Section
**Normal report has:**
- Non-zero `corr_stress` values
- Populated `top_edges` array with correlation pairs
- Valid `downside_corr_mean` values
- Non-zero `tail_points`
- Populated `downside_top_edges` array
- Populated `vol_shock` with actual statistics
- `regime` based on actual data (NORMAL, TENSION, STRESS, PANIC)

**Small report has:**
- `corr_stress: 0.0` (no data to correlate)
- Empty `top_edges: []`
- `downside_corr_mean: null`
- `tail_points: 0`
- Empty `downside_top_edges: []`
- `vol_shock` with all null values except `vol_z_gt2_pct: 0.0`
- `regime: "DATA_DEGRADED"` with `triggers: ["dq_breaker"]`
- `deltas` section present but based on previous valid data

### Flows Section
**Normal report has:**
- Flow scores for assets with valid data

**Small report has:**
- Empty `flows: {}`

### Narrative Section
Both reports have similar structure, but small report shows:
- `total_hits: 0`
- All keywords returning `null`
- Empty `samples: {}`

### Data Quality (dq) Section
**Normal report has:**
- `equities_ok_ratio: 0.95` (typically high)
- `crypto_ok_ratio: 1.0` (typically 100%)
- `overall_status: "ok"`
- `breaker_triggered: false`

**Small report has:**
- `equities_ok_ratio: 0.0` (0% success rate)
- `crypto_ok_ratio: 0.0` (0% success rate)
- `overall_status: "degraded"`
- `breaker_triggered: true`

### Meta Section
**Normal report has:**
- Higher `duration_sec` (more data processing)
- Non-zero `equities_ok` and `crypto_ok` counts
- Fewer or no errors

**Small report has:**
- `duration_sec: 1.053833` (very fast, no real work done)
- `equities_ok: 0`
- `crypto_ok: 0`
- `errors: 3` (all crypto failed)

## Summary

The small report is the result of the engine running during:
1. **Pre-market hours** (04:52 AM UTC = ~11:52 PM EST) when no equity daily data is available
2. **API outage** or network connectivity issues with Binance

When data quality breaker triggers (`overall_ratio < 0.60`), the engine:
- Sets `regime.label = "DATA_DEGRADED"`
- Adds `"dq_breaker"` to triggers
- Skips most calculations (portfolio, stress, flows)
- Generates minimal output report

This is expected behavior and not a bug. The engine correctly identifies and flags degraded data quality rather than producing unreliable analytics.
