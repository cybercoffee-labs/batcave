#!/usr/bin/env python3
"""
BATMAN LAB — TRADING ASSISTANT (SIMPLE MODE)

This is your cockpit. Run it, it tells you EXACTLY what to do.
No noise, no scrolling, no confusion.

Usage:
  python tools/trade_now.py          # Show current opportunity
  python tools/trade_now.py --watch  # Auto-refresh every 60 seconds
  python tools/trade_now.py --explain # Show detailed breakdown
"""

import json
import ssl
import sys
import time
import os
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def clear_screen():
    os.system("clear" if os.name != "nt" else "cls")


def fetch_binance_p2p(trade_type: str, fiat: str = "MXN", rows: int = 5):
    """Fetch Binance P2P ads. trade_type: BUY or SELL."""
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


def get_live_prices():
    """Get current buy/sell prices from Binance P2P."""

    # SELL ads = people selling USDT = YOU BUY from them (cheapest = best for you)
    sell_ads = fetch_binance_p2p("SELL")
    # BUY ads = people buying USDT = YOU SELL to them (most expensive = best for you)
    buy_ads = fetch_binance_p2p("BUY")

    buy_options = []
    for ad in sell_ads:
        adv = ad.get("adv", {})
        advertiser = ad.get("advertiser", {})
        price = float(adv.get("price", 0))
        available = float(adv.get("tradableQuantity", 0))
        min_order = float(adv.get("minSingleTransAmount", 0))
        max_order = float(adv.get("dynamicMaxSingleTransAmount", 0))
        nick = advertiser.get("nickName", "?")
        orders = advertiser.get("monthOrderCount", 0)
        rate = float(advertiser.get("monthFinishRate", 0)) * 100
        methods = [m.get("tradeMethodName", "?") for m in adv.get("tradeMethods", [])]

        buy_options.append(
            {
                "price": price,
                "available_usdt": available,
                "min_mxn": min_order,
                "max_mxn": max_order,
                "nick": nick,
                "orders": orders,
                "completion_rate": rate,
                "methods": methods,
            }
        )

    sell_options = []
    for ad in buy_ads:
        adv = ad.get("adv", {})
        advertiser = ad.get("advertiser", {})
        price = float(adv.get("price", 0))
        available = float(adv.get("tradableQuantity", 0))
        min_order = float(adv.get("minSingleTransAmount", 0))
        max_order = float(adv.get("dynamicMaxSingleTransAmount", 0))
        nick = advertiser.get("nickName", "?")
        orders = advertiser.get("monthOrderCount", 0)
        rate = float(advertiser.get("monthFinishRate", 0)) * 100
        methods = [m.get("tradeMethodName", "?") for m in adv.get("tradeMethods", [])]

        sell_options.append(
            {
                "price": price,
                "available_usdt": available,
                "min_mxn": min_order,
                "max_mxn": max_order,
                "nick": nick,
                "orders": orders,
                "completion_rate": rate,
                "methods": methods,
            }
        )

    return buy_options, sell_options


def display_trading_panel(capital_usd: float = 28.0, explain: bool = False):
    """Show the simple trading panel."""

    now = datetime.now()
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  🦇 BATMAN LAB — TRADING ASSISTANT                          ║
║  {now.strftime('%H:%M:%S')} — Tu capital: ${capital_usd:.0f} USD                         ║
╚══════════════════════════════════════════════════════════════╝
""")

    print("  Escaneando Binance P2P en vivo...")
    buy_options, sell_options = get_live_prices()

    if not buy_options or not sell_options:
        print("  ❌ Error: No se pudieron obtener precios. Revisa tu internet.")
        return

    # Best prices
    best_buy = buy_options[0]  # Cheapest seller (you buy cheap)
    best_sell = sell_options[0]  # Most expensive buyer (you sell expensive)

    buy_price = best_buy["price"]
    sell_price = best_sell["price"]

    spread = sell_price - buy_price
    spread_pct = (spread / buy_price) * 100

    capital_mxn = capital_usd * buy_price
    usdt_amount = capital_mxn / buy_price
    revenue_mxn = usdt_amount * sell_price
    profit_mxn = revenue_mxn - capital_mxn
    profit_usd = profit_mxn / sell_price

    # Determine if viable
    viable = spread_pct > 0.15

    # ── SIGNAL ──
    if viable:
        signal = "🟢 OPORTUNIDAD ACTIVA"
        action_color = "\033[92m"  # Green
    else:
        signal = "🔴 SIN OPORTUNIDAD (spread negativo o muy bajo)"
        action_color = "\033[91m"  # Red

    reset = "\033[0m"

    print(f"""
{'═'*62}
  {signal}
{'═'*62}

  📊 PRECIOS EN VIVO (Binance P2P USDT/MXN)
  ───────────────────────────────────────────

  🟢 TÚ COMPRAS USDT a:  ${buy_price:.2f} MXN
     Vendedor: {best_buy['nick']} ({best_buy['orders']} trades, {best_buy['completion_rate']:.0f}%)
     Pago: {', '.join(best_buy['methods'][:3])}
     Mín: ${best_buy['min_mxn']:.0f} MXN | Disponible: {best_buy['available_usdt']:.0f} USDT

  🔴 TÚ VENDES USDT a:   ${sell_price:.2f} MXN
     Comprador: {best_sell['nick']} ({best_sell['orders']} trades, {best_sell['completion_rate']:.0f}%)
     Pago: {', '.join(best_sell['methods'][:3])}
     Mín: ${best_sell['min_mxn']:.0f} MXN | Quiere: {best_sell['available_usdt']:.0f} USDT

