# NIGHTWING AGENT — MASTER CONTEXT FILE
# Read this file COMPLETELY before touching any code.
# This is the single source of truth for the Nightwing agent.

---

## 1. IDENTITY

**Agent Name:** NIGHTWING (Dick Grayson)
**Type:** P2P LATAM Arbitrage Execution Agent
**Parent System:** Batman Lab
**Mode:** SIMULATED by default. LIVE blocked. PAPER available and tested.
**Repo:** `~/Projects/batcave/nightwing_agent/`
**Brain:** `~/Projects/batcave/batman_flow_engine/` (reads data via bridge)
**Tests:** 126 passing
**Level:** L1 operational, accumulating PAPER data toward L2

**Core Rule:** Nightwing NEVER makes decisions alone. Batman provides the intelligence. Nightwing executes.

---

## 2. RELATIONSHIP WITH BATMAN

```
Batman (brain):
  Runs every 20 min → scans P2P markets → writes opportunities.jsonl
                                                    ↓
Nightwing (executor):
  batman_bridge.py reads last 50 lines of opportunities.jsonl
  → finds latest record for target fiat pair (type="C")
  → checks staleness (max 1200 seconds / 20 min)
  → deduplicates by opp_id (same opportunity = skip, don't re-trade)
  → returns edge_net, viable, premium, friction, depth, prices
```

**Batman MUST be running before Nightwing starts.**
**batman_bridge.py is the PRIMARY data source. market_data.py is FALLBACK only (BTC/ETH spot).**

---

## 3. FILE STRUCTURE

```
nightwing_agent/
├── agent.py                   — main agent loop (auto-pause + dedup)
├── alerts.py                  — alert system
├── dashboard.py               — Nightwing dashboard
├── scheduler.py               — cycle scheduler
├── core/
│   ├── batman_bridge.py       — reads from Batman's opportunities.jsonl ✅ (14 tests)
│   ├── feature_logger.py      — feature logging for research ✅
│   ├── gordon.py              — GORDON: security (4 protections) ✅ (25 tests)
│   ├── harvey.py              — HARVEY: trade execution ledger ✅ (18 tests)
│   ├── live_market.py         — live market data fetcher ✅
│   ├── lucius.py              — LUCIUS: compliance MXN/ARS/COP/VES ✅
│   ├── market_data.py         — SIMULATED/PAPER/LIVE price routing ✅
│   └── microstructure.py      — market microstructure analysis ✅
├── config/
│   ├── pairs.yaml             — MXN primary, ARS secondary, COP/VES disabled
│   └── settings.yaml          — mode: SIMULATED, interval: 300s
├── scanners/
│   ├── opportunity_scanner.py — opportunity detection
│   └── system_scanner.py      — system status scanner
├── research/
│   └── feature_analysis.py    — feature analysis tools
├── tests/                     — 126 tests total, all passing
│   ├── test_agent.py
│   ├── test_alerts.py
│   ├── test_batman_bridge.py  — 14 tests ✅ NEW
│   ├── test_dashboard.py
│   ├── test_feature_analysis.py
│   ├── test_feature_logger.py
│   ├── test_gordon.py         — 25 tests ✅ NEW
│   ├── test_harvey.py         — 18 tests ✅
│   ├── test_live_market.py
│   ├── test_lucius.py
│   ├── test_market_data.py
│   ├── test_microstructure.py
│   ├── test_p2p_depth.py
│   ├── test_scanners.py
│   └── test_scheduler.py
└── storage/
    ├── logs/
    │   ├── executions.jsonl    — agent execution records
    │   ├── gordon_audit.jsonl  — GORDON security event log
    │   ├── agent.log           — agent runtime log
    │   └── session_fixes.txt
    ├── ledger/
    │   └── trades.jsonl        — HARVEY trade ledger (append-only)
    └── reports/
```

---

## 4. AGENT CYCLE (what agent.py does each cycle)

