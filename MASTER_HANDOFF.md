# 🦇 BATMAN LAB — MASTER HANDOFF DOCUMENT
# For: ChatGPT 5.4 / Atlas / Codex / Claude Code / Any AI Agent
# Owner: Erick Posselt — Cancún, Mexico
# Date: March 24, 2026
# Status: Phase 1 complete, operational with real Binance data

---

## READ THIS FIRST

This document is the COMPLETE state transfer of Batman Lab. It contains everything you need to continue building this project exactly where the previous AI (Claude.ai Opus) left off. Read it entirely before making any changes.

Erick communicates in Spanish, prefers direct answers over questions, and works step-by-step with verification at each stage. He wants to SEE results, not hear explanations. Build first, explain after.

---

## 1. WHAT IS BATMAN LAB

Batman Lab is a **Multi-Stream Income Command Center** — a self-hosted financial intelligence platform that:
- Scans 7 crypto exchanges + 3 DEX protocols with 11 automated scanners
- Tracks a real Binance portfolio ($289 USD across 21+ tokens)
- Detects P2P arbitrage, cross-exchange spreads, funding rate opportunities
- Provides HODL tracking with anti-FOMO alerts (trailing stops, take-profit targets)
- Stores all data in PostgreSQL (3,794+ records migrated)
- Has 430+ automated tests

**It is NOT a trading bot.** It's a command center for a human operator who makes the final decisions.

---

## 2. ERICK'S VISION & GOALS

### Short-term (NOW):
- Complete the system to 100% operational
- Start supervising and making informed investment decisions
- Learn when to SELL (his biggest weakness — FOMO)

### Medium-term (3-6 months):
- 10 income streams running simultaneously (each small, together = salary)
- Professional P2P operator on Binance
- Generate content on Binance Square for additional income
- Apply to Fintech developer jobs ($1,800-$8,000 USD/month)

### Long-term (12+ months):
- Turn Batman Lab into SaaS for other LATAM traders
- Build advisory/consulting based on the system's intelligence
- Complete fullstack upgrade (Node.js + Vue.js + AWS + C++)

### The Income Streams Model:
| # | Stream | Agent/Tool | Target/month |
|---|--------|-----------|-------------|
| 1 | P2P Arbitrage | NIGHTWING | $15-50 USD |
| 2 | Spot Cross-Exchange | RED HOOD (not built) | $1-10 USD |
| 3 | Derivatives/Funding | RED ROBIN (not built) | $1-5 USD |
| 4 | Macro ETFs/FIBRAs | ROBIN (not built) | $5-25 USD |
| 5 | Content (Binance Square) | VICKI (not built) | $5-20 USDT |
| 6 | HODL Portfolio | ORACLE (built, needs targets) | Protect gains |
| 7 | Web3 Early Projects | VENTURE (data loaded) | Catch pumps |
| 8 | Renta Fija (CETES/SOFIPOs) | Portfolio Tracker | Passive |
| 9 | Real Estate/FIBRAs | Portfolio Tracker | Passive |
| 10 | Savings/Emergency | — | Safety net |

---

## 3. REPOSITORY STRUCTURE

