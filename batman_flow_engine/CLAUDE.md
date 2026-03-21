# BATMAN LAB — MASTER CONTEXT FILE
# Read this file COMPLETELY before touching any code.
# This is the single source of truth for the entire system.

---

## 1. SYSTEM IDENTITY

**Project Name:** Batman Lab
**Type:** Financial Intelligence Laboratory + Gated Execution System
**Mode:** OBSERVE-ONLY by default. LIVE execution requires explicit human approval gate.
**Philosophy:** Intelligence first. Execution is the consequence of reliable intelligence — never the starting point.
**Tests:** Batman 228 passing, Nightwing 155 passing (383 total)
**Level:** L1 operational, accumulating PAPER data toward L2

**Core Principle:**
> Understand how money moves before moving money.

---

## 2. REPOSITORY STRUCTURE

Both repos live inside `~/Projects/batcave/`:

### BATMAN (`~/Projects/batcave/batman_flow_engine/`)
The central intelligence brain. Observes markets, detects inefficiencies, produces research signals.
**Role:** WHY and WHEN — detect, analyze, justify.

### NIGHTWING (`~/Projects/batcave/nightwing_agent/`)
The first operational agent. P2P LATAM execution when authorized.
**Role:** HOW — execute, record, control.
**Status:** PAPER mode operational. LIVE blocked by default.

**CRITICAL:** Do NOT confuse paths. There may be legacy references to `~/Downloads/batman_p2p_agent` or `~/Projects/nightwing_agent/` — those are WRONG. The correct paths are above.

---

## 3. TEAM STRUCTURE (NON-NEGOTIABLE NAMES)

| Name | Character | Role | Repo | Status |
|------|-----------|------|------|--------|
| ALFRED | Alfred Pennyworth | ORACLE — Data ingestion, quality | batman_flow_engine | ✅ 100% (dq_score=1.0) |
| BATCOMPUTER | The Bat-Computer | SIGNAL — Market inefficiency detection | batman_flow_engine | ✅ 70% |
| BARBARA | Barbara Gordon | NARRATIVE — Macro, geopolitics, news | batman_flow_engine | ✅ Active (Ollama llama3.2:3b) |
| LUCIUS | Lucius Fox | ATLAS — Compliance, jurisdiction | nightwing_agent | ✅ Active (MXN/ARS on, COP/VES off) |
| GORDON | Commissioner Gordon | SHIELD — Security, kill switch | Both repos | ✅ Batman: scaffolding. Nightwing: 4 protections active (25 tests) |
| HARVEY | Harvey Dent | LEDGER — P&L, accounting | Both repos | ✅ Batman: signals SQLite. Nightwing: trade ledger JSONL (18 tests) |
| COMMANDER | Batman | COMMANDER — Orchestration | batman_flow_engine | 🟡 40% — gates not fully connected |

**Operational Agents (Robins):**

| Name | Character | Specialty | Repo | Status |
|------|-----------|-----------|------|--------|
| NIGHTWING | Dick Grayson | P2P LATAM arbitrage | nightwing_agent | ✅ PAPER mode, 126 tests, auto-pause, dedup |
| RED HOOD | Jason Todd | Spot trading cross-exchange | Not built | ❌ |
| RED ROBIN | Tim Drake | Basis, funding rates, derivatives | Not built | ❌ |
| ROBIN | Damian Wayne | Macro, ETFs, commodities | Not built | ❌ |

---

## 4. ARCHITECTURAL ORDER (STRICT — DO NOT CHANGE)

```
1. ALFRED (ORACLE)      — data must be clean before anything else
2. BATCOMPUTER (SIGNAL) — signals only from verified data
3. GORDON (SHIELD)      — security before decisions
   HARVEY (LEDGER)      — parallel to SHIELD, required before any live execution
4. LUCIUS (ATLAS)       — compliance before execution
5. COMMANDER            — decides only when 1-4 are ready
6. NIGHTWING            — executes after intelligence validates
7. BARBARA (NARRATIVE)  — enrichment layer, not core dependency
```