```
1. Kill switch check           — if KILL_SWITCH file exists, stop
2. fetch_prices(mode)          — BTC/ETH spot from market_data.py (Binance real in PAPER)
3. LUCIUS check                — check_jurisdiction(fiat, amount_usd)
   → If blocked: log + skip (counts toward auto-pause)
4. Batman bridge fetch         — fetch_from_batman(fiat)
   → Gets: edge_net, viable, premium, friction, depth, prices, opp_id
   → If stale/error: edge_net=0, viable=False
5. DEDUP check                 — if opp_id == last_opp_id → SKIP (don't re-trade)
6. GORDON security check       — circuit breaker, heartbeat, spread anomaly, exposure
   → If blocked: log + record in HARVEY + skip (counts toward auto-pause)
7. Decision gate:
   → viable=False → PASS
   → viable=True → OPPORTUNITY
     → SIMULATED: action=LOGGED
     → PAPER: action=SIMULATED_TRADE
     → LIVE: action=BLOCKED (always)
8. log_execution(result)       — writes to executions.jsonl
9. record_trade(result)        — HARVEY writes to trades.jsonl
10. print_summary()            — HARVEY daily summary at end of session
```

**Auto-pause:** After 3 consecutive blocked cycles (LUCIUS or GORDON), agent stops automatically.
**Dedup:** Same opp_id as previous cycle = SKIP. No duplicate trades in ledger.

---

## 5. GORDON SECURITY (4 protections)

| Check | What it does | Default limit |
|-------|-------------|---------------|
| Circuit breaker | Stops if daily P&L < threshold | -2.0% |
| Batman heartbeat | Stops if Batman data > threshold age | 2400s (40 min) |
| Spread anomaly | Blocks edge > 3% or < -5% (bad data) | 3.0% / -5.0% |
| Daily exposure | Blocks if daily total > limit | $10,000 / $2,500 single |