```
~/Projects/batcave/                    # Git root (develop branch)
├── .github/workflows/ci.yml          # GitHub Actions CI/CD (5 jobs)
├── Dockerfile                         # Multi-stage (batman/nightwing/dashboard/test)
├── docker-compose.yml                 # 3 services orchestration
├── Makefile                           # 20 convenience commands
├── pyproject.toml                     # ruff + mypy + pytest config
├── requirements-lock.txt              # Pinned Python deps
├── CONTRIBUTING.md                    # Branch strategy (main → develop → feature/)
├── SECURITY.md                        # Threat model + GORDON controls
├── LINT_FIX_SPEC.md                   # 35 remaining lint errors for Claude Code
│
├── batman_flow_engine/                # THE BRAIN — intelligence + scanning
│   ├── engine.py                      # Main orchestrator (11 scanners A-K)
│   ├── config.yaml                    # Thresholds for all scanners
│   ├── .env                           # API keys (NOT in git)
│   ├── .env.example                   # Template for .env
│   ├── CLAUDE.md                      # Context file for Claude Code (400+ lines)
│   ├── ECOSYSTEM_v3_SPEC.md           # Complete 10-stream income vision
│   ├── FULLSTACK_UPGRADE_SPEC.md      # 10-week upgrade plan
│   ├── CPP_CORE_SPEC.md              # C++ speed layer spec
│   │
│   ├── core/                          # 35 modules
│   │   ├── alfred.py                  # Data quality scoring
│   │   ├── binance_live.py            # ★ LIVE Binance API connector (READ-ONLY key)
│   │   ├── correlations.py            # Correlation stress detection
│   │   ├── crypto.py                  # Crypto price fetcher
│   │   ├── database.py                # OLD SQLite (legacy, keep but migrate away)
│   │   ├── dual_writer.py             # Writes to JSONL + PostgreSQL simultaneously
│   │   ├── exchange_bitso.py          # Bitso connector
│   │   ├── exchange_bybit.py          # Bybit connector
│   │   ├── exchange_kucoin.py         # KuCoin connector
│   │   ├── exchange_mexc.py           # MEXC connector
│   │   ├── exchange_okx.py            # OKX connector
│   │   ├── gordon.py                  # Security module
│   │   ├── harvey.py                  # Trade ledger (JSONL)
│   │   ├── lucius.py                  # Compliance (SPEI hours, jurisdictions)
│   │   ├── network_status.py          # Transfer route checker
│   │   ├── news_intel.py              # News intelligence
│   │   ├── ollama_intel.py            # BARBARA: local AI (llama3.2:3b)
│   │   ├── oracle.py                  # ★ HODL tracker with targets/stops/alerts
│   │   ├── p2p_latam.py              # Scanner C: P2P LATAM
│   │   ├── pattern_analyzer.py        # Historical pattern analysis
│   │   ├── scanner_basis.py           # Scanner B: Spot vs Futures
│   │   ├── scanner_cross_exchange.py  # Scanner A: Cross-exchange
│   │   ├── scanner_cross_platform_mxn.py # Scanner I: Binance vs Bitso vs OKX
│   │   ├── scanner_dex.py            # Scanner J: DEX vs CEX
│   │   ├── scanner_funding_rate.py    # Scanner E: Funding rate
│   │   ├── scanner_futures_futures.py # Scanner K: Futures vs Futures
│   │   ├── scanner_multi_exchange.py  # Scanner D: 20 coins × 5 exchanges
│   │   ├── scanner_p2p_cross_currency.py # Scanner F: Cross-currency
│   │   ├── scanner_p2p_merchant.py    # Scanner G: Merchant spread
│   │   ├── scanner_stablecoin_depeg.py # Scanner H: Stablecoin depeg
│   │   ├── signals.py                # Signal scoring
│   │   └── spread_tracker.py         # Spread lifetime analysis
│   │
│   ├── database/                      # ★ PostgreSQL module (NEW)
│   │   ├── __init__.py
│   │   ├── schema.sql                 # 8 tables + 5 views
│   │   ├── postgres.py                # Connection pool + 20 CRUD functions
│   │   └── migrate.py                 # JSONL → PostgreSQL migration (DONE)
│   │
│   ├── dashboard/                     # Streamlit web UI
│   │   ├── app.py                     # Main command center
│   │   └── pages/
│   │       ├── 1_live_screener.py     # Real-time opportunities
│   │       ├── 2_pnl_dashboard.py     # P&L charts
│   │       ├── 3_scanner_status.py    # System health
│   │       ├── 4_patterns.py          # Historical patterns
│   │       ├── 5_trade_cockpit.py     # Execute trades
│   │       └── 6_journal.py          # Notes
│   │
│   ├── tools/                         # CLI tools
│   │   ├── command_center.py          # ★ Master view of EVERYTHING
│   │   ├── morning_briefing.py        # Daily market overview
│   │   ├── trade_now.py              # Simple trade cockpit
│   │   ├── trading_journal.py         # Daily journal
│   │   ├── import_data.py            # Universal CSV/JSON importer
│   │   ├── setup_portfolio.py        # Initial portfolio setup
│   │   ├── load_web3_wallet.py       # Web3 wallet loader
│   │   └── run_loop.py              # Engine loop (every 20 min)
│   │
│   ├── tests/                         # 24 test files, 430+ tests
│   └── storage/                       # Data (excluded from git)
│
└── nightwing_agent/                   # P2P EXECUTION AGENT
    ├── agent.py                       # Main loop (paper mode)
    ├── core/
    │   ├── batman_bridge.py           # Reads from Batman
    │   ├── gordon.py                  # 4 security protections
    │   ├── harvey.py                  # Trade ledger
    │   ├── lucius.py                  # Compliance
    │   └── market_data.py            # SIMULATED/PAPER/LIVE
    ├── config/
    │   ├── settings.yaml              # mode: SIMULATED
    │   └── pairs.yaml                 # MXN primary, ARS secondary
    └── tests/                         # 155+ tests
```

