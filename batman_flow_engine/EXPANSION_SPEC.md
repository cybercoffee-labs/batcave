# BATMAN LAB — EXPANSION SPEC v1.0
# Multi-Exchange, Multi-Strategy Arbitrage Intelligence System
# Date: 2026-03-17
# Author: Claude.ai (architecture) + Erick Posselt (vision)
#
# THIS FILE IS THE BLUEPRINT. Read it completely before writing ANY code.
# Each task is self-contained and can be assigned to Claude Code, Codex, or Ollama.

---

## 0. CONTEXT — READ FIRST

Batman Lab is a financial intelligence system at `~/Projects/batcave/`.
Two repos:
- `batman_flow_engine/` — the brain (scans markets, detects opportunities)
- `nightwing_agent/` — the executor (evaluates and acts on opportunities)

**Current state:** Only scans Binance P2P for USDT/MXN spot-vs-P2P edge (~0.3-0.5%).
**Target state:** Multi-exchange, multi-strategy arbitrage observatory covering 25+ strategies.

**CRITICAL RULES:**
1. Read `CLAUDE.md` in the repo BEFORE touching code.
2. All new files go in `batman_flow_engine/` unless explicitly stated otherwise.
3. Run `pwd` first — if you're not in `~/Projects/batcave/batman_flow_engine/`, stop.
4. All scanners write to `storage/logs/opportunities.jsonl` (append-only, same format).
5. No secrets in code — API keys go in `.env` only.
6. Every new module needs tests in `tests/`.
7. Batman naming convention is NON-NEGOTIABLE (Alfred, Gordon, Harvey, etc.).

---

## 1. NEW EXCHANGE CONNECTORS

### Task 1.1: OKX Spot Price Connector
**Assign to:** Claude Code
**File:** `core/exchange_okx.py`
**API:** `https://www.okx.com/api/v5/market/ticker?instId={PAIR}`
**Pairs:** BTC-USDT, ETH-USDT, SOL-USDT, USDT-MXN (if available)
**Functions:**
```python
def fetch_okx_price(pair: str) -> dict:
    """Returns {"price": float, "bid": float, "ask": float, "volume_24h": float, "ts": str}"""

def fetch_okx_funding_rate(pair: str) -> dict:
    """Returns {"funding_rate": float, "next_funding_time": str, "ts": str}"""
```
**Test file:** `tests/test_exchange_okx.py` (mock HTTP responses)
**No API key needed** — public endpoints only.

### Task 1.2: Bybit Spot + Funding Rate Connector
**Assign to:** Claude Code
**File:** `core/exchange_bybit.py`
**API:** `https://api.bybit.com/v5/market/tickers?category=spot&symbol={PAIR}`
**Funding:** `https://api.bybit.com/v5/market/funding/history?category=linear&symbol={PAIR}`
**Pairs:** BTCUSDT, ETHUSDT, SOLUSDT
**Functions:**
```python
def fetch_bybit_price(pair: str) -> dict:
def fetch_bybit_funding_rate(pair: str) -> dict:
```
**Test file:** `tests/test_exchange_bybit.py`

### Task 1.3: Bitso (Mexico) Connector
**Assign to:** Claude Code
**File:** `core/exchange_bitso.py`
**API:** `https://api.bitso.com/v3/ticker/?book={PAIR}`
**Pairs:** btc_mxn, eth_mxn, usdt_mxn
**Functions:**
```python
def fetch_bitso_price(pair: str) -> dict:
    """Returns {"price": float, "bid": float, "ask": float, "volume_24h": float, "ts": str}"""

def fetch_bitso_order_book(pair: str, limit: int = 20) -> dict:
    """Returns {"bids": [...], "asks": [...]}"""
```
**Why Bitso matters:** Mexican exchange, SPEI with zero commission, regulated by CNBV.
**Test file:** `tests/test_exchange_bitso.py`

### Task 1.4: KuCoin Spot Connector
**Assign to:** Claude Code
**File:** `core/exchange_kucoin.py`
**API:** `https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={PAIR}`
**Pairs:** BTC-USDT, ETH-USDT, SOL-USDT
**Test file:** `tests/test_exchange_kucoin.py`