---

## 5. FILE STRUCTURE — BATMAN (`batman_flow_engine/`)

```
batman_flow_engine/
├── engine.py                  — main engine orchestrator
├── runner.py                  — single-cycle runner with reporting
├── app.py                     — Streamlit dashboard (port 8502)
├── config.yaml                — thresholds and configuration
├── CLAUDE.md                  — THIS FILE (master context)
├── core/
│   ├── alfred.py              — ALFRED: data quality module ✅
│   ├── correlations.py        — correlation stress detection
│   ├── crypto.py              — crypto price fetcher
│   ├── database.py            — SQLite database helpers
│   ├── economic_graph.py      — economic flow graph (read-only) ✅
│   ├── equities.py            — equity price fetcher (yfinance)
│   ├── flows.py               — flow analysis
│   ├── gordon.py              — GORDON: security/health (scaffolding)
│   ├── gordon_integration.py  — GORDON integration helpers
│   ├── harvey.py              — HARVEY: signal storage in SQLite ✅
│   ├── lucius.py              — LUCIUS reference (compliance rules)
│   ├── news_intel.py          — news intelligence fetcher
│   ├── observatory.py         — system telemetry/observability ✅
│   ├── ollama_intel.py        — BARBARA: Ollama llama3.2:3b ✅
│   ├── p2p_latam.py           — P2P LATAM data fetcher ✅
│   ├── portfolio.py           — portfolio simulation
│   ├── scanner_basis.py       — Scanner B: spot vs futures basis
│   ├── scanner_cross_exchange.py — Scanner A: cross-exchange spreads
│   ├── scanner_multi_exchange.py — Scanner D: multi-exchange spreads ✅
│   ├── scanner_funding_rate.py — Scanner E: funding rate arbitrage ✅
│   ├── scanner_p2p_cross_currency.py — Scanner F: cross-currency P2P ✅
│   ├── scanner_p2p_merchant.py — Scanner G: merchant spread ✅
│   ├── scanner_stablecoin_depeg.py — Scanner H: stablecoin depeg ✅
│   ├── exchange_bitso.py      — Bitso exchange connector ✅
│   ├── exchange_bybit.py      — Bybit exchange connector ✅
│   ├── exchange_kucoin.py     — KuCoin exchange connector ✅
│   ├── exchange_mexc.py       — MEXC exchange connector ✅
│   ├── exchange_okx.py        — OKX exchange connector ✅
│   ├── signals.py             — signal scoring and ranking
│   └── utils.py               — shared utilities
├── tools/
│   ├── architecture_status.py — CLI/JSON/dashboard ✅
│   ├── make_daily_summary.py  — daily summary table
│   ├── multi_strategy_dashboard.py — multi-scanner dashboard ✅
│   ├── research_metrics.py    — structural market analysis ✅
│   ├── run_loop.py            — automatic loop (every 20 min)
│   └── system_health.py       — system health checker
├── tests/                     — 228 tests total
│   ├── test_graph_engine.py   ✅
│   ├── test_lucius.py         ✅
│   ├── test_observatory.py    ✅
│   ├── test_observatory_metrics.py ✅
│   ├── test_p2p_latam.py      ✅
│   ├── test_exchange_bitso.py ✅
│   ├── test_exchange_bybit.py ✅
│   ├── test_exchange_kucoin.py ✅
│   ├── test_exchange_mexc.py  ✅
│   ├── test_exchange_okx.py   ✅
│   ├── test_scanner_funding_rate.py ✅
│   ├── test_scanner_multi_exchange.py ✅
│   ├── test_scanner_p2p_cross_currency.py ✅
│   ├── test_scanner_p2p_merchant.py ✅
│   ├── test_scanner_stablecoin_depeg.py ✅
│   └── test_ollama_opportunity.py ✅
└── storage/
    ├── batman.db              — SQLite (614+ signals)
    ├── latest.json            — latest engine cycle snapshot
    ├── prev.json / alerts.json
    ├── logs/
    │   ├── opportunities.jsonl — all detected opportunities (append-only)
    │   ├── data_quality.jsonl  — ALFRED quality reports
    │   ├── audit.log / engine.out / engine.err / loop.log
    │   └── session_fixes.txt
    └── reports/                — JSON reports per cycle
```

