# 🦇 Batman Flow Intelligence Engine (v1)

Local, legal, public-data **flow/liquidity/narrative** monitor.

## What you get
- Equity/ETF: RVOL anomaly, volume Z, realized vol, dollar volume (liquidity proxy), composite FlowScore
- Crypto (Binance via ccxt): spread, depth, realized vol, dollar vol, composite FlowScore
- Correlation stress monitor (rolling window)
- Portfolio pie + scenario projection (daily/weekly/monthly ranges)
- News narrative intensity (public GDELT endpoints; optional)

## Quickstart (macOS)
```bash
chmod +x run.sh
./run.sh
```

## Notes
- This is **detection/forensics** (not autotrading).
- Projections are **statistical estimates** based on historical data; **not guarantees**.
- Some premium datasets (options OI, true ETF flows) are not included in v1.