### Task 1.5: MEXC Spot Connector
**Assign to:** Codex (low priority)
**File:** `core/exchange_mexc.py`
**API:** `https://api.mexc.com/api/v3/ticker/price?symbol={PAIR}`
**Pairs:** BTCUSDT, ETHUSDT, SOLUSDT

---

## 2. NEW SCANNERS

### Task 2.1: Scanner D — Multi-Exchange Price Scanner
**Assign to:** Claude Code
**File:** `core/scanner_multi_exchange.py`
**Purpose:** Compare same asset across ALL connected exchanges simultaneously.
**Logic:**
```
For each asset (BTC, ETH, SOL, USDT):
    Fetch price from: Binance, OKX, Bybit, Bitso, KuCoin, MEXC
    Find: lowest ask, highest bid
    Calculate: spread_pct = (highest_bid - lowest_ask) / lowest_ask * 100
    If spread_pct > threshold (0.1%):
        Log opportunity with type="D", scanner_id="D-MULTI-EXCHANGE"
        Include: buy_exchange, sell_exchange, buy_price, sell_price, spread_pct
```
**Output format** (append to opportunities.jsonl):
```json
{
    "opp_id": "OPP-D-XXXXXXXX",
    "ts": "2026-03-17T...",
    "type": "D",
    "scanner_id": "D-MULTI-EXCHANGE",
    "asset": "BTC",
    "buy_exchange": "bitso",
    "sell_exchange": "binance",
    "buy_price": 74500.00,
    "sell_price": 74800.00,
    "spread_pct": 0.40,
    "estimated_fees_pct": 0.20,
    "edge_net": 0.20,
    "viable": true,
    "observe_only": true
}
```
**Test file:** `tests/test_scanner_multi_exchange.py`

### Task 2.2: Scanner E — Funding Rate Arbitrage Scanner
**Assign to:** Claude Code
**File:** `core/scanner_funding_rate.py`
**Purpose:** Monitor funding rates across Binance, OKX, Bybit. Alert when rates are high.
**Logic:**
```
For each asset (BTC, ETH, SOL):
    Fetch funding rate from: Binance, OKX, Bybit
    If any rate > 0.01% (per 8h = ~1.3% APY annualized):
        Log opportunity with type="E", scanner_id="E-FUNDING-RATE"
    Also compare rates BETWEEN exchanges:
        If spread between highest and lowest > 0.005%:
            Log cross-exchange funding arbitrage opportunity
```
**Output format:**
```json
{
    "opp_id": "OPP-E-XXXXXXXX",
    "ts": "...",
    "type": "E",
    "scanner_id": "E-FUNDING-RATE",
    "asset": "BTC",
    "exchange": "bybit",
    "funding_rate": 0.015,
    "annualized_pct": 19.71,
    "next_funding": "2026-03-17T16:00:00Z",
    "cross_exchange_spread": 0.008,
    "observe_only": true
}
```
**Binance Funding API:** `https://fapi.binance.com/fapi/v1/fundingRate?symbol={PAIR}&limit=1`
**Test file:** `tests/test_scanner_funding_rate.py`

### Task 2.3: Scanner F — P2P Cross-Currency Premium Scanner
**Assign to:** Claude Code
**File:** `core/scanner_p2p_cross_currency.py`
**Purpose:** Compare P2P premiums between MXN, ARS, COP, VES simultaneously.
**Logic:**
```
For each fiat (MXN, ARS, COP, VES):
    Get P2P buy/sell prices from Binance P2P (already in p2p_latam.py)
    Get official FX rate (already using open.er-api.com)
    Calculate premium_pct for each country

Compare premiums:
    If premium_ARS - premium_MXN > 1.0%:
        Log cross-currency opportunity: "Buy USDT with MXN, sell for ARS"
    Same for all pairs
```
**Output format:**
```json
{
    "opp_id": "OPP-F-XXXXXXXX",
    "ts": "...",
    "type": "F",
    "scanner_id": "F-P2P-CROSS-CURRENCY",
    "buy_fiat": "MXN",
    "sell_fiat": "ARS",
    "buy_premium_pct": 0.5,
    "sell_premium_pct": 3.2,
    "cross_premium_spread": 2.7,
    "estimated_transfer_cost_pct": 1.0,
    "edge_net": 1.7,
    "viable": true,
    "route": "MXN→USDT(Binance P2P)→USDT→ARS(Binance P2P)",
    "observe_only": true
}
```
**Test file:** `tests/test_scanner_p2p_cross_currency.py`

