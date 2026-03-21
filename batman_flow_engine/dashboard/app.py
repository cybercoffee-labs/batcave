#!/usr/bin/env python3
"""
🦇 BATMAN LAB — Command Center
Streamlit Web Dashboard

Run: streamlit run dashboard/app.py
"""

import streamlit as st
from pathlib import Path
import json
from datetime import datetime, timezone

st.set_page_config(
    page_title="🦇 Batman Lab",
    page_icon="🦇",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent.parent
LATEST_FILE = BASE_DIR / "storage" / "latest.json"
OPPS_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"

# Sidebar
st.sidebar.title("🦇 Batman Lab")
st.sidebar.caption("Economic Flow Intelligence")

# Batman Health
health_icon = "🔴"
health_text = "OFFLINE"
age_min = 9999
if LATEST_FILE.exists():
    try:
        data = json.loads(LATEST_FILE.read_text())
        ts = datetime.fromisoformat(data["timestamp"])
        age_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60
        if age_min < 30:
            health_icon = "🟢"
            health_text = "ALIVE"
        else:
            health_icon = "🟡"
            health_text = "STALE"
    except Exception:
        pass

st.sidebar.markdown(f"{health_icon} **Batman:** {health_text} ({age_min:.0f} min ago)")

# Count opportunities
opp_count = 0
viable_count = 0
if OPPS_FILE.exists():
    try:
        lines = OPPS_FILE.read_text().strip().split("\n")
        opp_count = len(lines)
        for line in lines[-100:]:
            try:
                r = json.loads(line)
                if r.get("viable"):
                    viable_count += 1
            except Exception:
                pass
    except Exception:
        pass

st.sidebar.markdown(f"📊 **Opportunities:** {opp_count} total, {viable_count} viable (last 100)")
st.sidebar.divider()
st.sidebar.markdown("### Navigation")
st.sidebar.markdown("""
- 📈 **Live Screener** — Real-time spreads
- 💰 **P&L Dashboard** — Your profits
- 🔍 **Scanner Status** — System health
- 📊 **Patterns** — Historical analysis
- 🎯 **Trade Cockpit** — Execute trades
- 📓 **Journal** — Notes & observations
""")

# Main page
st.title("🦇 Batman Lab — Command Center")
st.markdown(f"**{datetime.now().strftime('%A %B %d, %Y — %H:%M')}**")

# Quick stats
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Batman Status", health_text)
with col2:
    st.metric("Scanners Active", "11")
with col3:
    st.metric("Exchanges", "7 CEX + 3 DEX")
with col4:
    st.metric("Total Opportunities", opp_count)

st.divider()

# Latest opportunities summary
st.subheader("Latest Scanner Results")

if OPPS_FILE.exists():
    try:
        lines = OPPS_FILE.read_text().strip().split("\n")
        recent = []
        for line in lines[-50:]:
            try:
                recent.append(json.loads(line))
            except Exception:
                pass

        if recent:
            # Group by type
            by_type = {}
            for o in recent:
                t = o.get("type", "?")
                by_type.setdefault(t, []).append(o)

            scanner_names = {
                "A": "Cross-Exchange CEX",
                "B": "Spot vs Futures",
                "C": "P2P LATAM Premium",
                "D": "Multi-Exchange (20 coins)",
                "E": "Funding Rate",
                "F": "Cross-Currency P2P",
                "G": "Merchant Spread",
                "H": "Stablecoin Depeg",
                "I": "Cross-Platform MXN",
                "J": "DEX vs CEX",
                "K": "Futures vs Futures",
            }

            for scanner_type in sorted(by_type.keys()):
                opps = by_type[scanner_type]
                name = scanner_names.get(scanner_type, f"Scanner {scanner_type}")
                viable = [o for o in opps if o.get("viable")]
                edges = [o.get("edge_net", 0) for o in opps if o.get("edge_net") is not None]
                avg_edge = sum(edges) / len(edges) if edges else 0

                icon = "✅" if viable else "⚪"
                st.markdown(
                    f"{icon} **[{scanner_type}] {name}** — {len(opps)} detected, {len(viable)} viable, avg edge: {avg_edge:+.3f}%"
                )
    except Exception as e:
        st.error(f"Error reading opportunities: {e}")
else:
    st.info("No opportunities data yet. Start Batman: `python tools/run_loop.py`")

st.divider()
st.caption("Navigate using the sidebar pages for detailed views.")
