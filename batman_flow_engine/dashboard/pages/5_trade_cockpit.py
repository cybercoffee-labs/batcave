"""🎯 Trade Cockpit — Execute trades with step-by-step instructions"""

import streamlit as st
import json
import ssl
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

st.set_page_config(page_title="🎯 Trade Cockpit", layout="wide")
st.title("🎯 Trade Cockpit")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
NIGHTWING_DIR = BASE_DIR.parent / "nightwing_agent"
LEDGER_FILE = NIGHTWING_DIR / "storage" / "ledger" / "trades.jsonl"
JOURNAL_DIR = BASE_DIR / "journal"

# Capital input
capital_usd = st.sidebar.number_input("Your capital (USD)", min_value=1.0, max_value=100000.0, value=28.0, step=1.0)


@st.cache_data(ttl=60)
def fetch_binance_p2p(trade_type, fiat="MXN", rows=5):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    payload = json.dumps(
        {
            "fiat": fiat,
            "page": 1,
            "rows": rows,
            "tradeType": trade_type,
            "asset": "USDT",
            "publisherType": None,
        }
    ).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "batman-lab/1.0"}
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            data = json.loads(resp.read().decode())
        return data.get("data", [])
    except Exception:
        return []


def parse_ads(ads):
    parsed = []
    for ad in ads:
        adv = ad.get("adv", {})
        advertiser = ad.get("advertiser", {})
        methods = [m.get("tradeMethodName", "?") for m in adv.get("tradeMethods", [])]
        parsed.append(
            {
                "price": float(adv.get("price", 0)),
                "available": float(adv.get("tradableQuantity", 0)),
                "min_mxn": float(adv.get("minSingleTransAmount", 0)),
                "max_mxn": float(adv.get("dynamicMaxSingleTransAmount", 0)),
                "nick": advertiser.get("nickName", "?"),
                "orders": advertiser.get("monthOrderCount", 0),
                "rate": float(advertiser.get("monthFinishRate", 0)) * 100,
                "methods": methods,
            }
        )
    return parsed


# Fetch live data
with st.spinner("Scanning Binance P2P..."):
    sell_ads = parse_ads(fetch_binance_p2p("SELL"))  # You BUY from sellers
    buy_ads = parse_ads(fetch_binance_p2p("BUY"))  # You SELL to buyers

if not sell_ads or not buy_ads:
    st.error("Cannot fetch Binance P2P data. Check your internet.")
    st.stop()

best_buy = sell_ads[0]  # Cheapest seller
best_sell = buy_ads[0]  # Most expensive buyer

buy_price = best_buy["price"]
sell_price = best_sell["price"]
spread_pct = ((sell_price - buy_price) / buy_price) * 100

capital_mxn = capital_usd * buy_price
usdt_amount = capital_mxn / buy_price
revenue_mxn = usdt_amount * sell_price
profit_mxn = revenue_mxn - capital_mxn
profit_usd = profit_mxn / sell_price

# Signal
if spread_pct > 0.15:
    st.success(f"### 🟢 OPPORTUNITY ACTIVE — Edge: {spread_pct:+.3f}%")
else:
    st.error(f"### 🔴 NO OPPORTUNITY — Edge: {spread_pct:+.3f}% (too low)")

# Prices
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("🟢 BUY USDT @", f"${buy_price:.2f} MXN", help="Cheapest seller")
with col2:
    st.metric("🔴 SELL USDT @", f"${sell_price:.2f} MXN", help="Best buyer")
with col3:
    st.metric("💰 Profit", f"${profit_mxn:.2f} MXN", delta=f"${profit_usd:.2f} USD")

st.divider()

# Step by step
st.subheader("📋 Step by Step")