---

## 6. FILE STRUCTURE — NIGHTWING (`nightwing_agent/`)

```
nightwing_agent/
├── agent.py                   — main loop (auto-pause + dedup + GORDON)
├── alerts.py / dashboard.py / scheduler.py
├── core/
│   ├── batman_bridge.py       — reads from Batman ✅ (14 tests)
│   ├── gordon.py              — GORDON: 4 protections ✅ (25 tests)
│   ├── harvey.py              — HARVEY: trade ledger ✅ (18 tests)
│   ├── lucius.py              — LUCIUS: compliance ✅
│   ├── market_data.py         — SIMULATED/PAPER/LIVE ✅
│   ├── feature_logger.py / live_market.py / microstructure.py
├── config/
│   ├── pairs.yaml             — MXN primary, ARS secondary
│   └── settings.yaml          — mode: SIMULATED, interval: 300s
├── scanners/ / research/
├── tests/                     — 126 tests total, all passing
└── storage/
    ├── logs/ (executions.jsonl, gordon_audit.jsonl, agent.log)
    └── ledger/ (trades.jsonl — HARVEY trade ledger)
```

---

## 7. DATA FLOW — HOW BATMAN FEEDS NIGHTWING

```
Batman Loop (every 20 min):
  ALFRED validates → Scanners detect → HARVEY stores in batman.db
  → Writes opportunities.jsonl → Updates latest.json

Nightwing cycle (every 5 min):
  1. fetch_prices()          — BTC/ETH (Binance real in PAPER)
  2. LUCIUS check            — jurisdiction, hours, limits
  3. Batman bridge fetch     — read latest opportunity for MXN
  4. DEDUP check             — skip if same opp_id as last cycle
  5. GORDON security         — circuit breaker, heartbeat, anomaly, exposure
  6. Decision                — PASS / OPPORTUNITY / BLOCKED
  7. log_execution()         — executions.jsonl
  8. record_trade()          — HARVEY trades.jsonl
  9. AUTO-PAUSE              — stop after 3 consecutive blocks
```

---

## 8. DATA CONTRACTS

### Opportunity Record (Batman writes)
```json
{
  "opp_id": "OPP-C-XXXXXXXX",
  "ts": "2026-03-15T00:00:00+00:00",
  "type": "C", "asset": "USDT", "market": "MXN",
  "venue": "binance_p2p",
  "p2p_buy_price": 18.066, "p2p_sell_price": 18.014,
  "spot_price": 17.894803,
  "spread_flag": "NORMAL", "premium_quality": "VERIFIED",
  "p2p_premium": 0.00957, "total_friction_pct": 0.25,
  "edge_net": 0.707, "viable": true,
  "depth_estimate": 24271, "merchant_count": 10,
  "scanner_id": "C-P2P-LATAM", "observe_only": true
}
```

### Scanner Types
- **Type A** — Cross-exchange spread. Threshold: 0.05%
- **Type B** — Spot vs Futures basis. Threshold: 0.02%
- **Type C** — P2P LATAM premium. Threshold: 0.20%
- **Type D** — Multi-exchange spread (5+ exchanges). Threshold: 0.10%
- **Type E** — Funding rate arbitrage. Threshold: 0.01% per 8h
- **Type F** — Cross-currency P2P premium spread. Threshold: 1.0%
- **Type G** — P2P merchant buy-sell spread. Threshold: 0.5%
- **Type H** — Stablecoin depeg (USDT, USDC, DAI). Threshold: 0.2%

---

## 9. VERIFIED MARKET DATA (as of 2026-03-15)

