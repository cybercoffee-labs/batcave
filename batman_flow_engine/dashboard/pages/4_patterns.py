"""📊 Patterns — Historical analysis, best hours, heatmaps"""

import streamlit as st
import json
import pandas as pd
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="📊 Patterns", layout="wide")
st.title("📊 Historical Patterns")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OPPS_FILE = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"

SCANNER_NAMES = {
    "A": "Cross-Exchange",
    "B": "Basis",
    "C": "P2P LATAM",
    "D": "Multi-Exchange",
    "E": "Funding Rate",
    "F": "Cross-Currency",
    "G": "Merchant Spread",
    "H": "Depeg",
    "I": "Cross-Platform MXN",
    "J": "DEX vs CEX",
    "K": "Futures vs Futures",
}

# Load ALL data
all_opps = []
if OPPS_FILE.exists():
    for line in OPPS_FILE.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            r["_ts"] = datetime.fromisoformat(r["ts"].replace("Z", "+00:00")) if "ts" in r else None
            if r["_ts"]:
                r["_hour"] = r["_ts"].hour
                r["_dow"] = r["_ts"].strftime("%A")
                r["_date"] = r["_ts"].date()
                all_opps.append(r)
        except Exception:
            continue

if not all_opps:
    st.warning("Not enough data yet. Let Batman run for 24+ hours to see patterns.")
    st.stop()

df = pd.DataFrame(all_opps)
st.info(f"Analyzing {len(df)} opportunities from {df['_date'].min()} to {df['_date'].max()}")

# Filter
scanner_filter = st.multiselect("Filter by scanner", list(SCANNER_NAMES.keys()), default=["C", "G", "I"])
viable_only = st.checkbox("Viable only", value=True)

mask = df["type"].isin(scanner_filter)
if viable_only:
    mask = mask & (df.get("viable", False) == True)
filtered = df[mask]

if filtered.empty:
    st.warning("No data for selected filters.")
    st.stop()

st.divider()

# Best Hours Heatmap
st.subheader("Best Hours for Opportunities")
if "edge_net" in filtered.columns:
    hourly = filtered.groupby("_hour")["edge_net"].agg(["mean", "count"]).reset_index()
    hourly.columns = ["Hour (UTC)", "Avg Edge %", "Count"]

    col1, col2 = st.columns(2)
    with col1:
        st.bar_chart(hourly.set_index("Hour (UTC)")["Avg Edge %"])
        st.caption("Average edge by hour (UTC)")
    with col2:
        st.bar_chart(hourly.set_index("Hour (UTC)")["Count"])
        st.caption("Number of opportunities by hour")

    # Best hour
    if len(hourly) > 0:
        best_hour = hourly.loc[hourly["Avg Edge %"].idxmax()]
        st.success(
            f"⭐ Best hour: {int(best_hour['Hour (UTC)'])}:00 UTC — avg edge {best_hour['Avg Edge %']:+.3f}% ({int(best_hour['Count'])} opportunities)"
        )

st.divider()

# Day of Week
st.subheader("Best Days of Week")
if "edge_net" in filtered.columns:
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    daily = filtered.groupby("_dow")["edge_net"].agg(["mean", "count"]).reset_index()
    daily.columns = ["Day", "Avg Edge %", "Count"]
    daily["Day"] = pd.Categorical(daily["Day"], categories=day_order, ordered=True)
    daily = daily.sort_values("Day")

    st.bar_chart(daily.set_index("Day")["Avg Edge %"])

st.divider()

# Edge Distribution
st.subheader("Edge Distribution")
if "edge_net" in filtered.columns:
    edges = filtered["edge_net"].dropna()
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Min Edge", f"{edges.min():.3f}%")
    with col2:
        st.metric("Avg Edge", f"{edges.mean():.3f}%")
    with col3:
        st.metric("Max Edge", f"{edges.max():.3f}%")
    with col4:
        st.metric("Std Dev", f"{edges.std():.3f}%")

    st.line_chart(edges.reset_index(drop=True))

st.divider()

# Scanner comparison
st.subheader("Scanner Performance Comparison")
scanner_perf = (
    filtered.groupby("type")
    .agg(
        count=("type", "count"),
        viable=("viable", "sum") if "viable" in filtered.columns else ("type", "count"),
        avg_edge=("edge_net", "mean") if "edge_net" in filtered.columns else ("type", "count"),
    )
    .reset_index()
)
scanner_perf["name"] = scanner_perf["type"].map(SCANNER_NAMES)
st.dataframe(scanner_perf, use_container_width=True)

# Trend over time
st.subheader("Edge Trend Over Time")
if "edge_net" in filtered.columns and "_date" in filtered.columns:
    trend = filtered.groupby("_date")["edge_net"].mean().reset_index()
    trend.columns = ["Date", "Avg Edge %"]
    st.line_chart(trend.set_index("Date"))
    st.caption("Is the market getting tighter over time?")
