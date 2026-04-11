"""🔍 Scanner Status — System health overview"""

import streamlit as st
import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

st.set_page_config(page_title="🔍 Scanner Status", layout="wide")
st.title("🔍 Scanner Status")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LATEST_FILE = BASE_DIR / "storage" / "latest.json"
OPPS_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"
ENGINE_LOG = BASE_DIR / "engine.log"

SCANNERS = {
    "A": {"name": "Cross-Exchange CEX", "desc": "Binance vs OKX vs Bybit"},
    "B": {"name": "Spot vs Futures", "desc": "Basis arbitrage"},
    "C": {"name": "P2P LATAM Premium", "desc": "USDT/MXN, ARS, COP, VES"},
    "D": {"name": "Multi-Exchange", "desc": "20 coins across 7 exchanges"},
    "E": {"name": "Funding Rate", "desc": "Perpetual funding opportunities"},
    "F": {"name": "Cross-Currency P2P", "desc": "MXN↔ARS cross-currency"},
    "G": {"name": "Merchant Spread", "desc": "P2P buy/sell spread"},
    "H": {"name": "Stablecoin Depeg", "desc": "USDT/USDC/DAI deviations"},
    "I": {"name": "Cross-Platform MXN", "desc": "Binance vs Bitso vs OKX vs Bybit"},
    "J": {"name": "DEX vs CEX", "desc": "Uniswap/PancakeSwap vs exchanges"},
    "K": {"name": "Futures vs Futures", "desc": "Perp spread between exchanges"},
}

# Batman Engine Health
st.subheader("Batman Engine")
col1, col2, col3, col4 = st.columns(4)

if LATEST_FILE.exists():
    try:
        data = json.loads(LATEST_FILE.read_text())
        ts = datetime.fromisoformat(data["timestamp"])
        age = (datetime.now(timezone.utc) - ts).total_seconds() / 60

        with col1:
            status = "🟢 ALIVE" if age < 30 else "🟡 STALE" if age < 60 else "🔴 DEAD"
            st.metric("Status", status)
        with col2:
            st.metric("Last Run", f"{age:.0f} min ago")
        with col3:
            dq = data.get("data_quality", {}).get("dq_score", 0)
            st.metric("Data Quality", f"{dq*100:.0f}%")
        with col4:
            regime = data.get("stress", {}).get("regime", {}).get("label", "?")
            st.metric("Regime", regime)
    except Exception as e:
        st.error(f"Error reading latest.json: {e}")
else:
    for c in [col1, col2, col3, col4]:
        with c:
            st.metric("Status", "NOT RUNNING")

# Process check
st.subheader("Running Processes")
try:
    result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
    python_procs = [line for line in result.stdout.split("\n") if "python" in line and "grep" not in line]
    batman_procs = [line for line in python_procs if "run_loop" in line or "agent.py" in line]

    if batman_procs:
        for p in batman_procs:
            parts = p.split()
            pid = parts[1] if len(parts) > 1 else "?"
            cmd = " ".join(parts[10:]) if len(parts) > 10 else "?"
            if "run_loop" in p:
                st.success(f"🦇 Batman (PID {pid}): `{cmd}`")
            elif "agent.py" in p:
                st.success(f"🦅 Nightwing (PID {pid}): `{cmd}`")
    else:
        st.warning("No Batman/Nightwing processes found. Start them:")
        st.code(
            "cd ~/Projects/batcave/batman_flow_engine && nohup python tools/run_loop.py > storage/logs/overnight.log 2>&1 &"
        )
except Exception:
    st.info("Cannot check processes (normal on some systems)")

# Scanner-by-scanner status
st.subheader("Scanner Status (last 12h)")
cutoff = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()

scanner_stats = {}
if OPPS_FILE.exists():
    for line in OPPS_FILE.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            if r.get("ts", "") > cutoff:
                t = r.get("type", "?")
                scanner_stats.setdefault(t, {"count": 0, "viable": 0, "edges": [], "last_ts": ""})
                scanner_stats[t]["count"] += 1
                if r.get("viable"):
                    scanner_stats[t]["viable"] += 1
                if r.get("edge_net") is not None:
                    scanner_stats[t]["edges"].append(r["edge_net"])
                scanner_stats[t]["last_ts"] = r.get("ts", "")
        except Exception:
            continue

for scanner_id, info in SCANNERS.items():
    stats = scanner_stats.get(scanner_id, {"count": 0, "viable": 0, "edges": [], "last_ts": "Never"})
    avg_edge = sum(stats["edges"]) / len(stats["edges"]) if stats["edges"] else 0
    icon = "✅" if stats["viable"] > 0 else "⚪" if stats["count"] > 0 else "❌"

    with st.expander(f"{icon} [{scanner_id}] {info['name']} — {stats['count']} detected, {stats['viable']} viable"):
        st.markdown(f"**Description:** {info['desc']}")
        st.markdown(f"**Opportunities:** {stats['count']}")
        st.markdown(f"**Viable:** {stats['viable']}")
        st.markdown(f"**Avg Edge:** {avg_edge:+.3f}%")
        st.markdown(f"**Last seen:** {stats['last_ts'][:19] if stats['last_ts'] else 'Never'}")

# Engine log tail
st.subheader("Recent Engine Log")
if ENGINE_LOG.exists():
    try:
        lines = ENGINE_LOG.read_text().strip().split("\n")[-20:]
        st.code("\n".join(lines), language="log")
    except Exception:
        st.info("Cannot read engine log")

if st.button("🔄 Refresh"):
    st.rerun()