{'═'*62}
  💰 TU OPERACIÓN (con ${capital_usd:.0f} USD)
{'═'*62}
""")

    if viable:
        print(f"""  PASO 1: Ve a Binance P2P → USDT/MXN → pestaña "Comprar"
          Busca a "{best_buy['nick']}" o al precio ${buy_price:.2f}
          Paga ${capital_mxn:.0f} MXN → Recibes ~{usdt_amount:.1f} USDT

  PASO 2: Ve a Binance P2P → USDT/MXN → pestaña "Vender"
          Busca a "{best_sell['nick']}" o al precio ${sell_price:.2f}
          Vende tus {usdt_amount:.1f} USDT → Recibes ${revenue_mxn:.0f} MXN

  ─────────────────────────────────────────────
  Pagas:    ${capital_mxn:.2f} MXN
  Recibes:  ${revenue_mxn:.2f} MXN
  ─────────────────────────────────────────────
  GANANCIA: +${profit_mxn:.2f} MXN (+${profit_usd:.2f} USD)
  EDGE:     {spread_pct:+.3f}%
  TIEMPO:   ~5-10 minutos
  ─────────────────────────────────────────────
""")
    else:
        print(f"""  ⚠️  SPREAD: {spread_pct:+.3f}% — NO ES RENTABLE AHORA

  Comprarías a ${buy_price:.2f} y venderías a ${sell_price:.2f}
  Eso es {'-' if spread_pct < 0 else '+'}${abs(profit_mxn):.2f} MXN {'(PÉRDIDA)' if profit_mxn < 0 else '(muy bajo)'}

  👉 ESPERA. Batman te avisará cuando el spread suba.
  👉 Históricamente sube entre 9:00-11:00 AM y 7:00-9:00 PM
""")

    if explain:
        print(f"""
{'═'*62}
  📖 EXPLICACIÓN DETALLADA
{'═'*62}

  ¿Por qué funciona?
  Hay personas que NECESITAN pesos urgente → te venden USDT barato
  Hay personas que NECESITAN crypto urgente → te compran USDT caro
  Tú estás en el medio conectando a ambos → te quedas con la diferencia

  ¿Por qué el spread existe?
  - Urgencia: alguien necesita el dinero YA
  - Comodidad: prefieren P2P que ir al banco
  - Acceso: no tienen cuenta en Bitso/exchange
  - Método de pago: SPEI vs transferencia vs efectivo

  ¿Cuándo es mejor?
  - Mañana (9-11 AM): gente necesita pesos para el día
  - Noche (7-9 PM): gente compra crypto después del trabajo
  - Fines de semana: menos liquidez = spreads más amplios

  ¿Riesgos?
  - Contraparte no paga → Binance escrow protege (nunca sueltes sin confirmar)
  - Precio cambia → opera rápido, no dejes USDT "parado" mucho tiempo
  - Spread se cierra → no operes si el spread es < 0.2%
""")

    # Show top 3 alternatives
    print(f"""
{'═'*62}
  📋 ALTERNATIVAS (otros vendedores/compradores)
{'═'*62}

  COMPRAR USDT DE (top 3 más baratos):""")

    for i, opt in enumerate(buy_options[:3]):
        print(
            f"  {i+1}. ${opt['price']:.2f} MXN — {opt['nick']} ({opt['orders']} trades, {opt['completion_rate']:.0f}%) — {', '.join(opt['methods'][:2])}"
        )

    print("\n  VENDER USDT A (top 3 mejor precio):")
    for i, opt in enumerate(sell_options[:3]):
        print(
            f"  {i+1}. ${opt['price']:.2f} MXN — {opt['nick']} ({opt['orders']} trades, {opt['completion_rate']:.0f}%) — {', '.join(opt['methods'][:2])}"
        )

    print(f"""
{'═'*62}
  Registra tu trade: python tools/trading_journal.py --trade
  Siguiente escaneo: python tools/trade_now.py
{'═'*62}
""")


def watch_mode(capital_usd: float = 28.0, interval: int = 60):
    """Auto-refresh mode."""
    print("🦇 MODO VIGILANCIA — Ctrl+C para salir")
    print(f"   Escaneando cada {interval} segundos...\n")

    while True:
        try:
            clear_screen()
            display_trading_panel(capital_usd)
            print(f"  ⏰ Próximo escaneo en {interval}s... (Ctrl+C para salir)")
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\n  🦇 Vigilancia terminada. Buena sesión.")
            break


def main():
    capital = 28.0
    explain = "--explain" in sys.argv
    watch = "--watch" in sys.argv

    # Check for custom capital
    for arg in sys.argv[1:]:
        try:
            val = float(arg)
            if 1 <= val <= 100000:
                capital = val
        except ValueError:
            pass

    if watch:
        watch_mode(capital)
    else:
        display_trading_panel(capital, explain)


if __name__ == "__main__":
    main()