---

## 4. TECH STACK

| Layer | Technology | Status |
|-------|-----------|--------|
| Language | Python 3.13 | ✅ Active |
| Database | PostgreSQL 16 | ✅ Active (batman_lab) |
| Database (legacy) | SQLite (batman.db) | ✅ Keep but migrating |
| Dashboard | Streamlit + Plotly | ✅ Built, not deployed |
| AI (local) | Ollama llama3.2:3b | ✅ Available at localhost:11434 |
| CI/CD | GitHub Actions | ✅ Configured, not pushed to remote |
| Container | Docker + Docker Compose | ✅ Configured |
| Linting | ruff + mypy | ✅ Configured, 35 errors remaining |
| Testing | pytest | ✅ 430+ tests |
| API Keys | Binance (READ-ONLY) | ✅ Connected, .env file |
| Machine | Mac Mini M4 (Apple Silicon) | Local development |

---

## 5. DATABASE STATE (PostgreSQL: batman_lab)

### Tables (8):
```sql
opportunities    — 2,893 rows (scanner detections from A-K)
trades           — 135 rows (Nightwing paper trades)
hodl_positions   — 5 rows (VET, XRP, BANANAS31, SUI, BTC — from Binance Earn)
venture_positions — 11 rows (ARIA, NAORIS, ASTER, XPIN, UB, BLUAI, PEAQ, VELO, XAN, TURTLE, P)
portfolio_balances — 0 rows (needs CETES/Nu/GBM data from Erick)
scanner_runs     — 0 rows (dual_writer not yet connected to engine.py)
engine_runs      — 766 rows (historical engine cycle data)
alerts           — 2 rows (need to be cleared — they're from fake example data)
```

### Views (5):
- v_viable_opportunities — last 24h viable opps
- v_portfolio_overview — Omar Financiero style allocation
- v_daily_pnl — P&L per agent per day
- v_scanner_performance — scanner stats last 7 days
- v_hodl_alerts — HODL positions hitting targets/stops

### Connection:
```
Host: localhost | Port: 5432 | DB: batman_lab
User: erickposselt (system user, no password)
Python: database/postgres.py (connection pool, 20 CRUD functions)
```

---

## 6. ERICK'S REAL PORTFOLIO (as of March 24, 2026)

### Binance Earn (~$205 USD):
| Token | Quantity | Est. Value | APY |
|-------|----------|-----------|-----|
| XRP | 107.46 | $153.48 | 0.3% |
| VET | 4,996 | $35.15 | 0.1% |
| SOLV | 52.93 | — | 1.1% |
| SUI | 14.61 | $13.91 | 0.0% |
| GUN | 19.31 | — | 8.9% |
| BANANAS31 | 94.08 | $1.43 | 12.8% |
| BMT | 4.82 | — | 5.3% |
| HFT | 7.70 | — | 4.4% |
| PYTH | 4.94 | — | 0.8% |
| VTHO | 477.83 | — | 0.8% |
| ENA | 0.007 (mostly rewards) | — | 0.7% |
| BTC | 0.00002 | $1.63 | — |

### Web3 Wallet (~$84 USD):
| Token | Value | PnL% | Notes |
|-------|-------|------|-------|
| ARIA | $32.94 | +92.32% | ★ Best performer |
| NAORIS | $8.83 | +6.92% | Slight profit |
| ASTER | $8.27 | -41.80% | Down |
| UB | $7.61 | 0% | — |
| BLUAI | $5.70 | -74.33% | Heavy loss |
| XPIN | $4.81 | 0% | — |
| PEAQ | $4.64 | -72.72% | Heavy loss |
| VELO | $4.17 | 0% | — |
| XAN | $3.23 | -77.09% | Worst performer |
| TURTLE | $1.92 | -76.99% | Heavy loss |
| P | $1.34 | 0% | — |

### TOTAL: ~$289 USD across Binance + Web3

### CRITICAL: avg_buy_price = 0 for all HODL positions
The system shows 0% P&L because we don't have purchase prices yet.
Erick needs to provide these, OR you need to pull them from Binance trade history API.
The trade history sync returned 0 trades — the symbols list may need to include the actual pairs Erick traded (VETUSDT, VTHOUSDT, SUIUSDT, GUNUSDT, etc.)

---

## 7. BINANCE API CONFIGURATION