### Task 2.4: Scanner G — P2P Merchant Spread Scanner
**Assign to:** Claude Code
**File:** `core/scanner_p2p_merchant.py`
**Purpose:** Find the buy/sell spread on Binance P2P for merchant strategy.
**Logic:**
```
For each fiat (MXN, ARS):
    Fetch top 5 BUY ads (people wanting to buy USDT = you SELL to them)
    Fetch top 5 SELL ads (people selling USDT = you BUY from them)
    Calculate: merchant_spread = best_buy_ad_price - best_sell_ad_price
    If merchant_spread_pct > 0.5%:
        Log opportunity: "Post BUY ad at X, SELL ad at Y, earn spread"
```
**This is strategy #1 from the research — the most profitable for small capital.**
**Test file:** `tests/test_scanner_p2p_merchant.py`

### Task 2.5: Scanner H — Stablecoin Depeg Scanner
**Assign to:** Codex
**File:** `core/scanner_stablecoin_depeg.py`
**Purpose:** Monitor USDT, USDC, DAI prices across exchanges. Alert on depeg events.
**Logic:**
```
For each stablecoin (USDT, USDC, DAI):
    Fetch price from Binance, OKX, Bybit, Bitso
    If any price < 0.995 or > 1.005:
        Log depeg opportunity
    If spread between exchanges > 0.2%:
        Log cross-exchange stablecoin arbitrage
```
**Test file:** `tests/test_scanner_stablecoin_depeg.py`

---

## 3. BATMAN ENGINE INTEGRATION

### Task 3.1: Register New Scanners in Engine
**Assign to:** Claude Code
**File:** Modify `engine.py`
**Logic:** Add Scanner D, E, F, G, H to the engine cycle. Each runs after existing A, B, C.
**Config:** Add new thresholds to `config.yaml`:
```yaml
thresholds:
  # Existing
  min_spread_pct_A: 0.05
  min_basis_pct_B: 0.02
  min_edge_pct_C: 0.20
  # New
  min_spread_pct_D: 0.10      # Multi-exchange minimum spread
  min_funding_rate_E: 0.01     # Funding rate per 8h minimum
  min_cross_currency_F: 1.0    # Cross-currency premium spread minimum
  min_merchant_spread_G: 0.5   # P2P merchant buy-sell spread minimum
  min_depeg_H: 0.2             # Stablecoin depeg minimum
```

### Task 3.2: Update Opportunity Types in HARVEY
**Assign to:** Claude Code
**File:** Modify `core/harvey.py` (batman side)
**Logic:** HARVEY already stores in SQLite. Just ensure new types D, E, F, G, H are accepted.

---

## 4. NIGHTWING EXPANSION

### Task 4.1: Multi-Strategy Bridge
**Assign to:** Claude Code (AFTER Batman scanners are done)
**File:** Modify `nightwing_agent/core/batman_bridge.py`
**Logic:** Currently only reads type="C" records. Expand to read ALL types (A-H).
**New function:**
```python
def fetch_best_opportunity(fiats: list = ["MXN"]) -> dict:
    """Read latest opportunities of ALL types, return the one with highest edge_net."""
```

### Task 4.2: Strategy Router
**Assign to:** Claude Code
**File:** `nightwing_agent/core/strategy_router.py`
**Purpose:** Route each opportunity type to the correct execution path.
```python
STRATEGY_MAP = {
    "A": "cross_exchange",      # Alert: buy on X, sell on Y
    "B": "basis_trade",         # Alert: spot vs futures
    "C": "p2p_spot_arb",       # Current strategy
    "D": "multi_exchange",      # Alert: buy on X, sell on Y
    "E": "funding_rate",        # Alert: open funding rate position
    "F": "cross_currency_p2p",  # Alert: buy with MXN, sell for ARS
    "G": "p2p_merchant",        # Alert: post buy/sell ads at these prices
    "H": "stablecoin_depeg",    # Alert: buy depeg stablecoin
}
```

