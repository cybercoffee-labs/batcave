# Batman Lab — Security Policy & Threat Model

## Critical Assets

| Asset | Classification | Protection |
|-------|---------------|------------|
| API Keys (Binance, OKX) | SECRET | .env only, never in code |
| Trade Ledger (trades.jsonl) | CONFIDENTIAL | Append-only, local storage |
| Opportunity Data (opportunities.jsonl) | INTERNAL | Append-only, local storage |
| BBVA/Bank Credentials | SECRET | Never stored in system |
| Personal KYC Data | PII | Never stored in system |

## Trust Boundaries

```
┌─────────────────────────────────────────────┐
│ TRUSTED: Local Machine (Mac Mini M4)         │
│  ├── Batman Engine                           │
│  ├── Nightwing Agent                         │
│  ├── Streamlit Dashboard                     │
│  ├── SQLite Database                         │
│  └── Ollama (BARBARA)                        │
├─────────────────────────────────────────────┤
│ SEMI-TRUSTED: APIs (read-only, public)       │
│  ├── Binance API (market data)               │
│  ├── OKX API (market data)                   │
│  ├── Bybit API (market data)                 │
│  ├── CoinGecko API (market data)             │
│  └── DexScreener API (DEX data)              │
├─────────────────────────────────────────────┤
│ UNTRUSTED: External                          │
│  ├── P2P Counterparties                      │
│  ├── Internet connectivity                   │
│  └── Third-party package updates             │
└─────────────────────────────────────────────┘
```

## Threat Scenarios

### T1: API Key Exposure
- **Risk:** API keys committed to git or logged
- **Control:** .gitignore excludes .env, CI scans for secrets
- **GORDON:** gordon_audit.py logs access but never keys

### T2: P2P Counterparty Fraud
- **Risk:** Counterparty marks payment as sent but doesn't pay
- **Control:** Binance escrow protects. Never release crypto without confirmed payment.
- **LUCIUS:** Compliance rules block trades outside SPEI hours

### T3: Data Manipulation
- **Risk:** Tampered opportunity data leads to bad trades
- **Control:** ALFRED dq_score validates data quality
- **GORDON:** Spread anomaly detection flags unusual prices
- **Scanner I:** Sanity check rejects prices >3% from reference

### T4: System Compromise
- **Risk:** Mac Mini compromised, attacker accesses exchange accounts
- **Control:** API keys are read-only by default. LIVE mode requires explicit flags.
- **GORDON:** Kill switch, circuit breaker, daily exposure limit

### T5: Dependency Supply Chain
- **Risk:** Malicious package update
- **Control:** requirements-lock.txt pins exact versions
- **Mitigation:** Review deps before updating, use pip audit

### T6: API Rate Limiting / IP Ban
- **Risk:** Too many requests get IP blocked
- **Control:** 20-min scan interval, retry with backoff
- **Scanner D:** Rate-limited across 20 coins × 5 exchanges

## GORDON Security Controls (Active)

| Control | Type | Location |
|---------|------|----------|
| Circuit Breaker | Preventive | nightwing_agent/core/gordon.py |
| Batman Heartbeat | Detective | nightwing_agent/core/gordon.py |
| Spread Anomaly Detection | Detective | nightwing_agent/core/gordon.py |
| Daily Exposure Limit | Preventive | nightwing_agent/core/gordon.py |
| Auto-pause (3 blocks) | Preventive | nightwing_agent/agent.py |
| Dedup by opp_id | Preventive | nightwing_agent/agent.py |
| Sanity Check (Scanner I) | Detective | batman_flow_engine/core/scanner_cross_platform_mxn.py |
| Observe-only default | Preventive | config/settings.yaml |

## Incident Response

### Severity Levels
- **SEV1 (Critical):** Live trade executing incorrectly → GORDON kill switch
- **SEV2 (High):** Data quality degraded → ALFRED breaker, regime = DATA_DEGRADED
- **SEV3 (Medium):** Scanner failure → Logged, other scanners continue
- **SEV4 (Low):** API timeout → Retry with backoff

### Response Procedure
1. GORDON auto-activates kill switch for SEV1
2. Check `storage/logs/gordon_audit.jsonl` for security events
3. Check `engine.log` for scanner errors
4. If data issue: verify with `python tools/trade_now.py` (live prices)
5. Document in journal: `python tools/trading_journal.py --note "incident details"`

## Reporting Security Issues

Contact: Erick Posselt (project owner)
Do NOT create public GitHub issues for security vulnerabilities.