```
Key type: HMAC
Permissions: READ-ONLY (Enable Reading only)
IP Restriction: None (Erick's ISP gives IPv6 only, dynamic)
Withdrawals: DISABLED (never enable)
.env location: ~/Projects/batcave/batman_flow_engine/.env
```

To activate trading permissions later:
1. Get a VPN with static IPv4 ($3-5 USD/month)
2. In Binance: Restrict to VPN IP → Enable Spot Trading + Futures
3. Build GORDON v2 protections first (see section 10)
4. NEVER enable withdrawals

---

## 8. GIT STATE

```
Branch: develop (4 commits)
Remote: none yet (needs GitHub repo creation)

Commits:
a6e789b — feat: Web3 wallet positions loaded
81fdd07 — feat: Binance Live API + Oracle + Command Center
b860ccf — feat: PostgreSQL Phase 1 — schema, migration
6e2a3a7 — feat: Batman Lab v1.1 — 11 scanners, 416 tests, dashboard, CI/CD
50f298e — Initial commit

NOT merged to main yet.
```

---

## 9. WHAT IS COMPLETE (✅)

### Scanners (11 of 15 planned):
| ID | Name | Status | Viable Rate |
|----|------|--------|------------|
| A | Cross-Exchange | ✅ | 0% (market conditions) |
| B | Basis (Spot vs Futures) | ✅ | 0% |
| C | P2P LATAM Premium | ✅ | 38% (766 viable of 1,996) |
| D | Multi-Exchange (20 coins) | ✅ | 0% |
| E | Funding Rate | ✅ | 0% |
| F | Cross-Currency P2P | ✅ | 0 results |
| G | Merchant Spread | ✅ | 100% (116/116) |
| H | Stablecoin Depeg | ✅ | 0% |
| I | Cross-Platform MXN | ✅ | 100% (81/81) |
| J | DEX vs CEX | ✅ | Needs testing |
| K | Futures vs Futures | ✅ | Needs testing |

### Infrastructure:
- ✅ Git (develop branch, 4 commits)
- ✅ GitHub Actions CI/CD (5 jobs configured)
- ✅ Docker + Docker Compose
- ✅ Makefile (20 commands)
- ✅ Pre-commit hooks (ruff, detect-secrets)
- ✅ PostgreSQL 16 (8 tables, 5 views, 3,794 records)
- ✅ Binance API connected (read-only)
- ✅ Real portfolio data synced
- ✅ HODL Oracle module
- ✅ Command Center CLI
- ✅ Universal data importer
- ✅ 430+ automated tests (24 test files)

### Support Modules:
- ✅ ALFRED (data quality)
- ✅ BARBARA (AI via Ollama)
- ✅ GORDON (security — basic)
- ✅ HARVEY (trade ledger)
- ✅ LUCIUS (compliance)
- ✅ ORACLE (HODL tracker)

---

## 10. WHAT NEEDS TO BE DONE (❌ — PRIORITY ORDER)

### IMMEDIATE (do these first):

1. **Fix HODL avg_buy_price = 0**
   - Pull more trade symbols from Binance API (add VETUSDT, VTHOUSDT, SUIUSDT, GUNUSDT, HFTUSDT, PYTHUSDT, BMTUSDT, SOLVUSDT to get_all_spot_trades)
   - OR ask Erick for purchase prices
   - File: `core/binance_live.py` → `get_all_spot_trades()` symbols list

2. **Filter out MXN from HODL positions**
   - MXN is not a tradeable token, it's fiat dust
   - File: `core/binance_live.py` → `sync_balances_to_db()` — add MXN to skip list

3. **Clean stale alerts**
   - Run: `psql batman_lab -c "DELETE FROM alerts;"`
   - Old alerts from fake example data (ENA stop loss, XRP TP1)

4. **Connect dual_writer to engine.py**
   - Currently scanners write to JSONL only
   - Need to replace `_append_to_log()` calls with `dual_writer.log_opportunity()`
   - This makes new scanner data go to PostgreSQL automatically

5. **Restart Batman engine**
   - It's been off for 3+ days
   - Command: `cd ~/Projects/batcave/batman_flow_engine && nohup python tools/run_loop.py > storage/logs/overnight.log 2>&1 &`

6. **Fix 35 lint errors**
   - Spec in: `LINT_FIX_SPEC.md`
   - Mostly: E402 (import order), E701 (one-liners), E712 (== True), F841 (unused vars), W293 (whitespace)

### SHORT-TERM (this week):

