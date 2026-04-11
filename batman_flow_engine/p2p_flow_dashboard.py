import sqlite3
import pandas as pd
import streamlit as st

DB_PATH = "storage/batman.db"

conn = sqlite3.connect(DB_PATH)

query = """
SELECT
  json_extract(raw_json,'$.market') AS market,
  COUNT(*) AS signals,
  ROUND(
    100.0 * SUM(CASE WHEN json_extract(raw_json,'$.viable')=1 THEN 1 ELSE 0 END)/COUNT(*)
  ,2) AS viable_pct,
  ROUND(AVG(json_extract(raw_json,'$.edge_net')),3) AS avg_edge,
  ROUND(AVG(json_extract(raw_json,'$.depth_estimate')),0) AS avg_depth,
  ROUND(AVG(json_extract(raw_json,'$.merchant_count')),1) AS merchants
FROM signals
WHERE scanner_id='C-P2P-LATAM'
GROUP BY market
"""

df = pd.read_sql(query, conn)

df["flow_score"] = (df["avg_edge"] * df["avg_depth"]) / 1000

st.title("BATCAVE LATAM P2P FLOW MAP")

st.subheader("Market Overview")
st.dataframe(df)

st.subheader("FlowScore by Market")
st.bar_chart(df.set_index("market")["flow_score"])

st.subheader("Edge by Market")
st.bar_chart(df.set_index("market")["avg_edge"])

st.subheader("Liquidity by Market")
st.bar_chart(df.set_index("market")["avg_depth"])
