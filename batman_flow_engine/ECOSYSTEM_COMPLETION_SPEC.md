# BATMAN LAB — ECOSYSTEM COMPLETION SPEC v1.0
# Everything needed to reach 100% before first operation
# Created: 2026-03-20

---

## CURRENT STATE: 65% → TARGET: 100%

### What exists (34 modules, 383+ tests, 9 scanners A-I)
### What's missing: 12 components across 4 categories

---

## CATEGORY 1: WEB DASHBOARD (Priority: CRITICAL)
**Goal: Replace terminal with browser-based command center**
**Tech: Streamlit (Python, already in stack)**
**Location: ~/Projects/batcave/batman_flow_engine/dashboard/**

### Pages needed:

#### 1.1 — LIVE SCREENER (main page)
- Real-time table of ALL scanner results (A through I)
- Columns: Scanner | Asset | Buy Exchange | Buy Price | Sell Exchange | Sell Price | Spread % | Edge Net % | Viable | Age
- Color coding: green = viable, red = negative, yellow = marginal
- Auto-refresh every 60 seconds
- Filter by: scanner type, asset, exchange, viable only
- Sort by: edge_net descending (best opportunities first)
- THIS IS THE ARBITRAGESCANNER EQUIVALENT

#### 1.2 — P&L DASHBOARD
- Daily P&L chart (line chart, cumulative)
- Weekly/monthly summary cards
- Trade history table from HARVEY ledger
- Win rate, average edge, best/worst trade
- Capital growth curve
- Read from: nightwing_agent/storage/ledger/trades.jsonl

#### 1.3 — SCANNER STATUS
- Health of each scanner (A-I): last run, opportunities found, errors
- Batman engine health: alive/stale, dq_score, regime
- Nightwing status: mode, cycles, last decision
- System resources: disk, memory

#### 1.4 — HISTORICAL PATTERNS
- Heatmap: best hours of day × day of week for each scanner
- Spread distribution chart per scanner
- Edge trend over time (is the market getting tighter?)
- Read from: storage/logs/opportunities.jsonl (accumulated data)

#### 1.5 — TRADING COCKPIT (trade_now.py but in browser)
- Current best opportunity with STEP BY STEP instructions
- "I did this trade" button → records in HARVEY
- Notes field → saves to journal
- Timer: how long since opportunity appeared

#### 1.6 — JOURNAL / NOTES
- Today's journal entry (editable in browser)
- Quick note button (timestamp + text)
- View past journal entries
- Read/write from: batman_flow_engine/journal/*.md

---

## CATEGORY 2: EXPANDED SCANNING (Priority: HIGH)

### 2.1 — Scanner D expansion: Top 20 coins
Current: BTC, ETH, SOL (3 coins across Binance/OKX/Bybit)
Target: Add these 17 coins:
- XRP, DOGE, ADA, AVAX, LINK, DOT, MATIC, UNI, ATOM
- NEAR, APT, ARB, OP, FIL, LTC, BCH, XLM

Changes needed:
- Update ASSETS list in scanner_multi_exchange.py
- Add exchange-specific symbol formats for each
- Verify each coin exists on Binance + OKX + Bybit
- May need to batch API calls to avoid rate limits

### 2.2 — DEX Scanner (Scanner J)
New scanner: Compare CEX prices vs DEX prices
DEX sources:
- Uniswap V3 (Ethereum) — via public subgraph API
- PancakeSwap V3 (BSC) — via public subgraph API
- Raydium (Solana) — via Jupiter aggregator API

Strategy: Buy on DEX if cheaper, sell on CEX. Or vice versa.
Fields:
- type: "J"
- scanner_id: "J-DEX-CEX"
- dex_name, dex_price, cex_name, cex_price
- spread_pct, gas_estimate_usd, bridge_cost_usd
- edge_net (after gas + bridge)
- chain: ethereum/bsc/solana

Note: DEX scanning is MORE COMPLEX than CEX because:
- Gas fees vary (ETH gas can be $5-50)
- Bridge costs between chains
- Slippage on DEX trades
- Need web3 libraries (web3.py or httpx for subgraph queries)

### 2.3 — Futures vs Futures (Scanner K)
New scanner: Compare perpetual futures prices between exchanges
Strategy: Long on exchange A, short on exchange B when spread is wide
Sources:
- Binance Futures API (already partially connected via scanner_basis.py)
- OKX Perpetual Swaps (funding rate already in exchange_okx.py)
- Bybit Linear Perpetual (funding rate already in exchange_bybit.py)

Fields:
- type: "K"
- scanner_id: "K-FUTURES-FUTURES"
- asset, long_exchange, short_exchange
- long_price, short_price, spread_pct
- long_funding_rate, short_funding_rate
- net_funding_8h, annualized_pct
- edge_net (spread + funding differential)

### 2.4 — Network Status Checker
Before recommending cross-platform transfers, verify:
- Is USDT withdrawal open on source exchange?
- Is USDT deposit open on destination exchange?
- Which network is cheapest? (TRC20 vs ERC20 vs BEP20)
- Current withdrawal fee on each network
- Estimated arrival time

Sources:
- Binance: GET /sapi/v1/capital/config/getall (needs API key)
- OKX: GET /api/v5/asset/currencies
- Bybit: GET /v5/asset/coin/query-info

---

## CATEGORY 3: INTELLIGENCE LAYER (Priority: MEDIUM)

### 3.1 — Spread Lifetime Tracking
For each opportunity detected:
- When did it first appear? (first_seen timestamp)
- When did it peak? (max_edge timestamp)
- When did it close? (last_seen when edge < threshold)
- Duration in minutes
- Build database of spread lifetimes per scanner type

Implementation:
- New SQLite table: spread_lifetimes
- Columns: opp_id, scanner_type, asset, first_seen, peak_time, peak_edge, last_seen, duration_min
- Update on each engine run: check if previous opportunities still exist
- Dashboard shows: "Average MXN P2P spread lasts 45 minutes"

### 3.2 — Historical Pattern Analyzer
Tool that reads all opportunities.jsonl and produces:
- Best hours by scanner (heatmap data)
- Best days of week
- Spread width distribution
- Trend analysis (getting better or worse over time)
- Correlation with BTC price / Fear & Greed / volume

Output: JSON file that the Streamlit dashboard reads for charts

### 3.3 — Counterparty Intelligence (P2P)
Track Binance P2P traders over time:
- Which sellers consistently have the lowest prices?
- Which buyers consistently pay the most?
- Completion rate trends
- Payment method preferences
- "Recommended counterparties" list

Storage: SQLite table tracking ad data over time

---

## CATEGORY 4: OPERATIONAL TOOLS (Priority: MEDIUM)

### 4.1 — In-Dashboard Journal
Not a separate command — integrated into the Streamlit dashboard:
- "Add note" button always visible
- Notes appear in sidebar with timestamps
- Tags: #observation #trade #idea #risk
- Searchable history
- Export to markdown

### 4.2 — Visual P&L
Charts in the dashboard (using Plotly):
- Cumulative P&L line chart (daily)
- Trade-by-trade waterfall chart
- Edge distribution histogram
- Capital growth projection
- Win/loss ratio donut chart

Data source: nightwing_agent/storage/ledger/trades.jsonl
Plus: record_manual_trade.py writes here too

### 4.3 — Pre-Operation Checklist (automated)
Before each trading session, verify:
- [ ] Batman is running and fresh (< 30 min old)
- [ ] Nightwing is running
- [ ] Internet connection stable
- [ ] Binance P2P is accessible
- [ ] SPEI hours (05:00-23:30 Mexico City)
- [ ] No circuit breaker triggered
- [ ] Capital balance confirmed
- All shown as green/red checks in dashboard

---

## BUILD ORDER (Claude Code tasks)

### Sprint 1 (Days 1-3): Dashboard Foundation
1. Create dashboard/ directory structure
2. Build Streamlit app with 6 pages
3. Live screener reading from opportunities.jsonl
4. P&L dashboard reading from trades.jsonl
5. Scanner status from latest.json
6. Deploy locally: streamlit run dashboard/app.py

### Sprint 2 (Days 4-6): Expanded Scanning
7. Scanner D: add 17 more coins
8. Scanner K: futures vs futures (Binance/OKX/Bybit)
9. Integrate both into engine.py
10. Tests for new scanners

### Sprint 3 (Days 7-9): DEX Scanner
11. Scanner J: Uniswap/PancakeSwap/Raydium price fetching
12. CEX vs DEX comparison logic
13. Gas fee estimation
14. Integrate into engine.py
15. Tests

### Sprint 4 (Days 10-12): Intelligence
16. Spread lifetime tracking (SQLite)
17. Historical pattern analyzer
18. Heatmap data generation
19. Dashboard: historical patterns page
20. Dashboard: trading cockpit with notes

### Sprint 5 (Days 13-14): Polish
21. Pre-operation checklist in dashboard
22. Network status checker
23. All dashboard pages connected and tested
24. CLAUDE.md updated with new architecture
25. Full system test: run all scanners + dashboard

---

## FILE STRUCTURE (new files)

```
~/Projects/batcave/batman_flow_engine/
├── dashboard/
│   ├── app.py                    # Streamlit main app
│   ├── pages/
│   │   ├── 1_live_screener.py    # Real-time spreads table
│   │   ├── 2_pnl_dashboard.py    # P&L charts
│   │   ├── 3_scanner_status.py   # System health
│   │   ├── 4_patterns.py         # Historical analysis
│   │   ├── 5_trade_cockpit.py    # Execute trades
│   │   └── 6_journal.py          # Notes & journal
│   ├── components/
│   │   ├── charts.py             # Plotly chart builders
│   │   ├── tables.py             # Data table formatters
│   │   └── utils.py              # Shared dashboard utilities
│   └── static/
│       └── style.css             # Custom styling
├── core/
│   ├── scanner_dex.py            # NEW: Scanner J (DEX vs CEX)
│   ├── scanner_futures_futures.py # NEW: Scanner K (Futures vs Futures)
│   ├── network_status.py         # NEW: Withdrawal/deposit status
│   ├── spread_tracker.py         # NEW: Spread lifetime tracking
│   └── pattern_analyzer.py       # NEW: Historical patterns
└── tools/
    └── trade_now.py              # Already built
```

---

## WHAT THIS GIVES YOU

When complete, you open your browser to localhost:8501 and see:
- A table of ALL opportunities across ALL scanners (like ArbitrageScanner)
- Your P&L with charts
- Historical patterns (best hours to trade)
- A cockpit that says "buy here, sell here, you earn this"
- A journal to take notes while operating
- System health overview

Plus things ArbitrageScanner DOESN'T have:
- P2P LATAM intelligence
- Compliance engine
- Security controls
- Local AI analysis
- $0/month cost

This is your 100%.