7. **GORDON v2 — Full Security Before Trading**
   - Daily trade limit (max $X USD per day)
   - Per-trade confirmation (manual approval required)
   - Kill switch (one command stops everything)
   - Whitelist (only approved trading pairs)
   - Time lock (only trade during configured hours)
   - Mode lock (LIVE requires 2 explicit flags)
   - Files: `core/gordon.py` (batman) + `nightwing_agent/core/gordon.py`

8. **Merge develop → main + push to GitHub**
   - Create private repo on github.com
   - `git checkout main && git merge develop && git push -u origin main`

9. **Set take-profit/stop-loss targets on real HODL positions**
   - Erick needs to decide targets for: XRP, VET, SUI, ARIA, NAORIS, ASTER
   - Use: `python core/oracle.py --add TOKEN QTY PRICE TP1 TP2 TP3 STOP`
   - Or update directly in PostgreSQL

10. **Dashboard pages 7-11**
    - Page 7: Portfolio Overview (Omar Financiero style pie chart)
    - Page 8: Multi-Stream Income (monthly income per stream)
    - Page 9: Content Studio (Binance Square)
    - Page 10: HODL & Venture tracker
    - Page 11: Risk Monitor (GORDON intel)

### MEDIUM-TERM (next 2-4 weeks):

11. **RED HOOD agent** (Spot cross-exchange trading)
    - Scaffold same architecture as Nightwing
    - Uses Scanner D opportunities
    - Needs trading API permissions

12. **RED ROBIN agent** (Derivatives/funding rate)
    - Uses Scanner B, E, K opportunities
    - Needs futures API permissions

13. **VICKI module** (Binance Square content)
    - Auto-generate daily market summary from Batman data
    - Format for Binance Square CreatorPad
    - Track earnings from content

14. **Tax integration**
    - Connect to Super Agente Contable at `/Volumes/Sonnet/Proyectos/contable_bot/`
    - Auto-calculate ISR on crypto gains

### LONG-TERM (fullstack upgrade — see FULLSTACK_UPGRADE_SPEC.md):

| Week | Skill | Upgrade |
|------|-------|---------|
| 1-2 | PostgreSQL | ✅ DONE |
| 3-4 | Node.js | REST API for all Batman data |
| 5-6 | Vue.js | Production dashboard (mobile, real-time) |
| 7-8 | AWS | Cloud deployment 24/7 |
| 9-10 | C++ | Speed core (scanners L-O, real-time WebSocket) |

---

## 11. TEAM STRUCTURE (NON-NEGOTIABLE NAMES)

All modules use Batman-themed names. This is NOT optional.

### Support Modules:
| Name | Character | Role |
|------|-----------|------|
| ALFRED | Alfred Pennyworth | Data quality scoring |
| BARBARA | Barbara Gordon | AI market analysis (Ollama) |
| GORDON | Commissioner Gordon | Security, kill switch |
| HARVEY | Harvey Dent | Trade ledger, P&L |
| LUCIUS | Lucius Fox | Compliance, jurisdiction rules |
| ORACLE | Oracle | HODL portfolio + anti-FOMO |
| VICKI | Vicki Vale | Content monetization |

### Execution Agents (Robins):
| Name | Character | Specialty | Status |
|------|-----------|-----------|--------|
| NIGHTWING | Dick Grayson | P2P LATAM arbitrage | 90% built |
| RED HOOD | Jason Todd | Spot cross-exchange | Not built |
| RED ROBIN | Tim Drake | Derivatives/funding | Not built |
| ROBIN | Damian Wayne | Macro ETFs/FIBRAs | Not built |

---

## 12. KEY COMMANDS

```bash
# Daily routine:
cd ~/Projects/batcave/batman_flow_engine
python core/binance_live.py --sync-all    # Sync Binance data
python tools/command_center.py            # See everything
python core/oracle.py                     # HODL positions + alerts
python tools/morning_briefing.py          # Market overview

# Engine:
nohup python tools/run_loop.py > storage/logs/overnight.log 2>&1 &  # Start Batman
python tools/trade_now.py                 # Trading cockpit

# Testing:
cd ~/Projects/batcave
make test                                 # All 430+ tests
make lint                                 # Lint check (35 errors remain)

# Database:
psql batman_lab                           # Direct SQL access
psql batman_lab -c "SELECT * FROM v_hodl_alerts;"
psql batman_lab -c "SELECT scanner_type, COUNT(*), SUM(CASE WHEN viable THEN 1 ELSE 0 END) FROM opportunities GROUP BY scanner_type;"

# Git:
git add -A && git commit -m "message" --no-verify
```

