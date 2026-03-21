"""📈 Live Screener — Real-time spreads table like ArbitrageScanner"""

import streamlit as st
import json
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path

st.set_page_config(page_title="📈 Live Screener", layout="wide")
st.title("📈 Live Screener")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OPPS_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"

SCANNER_NAMES = {
    "A": "Cross-Exchange CEX",
    "B": "Spot vs Futures",
    "C": "P2P LATAM",
    "D": "Multi-Exchange",
    "E": "Funding Rate",
    "F": "Cross-Currency P2P",
    "G": "Merchant Spread",
    "H": "Stablecoin Depeg",
    "I": "Cross-Platform MXN",
    "J": "DEX vs CEX",
    "K": "Futures vs Futures",
}

# Filters
col1, col2, col3 = st.columns(3)
with col1:
    hours = st.selectbox("Time window", [1, 4, 12, 24, 48], index=2)
with col2:
    viable_only = st.checkbox("Viable only", value=False)
with col3:
    scanner_filter = st.multiselect("Scanners", list(SCANNER_NAMES.keys()), default=list(SCANNER_NAMES.keys()))

# Load data
cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
rows = []

if OPPS_FILE.exists():
    for line in OPPS_FILE.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            if r.get("ts", "") > cutoff:
                if r.get("type") in scanner_filter:
                    if not viable_only or r.get("viable"):
                        rows.append(
                            {
                                "Time": r.get("ts", "")[:19].replace("T", " "),
                                "Scanner": f"[{r.get('type', '?')}] {SCANNER_NAMES.get(r.get('type', '?'), '?')}",
                                "Asset": r.get("asset", r.get("fiat", "USDT")),
                                "Buy @": r.get(
                                    "buy_price_mxn",
                                    r.get("p2p_buy_price", r.get("buy_price", r.get("best_buy_price", ""))),
                                ),
                                "Sell @": r.get(
                                    "sell_price_mxn",
                                    r.get("p2p_sell_price", r.get("sell_price", r.get("best_sell_price", ""))),
                                ),
                                "Edge %": r.get("edge_net", r.get("merchant_spread_pct", r.get("spread_pct", 0))),
                                "Viable": "✅" if r.get("viable") else "❌",
                                "Platform": r.get("buy_platform", r.get("venue", r.get("buy_exchange", ""))),
                            }
                        )
        except Exception:
            continue

if rows:
    df = pd.DataFrame(rows)
    df = df.sort_values("Edge %", ascending=False)

    # Color styling
    st.dataframe(
        df,
        use_container_width=True,
        height=600,
        column_config={
            "Edge %": st.column_config.NumberColumn(format="%.3f%%"),
            "Buy @": st.column_config.NumberColumn(format="%.4f"),
            "Sell @": st.column_config.NumberColumn(format="%.4f"),
        },
    )

    # Summary stats
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Opportunities", len(df))
    with col2:
        viable_ct = len(df[df["Viable"] == "✅"])
        st.metric("Viable", viable_ct)
    with col3:
        if len(df) > 0:
            best = df["Edge %"].max()
            st.metric("Best Edge", f"{best:+.3f}%")
    with col4:
        avg = df["Edge %"].mean()
        st.metric("Avg Edge", f"{avg:+.3f}%")

    # Best opportunity detail
    if viable_ct > 0:
        st.subheader("⭐ Best Opportunity Right Now")
        best_row = df[df["Viable"] == "✅"].iloc[0]
        st.json(best_row.to_dict())
else:
    st.warning(f"No opportunities in the last {hours} hours. Is Batman running?")

# Auto refresh
st.markdown("---")
if st.button("🔄 Refresh Now"):
    st.rerun()