if spread_pct > 0.15:
    st.markdown(f"""
    **STEP 1:** Go to [Binance P2P](https://p2p.binance.com) → USDT/MXN → **Buy** tab
    - Look for seller: **{best_buy['nick']}** at **${buy_price:.2f} MXN**
    - Pay **${capital_mxn:.0f} MXN** → Receive **~{usdt_amount:.1f} USDT**
    - Methods: {', '.join(best_buy['methods'][:3])}
    - Seller stats: {best_buy['orders']} trades, {best_buy['rate']:.0f}% completion

    **STEP 2:** Go to Binance P2P → USDT/MXN → **Sell** tab
    - Look for buyer: **{best_sell['nick']}** at **${sell_price:.2f} MXN**
    - Sell **{usdt_amount:.1f} USDT** → Receive **${revenue_mxn:.0f} MXN**
    - Methods: {', '.join(best_sell['methods'][:3])}
    - Buyer stats: {best_sell['orders']} trades, {best_sell['rate']:.0f}% completion

    **RESULT:** You paid ${capital_mxn:.2f} MXN → Received ${revenue_mxn:.2f} MXN = **+${profit_mxn:.2f} MXN profit**
    """)
else:
    st.warning("Wait for a better opportunity. Best hours: 9-11 AM and 7-9 PM Mexico time.")

st.divider()

# Record trade
st.subheader("📝 Record This Trade")
with st.form("record_trade"):
    col1, col2 = st.columns(2)
    with col1:
        actual_buy = st.number_input("Actual buy price (MXN)", value=buy_price, format="%.4f")
        actual_sell = st.number_input("Actual sell price (MXN)", value=sell_price, format="%.4f")
    with col2:
        actual_amount = st.number_input("Amount (USDT)", value=usdt_amount, format="%.1f")
        notes = st.text_input("Notes", placeholder="First trade! Took 8 minutes.")

    submitted = st.form_submit_button("✅ Record Trade")
    if submitted:
        actual_pnl = actual_amount * (actual_sell - actual_buy)
        actual_edge = ((actual_sell - actual_buy) / actual_buy) * 100

        trade = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "asset": "USDT",
            "pair": "USDT/MXN",
            "exchange": "binance_p2p",
            "buy_price": actual_buy,
            "sell_price": actual_sell,
            "amount_usdt": actual_amount,
            "pnl_mxn": round(actual_pnl, 4),
            "pnl_usd": round(actual_pnl / actual_sell, 4),
            "edge_pct": round(actual_edge, 4),
            "notes": notes,
        }

        LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER_FILE, "a") as f:
            f.write(json.dumps(trade) + "\n")

        st.success(f"Trade recorded! P&L: ${actual_pnl:.2f} MXN ({actual_edge:+.3f}%)")

        # Also write to journal
        JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        today_file = JOURNAL_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.md"
        note_line = f"\n- **[{datetime.now().strftime('%H:%M')}]** Trade: Buy@{actual_buy} Sell@{actual_sell} Edge:{actual_edge:+.3f}% P&L:${actual_pnl:.2f} MXN — {notes}\n"
        with open(today_file, "a") as f:
            f.write(note_line)

st.divider()

# All ads table
st.subheader("All Available Ads")
tab1, tab2 = st.tabs(["Buy USDT from (sellers)", "Sell USDT to (buyers)"])

with tab1:
    for i, ad in enumerate(sell_ads):
        st.markdown(
            f"{i+1}. **${ad['price']:.2f}** — {ad['nick']} ({ad['orders']} trades, {ad['rate']:.0f}%) — {', '.join(ad['methods'][:2])} — {ad['available']:.0f} USDT avail"
        )

with tab2:
    for i, ad in enumerate(buy_ads):
        st.markdown(
            f"{i+1}. **${ad['price']:.2f}** — {ad['nick']} ({ad['orders']} trades, {ad['rate']:.0f}%) — {', '.join(ad['methods'][:2])} — {ad['available']:.0f} USDT avail"
        )

if st.button("🔄 Refresh Prices"):
    st.cache_data.clear()
    st.rerun()
