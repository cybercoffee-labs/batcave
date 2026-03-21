import yaml
import pandas as pd
import streamlit as st
import plotly.express as px

from core.equities import equity_metrics, returns_matrix
from core.crypto import crypto_metrics
from core.flows import flow_score_equity, flow_score_crypto
from core.correlations import rolling_corr_stress, top_corr_edges
from core.portfolio import portfolio_projection
from core.news_intel import narrative_intensity

st.set_page_config(page_title="🦇 Batman Flow Engine", layout="wide")


@st.cache_data(ttl=120)
def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


cfg = load_config()

st.title("🦇 Batman Flow Intelligence Engine — Flujos / Liquidez / Estrés / Narrativa")

# -------------------------
# NEWS / NARRATIVE INTEL
# -------------------------
if cfg.get("news_intel", {}).get("enabled", False):
    with st.expander("🗞️ Narrative Intel (public index) — últimos eventos", expanded=True):
        kws = cfg["news_intel"]["keywords"]
        lookback = int(cfg["news_intel"]["lookback_hours"])
        maxrec = int(cfg["news_intel"]["max_records"])
        if st.button("Actualizar narrativa"):
            st.cache_data.clear()
        try:
            ni = narrative_intensity(kws, lookback_hours=lookback, max_records=maxrec)
            st.metric("Total hits (lookback)", ni["total_hits"])
            st.json(ni["by_keyword"])
            st.caption("Muestras (3 por keyword, si hay):")
            st.json(ni["samples"])
        except Exception as e:
            st.warning(f"Narrative intel no disponible ahora: {e}")

st.divider()

# -------------------------
# EQUITIES
# -------------------------
eq_list = cfg["watchlists"]["equities"]
params = cfg["signals"]["windows"]
th = cfg["signals"]["thresholds"]

with st.spinner("Cargando equities/ETFs..."):
    eq_rows = []
    for t in eq_list:
        m = equity_metrics(t, vol_z_window=int(params["vol_z_window"]), rvol_window=int(params["rvol_window"]))
        if m.get("status", "").startswith("ok"):
            m["flow_score"] = flow_score_equity(
                m.get("vol_z", 0.0), m.get("rvol", 1.0), m.get("rv20_ann", 0.0), m.get("dollar_vol", 1.0)
            )
        eq_rows.append(m)
    eq_df = pd.DataFrame(eq_rows)

# -------------------------
# CRYPTO
# -------------------------
cr_list = cfg["watchlists"]["crypto"]
with st.spinner("Cargando crypto..."):
    cr_rows = []
    for s in cr_list:
        m = crypto_metrics(s)
        if m.get("status") == "ok":
            m["flow_score"] = flow_score_crypto(
                m.get("spread", 0.0), m.get("depth_0_5pct", 1.0), m.get("rv_ann", 0.0), m.get("dollar_vol_1h", 1.0)
            )
        cr_rows.append(m)
    cr_df = pd.DataFrame(cr_rows)

c1, c2 = st.columns([1, 1])

with c1:
    st.subheader("Equities/ETFs — Ranking FlowScore")
    if not eq_df.empty:
        show = eq_df.sort_values("flow_score", ascending=False, na_position="last")
        st.dataframe(show, use_container_width=True)
        hot = show[
            (show["vol_z"].fillna(0) >= float(th["vol_z_hot"]))
            | (show["flow_score"].fillna(0) >= float(th["flow_score_hot"]))
        ]
        st.markdown("**Hot (anomalía / flujo alto)**")
        st.dataframe(hot, use_container_width=True)

with c2:
    st.subheader("Crypto — Liquidez (spread/depth) + FlowScore")
    if not cr_df.empty:
        show = cr_df.sort_values("flow_score", ascending=False, na_position="last")
        st.dataframe(show, use_container_width=True)

st.divider()

# -------------------------
# CORRELATION STRESS
# -------------------------
st.subheader("Estrés sistémico — Correlación promedio (rolling)")
rets = returns_matrix(eq_list, days="240d")
if not rets.empty:
    corr_window = int(params["corr_window"])
    stress = rolling_corr_stress(rets, window=corr_window)
    st.json(stress)
    edges = top_corr_edges(rets, window=corr_window, k=20)
    st.caption("Top correlaciones (última ventana)")
    st.dataframe(edges, use_container_width=True)
else:
    st.info("No se pudo construir returns matrix (tickers inválidos o data insuficiente).")

st.divider()

# -------------------------
# PORTFOLIO PIE + PROJECTION
# -------------------------
st.subheader("Portafolio — pastel + proyección (rangos estadísticos)")
weights = cfg.get("portfolio", {}).get("weights", {})
if weights:
    p_df = pd.DataFrame([{"asset": k, "weight": v} for k, v in weights.items()])
    fig = px.pie(p_df, values="weight", names="asset")
    st.plotly_chart(fig, use_container_width=True)

    if not rets.empty:
        proj = portfolio_projection(rets, weights)
        st.json(proj)
else:
    st.info("Configura weights en config.yaml para habilitar el pastel y proyección.")