| Market | Avg Edge Net | Viable % | Friction | Depth |
|--------|-------------|----------|----------|-------|
| MXN | +0.62% to +0.71% | ~100% | 0.25% | $13k-$24k |
| ARS | +0.306% | 67% | 0.40% | $8,230 |
| COP | -0.59% | 0% | 0.30% | $24,673 |
| VES | -1.73% | 0% | 0.35% | $99,843 |

**MXN edge is consistent across March 13-15.** VES uses parallel rate from dolarapi.com.
**ALFRED dq_score: 1.0 (100%). Ollama: AVAILABLE (llama3.2:3b)**

---

## 10. OPERATIONAL READINESS LEVELS

| Level | Name | Requirements | Status |
|-------|------|-------------|--------|
| L0 | Observe Only | Scanners + logs + dq_score > 0.60 | ✅ Complete |
| L1 | Simulated | HARVEY + GORDON + edge validated | ✅ Complete |
| L2 | Paper Trading | Real prices + 2-3 days clean data | 🟡 In progress |
| L3 | Small Capital Live | ALL gates + COMMANDER + 30 days PAPER | 🔴 Not ready |
| L4 | Scaled Live | L3 stable 30 days | 🔴 Not ready |

---

## 11. KNOWN ISSUES & PRIORITIES

### HIGH
1. **COMMANDER pipeline incomplete** — gates not fully connected in engine.py
2. **LUCIUS reads executions.jsonl, GORDON reads trades.jsonl** — two sources for daily exposure, could drift

### PENDING
3. **Accumulate 2-3 days of clean PAPER data** — validate edge before L3
4. **Analyze strategy** with data when 200+ unique records exist
5. **Dashboard Streamlit for Nightwing** — nice-to-have

### RESOLVED (do not re-fix)
- ~~VES spread 9.9%~~ — Fixed (parallel rate)
- ~~dq_score 38%~~ — Fixed (ALFRED 100%)
- ~~Double engine bug~~ — Fixed
- ~~Batman→Nightwing bridge~~ — Fixed
- ~~HARVEY not built~~ — Fixed (both repos)
- ~~GORDON not built in Nightwing~~ — Fixed (4 protections, 25 tests)
- ~~Duplicate trades from same opp_id~~ — Fixed (dedup in agent.py)
- ~~Wasted cycles on LUCIUS blocks~~ — Fixed (auto-pause after 3)

---

## 12. INVIOLABLE RULES (NEVER BREAK THESE)

1. **OBSERVE-ONLY by default.** No real trades without explicit flags AND human gate.
2. **Append-only logs.** Never delete or modify `.jsonl` files.
3. **Every opportunity needs an evidence bundle.** No signal without reproducible inputs.
4. **No secrets in code.** API keys → `.env` only.
5. **Batman runs ALWAYS before Nightwing.**
6. **VES always uses parallel rate** from dolarapi.com.
7. **LIVE mode requires:** HARVEY ✅ + LUCIUS ✅ + GORDON ✅ + two explicit config flags.
8. **Do not modify team names/structure** without Erick's approval.
9. **Document every change** in `storage/logs/session_fixes.txt`.

---

## 13. HOW TO RUN

```bash
# Terminal 1: Batman (always first)
cd ~/Projects/batcave/batman_flow_engine
python tools/run_loop.py

# Terminal 2: Nightwing
cd ~/Projects/batcave/nightwing_agent
python agent.py --mode paper --cycles 0    # Continuous
python agent.py --mode paper --cycles 1    # Single cycle

# Terminal 3: Monitoring
cd ~/Projects/batcave/nightwing_agent
python -m pytest tests/ -v                 # 126 tests
python3 -c "from core.harvey import print_summary; print_summary()"

# Batman status
cd ~/Projects/batcave/batman_flow_engine
python tools/architecture_status.py
python tools/research_metrics.py
```

---

*Last updated: 2026-03-17 | Batman Lab — L1 operational, 383 tests, accumulating PAPER data*
*Pipeline: ALFRED → BATCOMPUTER → LUCIUS → GORDON → DEDUP → NIGHTWING → HARVEY*
*See EXPANSION_SPEC.md for Phase 2 multi-strategy expansion details (scanners D-H)*
