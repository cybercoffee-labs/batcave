"""💰 P&L Dashboard — Visual profit/loss tracking"""

import streamlit as st
import json
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="💰 P&L Dashboard", layout="wide")
st.title("💰 P&L Dashboard")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
NIGHTWING_DIR = BASE_DIR.parent / "nightwing_agent"
LEDGER_FILE = NIGHTWING_DIR / "storage" / "ledger" / "trades.jsonl"
JOURNAL_DIR = BASE_DIR / "journal"

# Load trades
trades = []
if LEDGER_FILE.exists():
    for line in LEDGER_FILE.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            trades.append(json.loads(line))
        except Exception:
            continue

if not trades:
    st.info(
        "No trades recorded yet. Use `python tools/record_manual_trade.py` or the Trade Cockpit to record your first trade."
    )
    st.markdown("### How to record a trade")
    st.code("cd ~/Projects/batcave/nightwing_agent\npython tools/record_manual_trade.py", language="bash")
    st.stop()

df = pd.DataFrame(trades)

# Parse timestamps
if "ts" in df.columns:
    df["date"] = pd.to_datetime(df["ts"]).dt.date
elif "timestamp" in df.columns:
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date

# Summary metrics
col1, col2, col3, col4 = st.columns(4)

total_pnl = df.get("pnl_usd", df.get("profit_usd", pd.Series([0]))).sum()
trade_count = len(df)
avg_edge = df.get("edge_pct", df.get("edge_net", pd.Series([0]))).mean()
win_count = len(df[df.get("pnl_usd", df.get("profit_usd", pd.Series([0]))) > 0])
win_rate = (win_count / trade_count * 100) if trade_count > 0 else 0

with col1:
    st.metric("Total P&L", f"${total_pnl:.2f} USD", delta=f"{total_pnl:+.2f}")
with col2:
    st.metric("Total Trades", trade_count)
with col3:
    st.metric("Win Rate", f"{win_rate:.0f}%")
with col4:
    st.metric("Avg Edge", f"{avg_edge:.3f}%")

st.divider()

# Cumulative P&L chart
st.subheader("Cumulative P&L")
if "pnl_usd" in df.columns or "profit_usd" in df.columns:
    pnl_col = "pnl_usd" if "pnl_usd" in df.columns else "profit_usd"
    df["cumulative_pnl"] = df[pnl_col].cumsum()
    st.line_chart(df.set_index(df.index)["cumulative_pnl"])

# Trade history table
st.subheader("Trade History")
display_cols = [
    c
    for c in [
        "ts",
        "timestamp",
        "asset",
        "pair",
        "exchange",
        "venue",
        "edge_net",
        "edge_pct",
        "pnl_usd",
        "profit_usd",
        "amount_usd",
    ]
    if c in df.columns
]
if display_cols:
    st.dataframe(df[display_cols].sort_index(ascending=False), use_container_width=True)
else:
    st.dataframe(df.sort_index(ascending=False), use_container_width=True)

# Daily summary
st.subheader("Daily Summary")
if "date" in df.columns:
    pnl_col = "pnl_usd" if "pnl_usd" in df.columns else "profit_usd"
    if pnl_col in df.columns:
        daily = (
            df.groupby("date")
            .agg(
                trades=(pnl_col, "count"),
                total_pnl=(pnl_col, "sum"),
                avg_pnl=(pnl_col, "mean"),
            )
            .reset_index()
        )
        st.dataframe(daily, use_container_width=True)
        st.bar_chart(daily.set_index("date")["total_pnl"])