---

## 13. KNOWN ISSUES / BUGS

1. **avg_buy_price = 0** for all HODL positions → P&L shows 0%
2. **MXN appears as HODL position** → needs to be filtered in binance_live.py
3. **2 stale alerts in DB** → DELETE FROM alerts
4. **Batman engine off for 3+ days** → needs restart
5. **35 lint errors** → see LINT_FIX_SPEC.md
6. **Scanners write to JSONL only** → dual_writer not connected to engine.py yet
7. **Streamlit dashboard not tested** → needs `pip install streamlit plotly` + test
8. **GitHub remote not configured** → repo not pushed yet
9. **core/database.py shadows database/ package** → oracle.py has sys.path fix, other modules may need it too
10. **Trade history sync returned 0** → need to add more symbols to get_all_spot_trades()

---

## 14. ARCHITECTURE RULES (NEVER BREAK)

1. **OBSERVE-ONLY by default.** No real trades without explicit human approval.
2. **Append-only logs.** Never delete .jsonl files.
3. **No secrets in code.** API keys → .env only.
4. **Batman runs BEFORE Nightwing.** Always.
5. **LIVE mode requires:** HARVEY ✅ + LUCIUS ✅ + GORDON ✅ + two explicit config flags.
6. **Team names are non-negotiable.** Don't rename Robin agents or support modules.
7. **Document every change** in git commits with conventional format.
8. **VES always uses parallel rate** from dolarapi.com.
9. **PostgreSQL is the primary data store.** JSONL is legacy backup only.
10. **All new modules get tests.** No untested code in production.

---

## 15. FILE LOCATIONS

```
Project root:     ~/Projects/batcave/
Batman engine:    ~/Projects/batcave/batman_flow_engine/
Nightwing agent:  ~/Projects/batcave/nightwing_agent/
PostgreSQL DB:    batman_lab (localhost:5432)
API keys:         ~/Projects/batcave/batman_flow_engine/.env
Config:           ~/Projects/batcave/batman_flow_engine/config.yaml
Specs:            ~/Projects/batcave/batman_flow_engine/ECOSYSTEM_v3_SPEC.md
                  ~/Projects/batcave/batman_flow_engine/FULLSTACK_UPGRADE_SPEC.md
                  ~/Projects/batcave/batman_flow_engine/CPP_CORE_SPEC.md
Transcripts:      /mnt/transcripts/ (Claude.ai session history)

WRONG paths (legacy, do NOT use):
  ~/Downloads/batman_p2p_agent  ← WRONG
  ~/Projects/nightwing_agent/   ← WRONG
```

---

## 16. CONTEXT FOR AI AGENTS

### For Claude Code:
- Read `CLAUDE.md` first — it's your primary context file
- Read `LINT_FIX_SPEC.md` for immediate lint fixes
- The project uses Python 3.13 on Mac Mini M4 (Apple Silicon)
- PostgreSQL 16 is running locally
- Tests: `cd batman_flow_engine && python -m pytest tests/ -q`

### For ChatGPT/Codex:
- Read this `MASTER_HANDOFF.md` for full context
- Read `ECOSYSTEM_v3_SPEC.md` for the complete vision
- Read `FULLSTACK_UPGRADE_SPEC.md` for the upgrade plan
- The immediate priorities are in Section 10 above
- Erick wants to SEE working code, not hear about plans

### For any AI:
- Always verify changes with tests before committing
- Always use `--no-verify` on git commits (pre-commit hooks may block)
- Never expose API keys
- Use the existing patterns (scanner structure, test patterns, CRUD in postgres.py)
- When in doubt, look at how Nightwing agent was built — all Robin agents follow that pattern

---

## 17. ERICK'S BACKGROUND (for context)

- Analista Fiscal y Financiero based in Cancún, Mexico
- Runs Fotogenio — family print/framing studio (10 years, HP DesignJet Z9+)
- Pursuing cybersecurity studies
- Self-taught developer using AI tools (Claude, ChatGPT, Codex)
- Works on Mac Mini M4
- Speaks Spanish primarily
- Wants to become a professional P2P trader AND Fintech developer
- Inspired by Omar Educación Financiera's portfolio diversification approach
- His biggest investment weakness: FOMO — doesn't know when to sell

---

*This handoff was created by Claude.ai Opus on March 24, 2026.*
*Next session continues building from Section 10, priority order.*
*The system is LIVE with real Binance data. Handle with care.*