---

## 5. OLLAMA / BARBARA ENHANCEMENT

### Task 5.1: Opportunity Analyzer
**Assign to:** Claude Code (calls Ollama)
**File:** Modify `core/ollama_intel.py`
**New function:**
```python
def analyze_opportunity(opp: dict) -> dict:
    """
    Send opportunity data to Ollama for natural language analysis.
    Returns: {"risk_assessment": str, "recommendation": str, "confidence": float}
    """
```
**Prompt template:**
```
You are a crypto arbitrage analyst. Analyze this opportunity:
Type: {type}, Edge: {edge_net}%, Exchange: {exchange}, Asset: {asset}
What is the risk level? Should we act? Confidence 0-1?
Respond in JSON only.
```

---

## 6. DASHBOARDS & MONITORING

### Task 6.1: Multi-Strategy Dashboard
**Assign to:** Codex
**File:** `tools/multi_strategy_dashboard.py`
**Purpose:** CLI dashboard showing ALL opportunity types, last 24h stats.
**Output:**
```
╔══════════════════════════════════════════════════════════════╗
║              BATMAN LAB — MULTI-STRATEGY MONITOR             ║
╠══════════════════════════════════════════════════════════════╣
║  Scanner A (Cross-Exchange):    3 opps | avg edge +0.15%    ║
║  Scanner B (Basis):             1 opp  | avg edge +0.08%    ║
║  Scanner C (P2P Spot):          8 opps | avg edge +0.55%    ║
║  Scanner D (Multi-Exchange):    5 opps | avg edge +0.22%    ║
║  Scanner E (Funding Rate):      2 opps | avg rate 12% APY   ║
║  Scanner F (Cross-Currency):    1 opp  | edge +2.7%         ║
║  Scanner G (Merchant Spread):   4 opps | avg spread 1.8%    ║
║  Scanner H (Stablecoin Depeg):  0 opps | no depeg detected  ║
╠══════════════════════════════════════════════════════════════╣
║  BEST OPPORTUNITY NOW:                                       ║
║  Scanner F: Buy USDT with MXN, sell for ARS — edge +2.7%   ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 7. PRIORITY ORDER

**Phase 1 (TODAY — Claude Code):**
1. Task 1.3: Bitso connector (most important — Mexican exchange)
2. Task 1.1: OKX connector
3. Task 1.2: Bybit connector (+ funding rates)
4. Task 2.1: Scanner D (multi-exchange)
5. Task 2.2: Scanner E (funding rate)

**Phase 2 (TOMORROW — Claude Code):**
6. Task 2.3: Scanner F (cross-currency P2P)
7. Task 2.4: Scanner G (merchant spread)
8. Task 3.1: Register in engine
9. Task 4.1: Multi-strategy bridge
10. Task 4.2: Strategy router

**Phase 3 (Codex + Ollama):**
11. Task 1.4: KuCoin connector
12. Task 1.5: MEXC connector
13. Task 2.5: Scanner H (stablecoin depeg)
14. Task 5.1: Ollama analyzer
15. Task 6.1: Dashboard

---

## 8. TESTING REQUIREMENTS

Every module needs:
- At least 5 tests
- Mock all HTTP calls (no real API calls in tests)
- Test error handling (timeouts, malformed responses, API down)
- Test with `python -m pytest tests/ -v` from repo root

---

## 9. FILE NAMING CONVENTION

```
core/exchange_{name}.py      — exchange connector
core/scanner_{name}.py       — market scanner
tests/test_exchange_{name}.py — connector tests
tests/test_scanner_{name}.py  — scanner tests
```

---

## 10. HOW TO USE THIS SPEC

**For Claude Code:**
```
cd ~/Projects/batcave/batman_flow_engine
cat CLAUDE.md                    # Read master context
cat EXPANSION_SPEC.md            # Read this spec
# Then execute tasks in Phase 1 order
```

**For Codex:**
```
Same repo, same spec. Focus on Phase 3 tasks only.
```

**For Ollama/BARBARA:**
```
Already running at localhost:11434
Claude Code creates the integration module (Task 5.1)
```

---

*Created: 2026-03-17 | Batman Lab Expansion — from single-pair to multi-strategy observatory*
