# 🦇 Batman Lab — Economic Flow Intelligence System

![Tests](https://img.shields.io/badge/tests-383%2B%20passing-brightgreen)
![Scanners](https://img.shields.io/badge/scanners-11-blue)
![Exchanges](https://img.shields.io/badge/exchanges-7%20CEX%20%2B%203%20DEX-orange)
![License](https://img.shields.io/badge/license-private-red)

## What is this?

Batman Lab is a self-hosted financial intelligence system that scans crypto markets across 11 strategies, 20+ coins, 7 centralized exchanges, and 3 DEX protocols. It detects price inefficiencies in real-time and provides a web dashboard for manual trading operations.

**This is NOT a trading bot.** It's a command center for a human operator.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    BATMAN (Intelligence)                  │
│  11 Scanners (A-K) → ALFRED (DQ) → HARVEY (Signals DB)  │
│  BARBARA (AI) → GORDON (Security) → LUCIUS (Compliance)  │
└──────────────────────┬──────────────────────────────────┘
                       │ opportunities.jsonl
┌──────────────────────▼──────────────────────────────────┐
│                   NIGHTWING (Execution)                   │
│  Bridge → Dedup → GORDON → Decision → HARVEY (Ledger)    │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   DASHBOARD (Web UI)                      │
│  Live Screener │ P&L Charts │ Patterns │ Trade Cockpit   │
└─────────────────────────────────────────────────────────┘
```

## 11 Scanners

| ID | Name | Strategy |
|----|------|----------|
| A | Cross-Exchange | Same coin, different CEX |
| B | Basis | Spot vs Futures spread |
| C | P2P LATAM | USDT/MXN, ARS, COP, VES premiums |
| D | Multi-Exchange | 20 coins × 5 exchanges |
| E | Funding Rate | Perpetual funding opportunities |
| F | Cross-Currency | MXN↔ARS P2P routes |
| G | Merchant Spread | P2P buy/sell spread |
| H | Stablecoin Depeg | USDT/USDC/DAI deviations |
| I | Cross-Platform MXN | Binance vs Bitso vs OKX vs Bybit |
| J | DEX vs CEX | Uniswap/PancakeSwap vs Binance |
| K | Futures vs Futures | Perp spread between exchanges |

## Quick Start

```bash
# Clone and install
git clone <repo-url> && cd batcave
make install

# Start everything
make run        # Batman + Nightwing in background
make dashboard  # Web UI at localhost:8501

# Or with Docker
make docker-up  # Everything at localhost:8501
```

## Commands

```bash
make test       # Run all 383+ tests
make lint       # Lint both repos
make briefing   # Morning market briefing
make trade      # Trade cockpit
make status     # Check system health
make stop       # Stop all processes
```

## Tech Stack

- **Language:** Python 3.13
- **Data:** SQLite + JSONL (append-only)
- **AI:** Ollama (llama3.2:3b) local
- **Dashboard:** Streamlit + Plotly
- **APIs:** Binance, OKX, Bybit, Bitso, KuCoin, MEXC, DexScreener (all public, no keys needed)
- **CI/CD:** GitHub Actions
- **Container:** Docker + Docker Compose
- **Testing:** pytest (383+ tests)
- **Linting:** ruff + mypy

## Project Structure

```
batcave/
├── batman_flow_engine/    # Intelligence brain (11 scanners)
│   ├── core/              # 35 modules (scanners, exchanges, analysis)
│   ├── dashboard/         # Streamlit web UI (6 pages)
│   ├── tools/             # CLI tools (briefing, journal, trade)
│   ├── tests/             # 228+ tests
│   └── storage/           # Data (SQLite, JSONL, reports)
├── nightwing_agent/       # Execution agent (P2P LATAM)
│   ├── core/              # Bridge, Gordon, Harvey, Lucius
│   ├── tests/             # 155+ tests
│   └── storage/           # Trade ledger
├── .github/workflows/     # CI/CD pipeline
├── Dockerfile             # Multi-stage build
├── docker-compose.yml     # Full orchestration
├── Makefile               # Convenience commands
└── pyproject.toml         # Linting + typing config
```

## Support Modules

| Module | Character | Role |
|--------|-----------|------|
| ALFRED | Alfred Pennyworth | Data quality scoring |
| BARBARA | Barbara Gordon | AI market analysis (Ollama) |
| GORDON | Commissioner Gordon | Security, kill switch, circuit breaker |
| HARVEY | Harvey Dent | Trade ledger + P&L tracking |
| LUCIUS | Lucius Fox | Compliance (SPEI hours, jurisdiction rules) |

---

*Built by Erick Posselt | Cancún, Mexico | 2026*