Plus: kill switch (file-based), audit log (gordon_audit.jsonl).
GORDON warns (but doesn't block) on: ANOMALOUS spread flag, merchant count < 3.

---

## 6. DATA BATMAN SENDS (bridge response format)

```json
{
  "status": "ok",
  "fiat": "MXN",
  "market": "USDT/MXN",
  "p2p_premium": 0.0069,
  "edge_net": 0.685,
  "viable": true,
  "total_friction_pct": 0.25,
  "spot_price": 17.894612,
  "p2p_buy_price": 18.062,
  "p2p_sell_price": 18.026,
  "depth_estimate": 23074.1,
  "merchant_count": 10,
  "premium_quality": "VERIFIED",
  "rate_source": "official",
  "spread_flag": "NORMAL",
  "age_seconds": 21,
  "batman_ts": "2026-03-14T14:35:41+00:00",
  "opp_id": "OPP-C-1278F4DC89"
}
```

Possible status values: `"ok"`, `"stale"`, `"error"`

---

## 7. CONFIGURATION

### pairs.yaml
```yaml
pairs:
  - symbol: USDT/MXN
    enabled: true
    priority: 1       # Primary — SPEI, high liquidity
  - symbol: USDT/ARS
    enabled: true
    priority: 2       # Secondary — 24/7, smaller limits
  - symbol: USDT/COP
    enabled: false     # Negative edge
  - symbol: USDT/VES
    enabled: false     # Negative edge
```

### settings.yaml
```yaml
mode: SIMULATED       # SIMULATED | PAPER | LIVE (LIVE blocked)
cycle:
  interval_seconds: 300
gates:
  min_edge_net_pct: 0.10
```

---

## 8. LUCIUS COMPLIANCE RULES

| Fiat | Enabled | Hours | Max Single USD | Max Daily USD |
|------|---------|-------|----------------|---------------|
| MXN | ✅ | SPEI 05:00-23:30 Mexico City | $2,500 | $10,000 |
| ARS | ✅ | 24/7 | $500 | $2,000 |
| COP | ❌ | — | — | — |
| VES | ❌ | — | — | — |

**Note:** LUCIUS reads daily exposure from `executions.jsonl`, not from HARVEY's `trades.jsonl`.

---

## 9. MARKET DATA (verified as of 2026-03-15)

| Pair | Edge Net | Viable | Friction | Depth |
|------|----------|--------|----------|-------|
| USDT/MXN | +0.62% to +0.71% | ✅ 100% | 0.25% | $13k-$24k |
| USDT/ARS | +0.306% | ✅ 67% | 0.40% | $8,230 |
| USDT/COP | -0.59% | ❌ No | 0.30% | $24,673 |
| USDT/VES | -1.73% | ❌ No | 0.35% | $99,843 |

MXN edge is consistent across multiple sessions (March 13-15).

---

## 10. OPERATIONAL RULES

1. **Batman runs ALWAYS before Nightwing.** Run `python tools/run_loop.py` in batman_flow_engine first.
2. **LIVE mode is BLOCKED.** Requires: HARVEY ✅ + LUCIUS ✅ + GORDON ✅ + two explicit config flags.
3. **batman_bridge.py is PRIMARY source.** market_data.py is fallback for BTC/ETH spot only.
4. **Dedup is active.** Same opp_id = SKIP. One trade per unique opportunity.
5. **Auto-pause is active.** 3 consecutive blocks → agent stops automatically.
6. **VES always uses parallel rate** from dolarapi.com, never official.
7. **Append-only logs.** Never delete or modify executions.jsonl or trades.jsonl.
8. **Document every change** in `storage/logs/session_fixes.txt`.
9. **All files in this repo ONLY.** Do NOT create files in batman_flow_engine/ or anywhere else.

---

## 11. HOW TO RUN

```bash
# === Terminal 1: Batman (always first) ===
cd ~/Projects/batcave/batman_flow_engine
python tools/run_loop.py

# === Terminal 2: Nightwing ===
cd ~/Projects/batcave/nightwing_agent
python agent.py --mode paper --cycles 0     # Continuous PAPER mode
python agent.py --mode simulated --cycles 1 # Single SIMULATED cycle

# === Terminal 3: Tests & monitoring ===
cd ~/Projects/batcave/nightwing_agent
python -m pytest tests/ -v                  # 126 tests
python3 -c "from core.harvey import print_summary; print_summary()"  # Daily ledger

# Check Batman freshness
python3 -c "
from core.batman_bridge import fetch_from_batman, is_batman_alive
print('Batman alive:', is_batman_alive())
data = fetch_from_batman('MXN')
print(f'Status: {data[\"status\"]}')
if data.get('status') == 'ok':
    print(f'Edge: {data[\"edge_net\"]}% Viable: {data[\"viable\"]} Age: {data[\"age_seconds\"]:.0f}s')
"
```

---

## 12. LAST VERIFIED OUTPUT (2026-03-15)

```
NIGHTWING P2P AGENT  Mode: PAPER  Cycles: 1

[Cycle 1] BTC: $71,679.99  ETH: $2,106.46
[Cycle 1] LUCIUS APPROVED: MXN $500.00 USD
[Cycle 1] 🦇 USDT/MXN premium=+0.957% edge_net=+0.707% viable=✅
          spot=17.894803 buy=18.066 sell=18.014
          friction=0.25% depth=$24,271 age=512s
[Cycle 1] 🛡️ GORDON APPROVED
          OPPORTUNITY - viable=True edge_net=+0.707%
          SIMULATING trade (PAPER mode)
[Cycle 1] Complete in 366ms
```

---

## 13. KNOWN ISSUES

1. **LUCIUS reads from executions.jsonl, GORDON reads from trades.jsonl** — two different files for daily exposure tracking. Could cause inconsistency. Future fix: unify to one source.
2. **Nightwing runs every 5 min, Batman every 20 min** — most cycles are SKIP (dedup). Consider matching intervals or making Nightwing wait for new Batman data.

---

## 14. PENDING (in priority order)

1. **Accumulate 2-3 days of clean PAPER data** — validate edge consistency
2. **Analyze strategy** with GPT-5.4 when 200+ unique records exist
3. **COMMANDER pipeline in Batman** — connect gates in engine.py
4. **Dashboard Streamlit** — nice-to-have visualization

---

*Last updated: 2026-03-15 | Nightwing Agent — L1 operational, 126 tests passing*
*Pipeline: Prices → LUCIUS → Bridge → Dedup → GORDON → Decision → HARVEY*
