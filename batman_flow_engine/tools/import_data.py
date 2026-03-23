#!/usr/bin/env python3
"""
🦇 BATMAN LAB — Universal Data Importer

Imports your real data from ANY platform into PostgreSQL.
Drop a CSV/XLSX and Batman Lab reads it automatically.

SUPPORTED FORMATS:
  1. Binance — Trade History CSV (Orders > Spot > Trade History > Export)
  2. Binance — Transaction History / Statements CSV
  3. Binance — P2P Order History CSV
  4. GBM — Trade History (Excel export)
  5. Bitso — Transaction CSV
  6. Generic — Any CSV with: date, asset, side, price, quantity columns
  7. Manual — JSON file with positions array

USAGE:
  # Auto-detect format from any CSV/XLSX:
  python tools/import_data.py /path/to/binance_trades.csv

  # Specify format explicitly:
  python tools/import_data.py /path/to/file.csv --format binance-spot

  # Import HODL positions from JSON:
  python tools/import_data.py /path/to/my_positions.json --format hodl

  # List supported formats:
  python tools/import_data.py --formats

HOW TO EXPORT FROM BINANCE:
  1. Go to: https://www.binance.com/en/my/orders/exchange/tradeorder
  2. Click "Trade History" > "Export"
  3. Select date range > "Generate"
  4. Download the CSV
  5. Run: python tools/import_data.py ~/Downloads/binance_trade_history.csv
"""

import csv
import json
import sys
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

IMPORT_DIR = BASE_DIR / "imports"
IMPORT_DIR.mkdir(exist_ok=True)


# ─────────────────────── FORMAT DETECTION ───────────────────────

KNOWN_HEADERS = {
    "binance-spot": ["Date(UTC)", "Pair", "Side", "Price", "Executed", "Amount", "Fee"],
    "binance-spot-v2": ["Date(UTC)", "OrderNo", "Pair", "Type", "Order Price", "Order Amount", "AvgTrading Price", "Filled", "Total", "Trigger Conditions", "status"],
    "binance-statement": ["User_ID", "UTC_Time", "Account", "Operation", "Coin", "Change", "Remark"],
    "binance-p2p": ["Order Number", "Order Type", "Asset Type", "Fiat Type", "Total Price", "Price", "Quantity"],
    "bitso": ["tid", "oid", "book", "side", "price", "amount", "value", "fee_amount", "fee_currency", "created_at"],
    "generic": ["date", "asset", "side", "price", "quantity"],
}


def detect_format(filepath: Path) -> str:
    """Auto-detect CSV format based on headers."""
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            headers = next(reader)
            headers_clean = [h.strip() for h in headers]

            for fmt_name, expected in KNOWN_HEADERS.items():
                if all(h in headers_clean for h in expected[:3]):
                    return fmt_name

            # Check if it's a JSON file
            if filepath.suffix.lower() == ".json":
                return "hodl-json"

        return "unknown"
    except Exception:
        if filepath.suffix.lower() == ".json":
            return "hodl-json"
        return "unknown"


# ─────────────────────── PARSERS ───────────────────────

def parse_binance_spot(filepath: Path) -> list:
    """Parse Binance Spot Trade History CSV."""
    trades = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pair = row.get("Pair", row.get("Market", ""))
                # Split pair: XRPUSDT → XRP, USDT
                asset = pair.replace("USDT", "").replace("BUSD", "").replace("BTC", "").replace("BNB", "")
                market = "USDT" if "USDT" in pair else "BTC" if "BTC" in pair else "BNB"

                price = float(row.get("Price", row.get("AvgTrading Price", 0)))
                quantity = float(row.get("Executed", row.get("Filled", row.get("Order Amount", 0))))
                fee = float(row.get("Fee", "0").replace(",", "")) if row.get("Fee") else 0
                side = row.get("Side", row.get("Type", "BUY")).upper()
                ts = row.get("Date(UTC)", row.get("Date", ""))

                if not price or not quantity:
                    continue

                trades.append({
                    "trade_id": f"BN-{uuid.uuid4().hex[:10].upper()}",
                    "agent": "import-binance",
                    "ts": ts,
                    "asset": asset,
                    "market": market,
                    "side": side,
                    "price": price,
                    "quantity": quantity,
                    "fee": fee,
                    "status": "executed",
                    "metadata": {"source": "binance-spot-csv", "pair": pair},
                })
            except Exception as e:
                print(f"  ⚠️  Skip row: {e}")
    return trades


def parse_binance_statement(filepath: Path) -> list:
    """Parse Binance Statement/Transaction History CSV."""
    trades = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                operation = row.get("Operation", "")
                coin = row.get("Coin", "")
                change = float(row.get("Change", 0))
                ts = row.get("UTC_Time", "")

                # Only process buy/sell/trade operations
                if operation.lower() not in ("buy", "sell", "trade", "transaction related", "small assets exchange bnb"):
                    continue

                side = "BUY" if change > 0 else "SELL"

                trades.append({
                    "trade_id": f"BNS-{uuid.uuid4().hex[:10].upper()}",
                    "agent": "import-binance-statement",
                    "ts": ts,
                    "asset": coin,
                    "market": "USDT",
                    "side": side,
                    "price": 0,  # Statement doesn't have price per unit
                    "quantity": abs(change),
                    "fee": 0,
                    "status": "executed",
                    "metadata": {"source": "binance-statement", "operation": operation, "remark": row.get("Remark", "")},
                })
            except Exception as e:
                print(f"  ⚠️  Skip row: {e}")
    return trades


def parse_binance_p2p(filepath: Path) -> list:
    """Parse Binance P2P Order History CSV."""
    trades = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                order_type = row.get("Order Type", "").upper()
                asset = row.get("Asset Type", "USDT")
                fiat = row.get("Fiat Type", "MXN")
                total_price = float(row.get("Total Price", 0))
                price = float(row.get("Price", 0))
                quantity = float(row.get("Quantity", 0))
                status = row.get("Status", "Completed")

                if "completed" not in status.lower():
                    continue

                trades.append({
                    "trade_id": f"P2P-{row.get('Order Number', uuid.uuid4().hex[:10].upper())}",
                    "agent": "import-p2p",
                    "ts": row.get("Created Time", ""),
                    "asset": asset,
                    "market": fiat,
                    "side": "BUY" if "buy" in order_type.lower() else "SELL",
                    "price": price,
                    "quantity": quantity,
                    "fee": 0,  # P2P has no fees on Binance
                    "status": "executed",
                    "metadata": {
                        "source": "binance-p2p", "total_price_fiat": total_price,
                        "order_number": row.get("Order Number", ""),
                    },
                })
            except Exception as e:
                print(f"  ⚠️  Skip row: {e}")
    return trades


def parse_bitso(filepath: Path) -> list:
    """Parse Bitso Transaction CSV."""
    trades = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                book = row.get("book", "")  # e.g. "btc_mxn"
                parts = book.split("_")
                asset = parts[0].upper() if parts else "?"
                market = parts[1].upper() if len(parts) > 1 else "MXN"

                trades.append({
                    "trade_id": f"BIT-{row.get('tid', uuid.uuid4().hex[:10].upper())}",
                    "agent": "import-bitso",
                    "ts": row.get("created_at", ""),
                    "asset": asset,
                    "market": market,
                    "side": row.get("side", "buy").upper(),
                    "price": float(row.get("price", 0)),
                    "quantity": float(row.get("amount", 0)),
                    "fee": float(row.get("fee_amount", 0)),
                    "status": "executed",
                    "metadata": {"source": "bitso", "oid": row.get("oid", "")},
                })
            except Exception as e:
                print(f"  ⚠️  Skip row: {e}")
    return trades


def parse_generic(filepath: Path) -> list:
    """Parse generic CSV: date, asset, side, price, quantity."""
    trades = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                trades.append({
                    "trade_id": f"GEN-{uuid.uuid4().hex[:10].upper()}",
                    "agent": "import-generic",
                    "ts": row.get("date", row.get("timestamp", row.get("Date", ""))),
                    "asset": row.get("asset", row.get("Asset", row.get("coin", "?"))).upper(),
                    "market": row.get("market", row.get("Market", "USDT")).upper(),
                    "side": row.get("side", row.get("Side", "BUY")).upper(),
                    "price": float(row.get("price", row.get("Price", 0))),
                    "quantity": float(row.get("quantity", row.get("Quantity", row.get("amount", 0)))),
                    "fee": float(row.get("fee", row.get("Fee", 0))),
                    "status": "executed",
                    "metadata": {"source": "generic-csv"},
                })
            except Exception as e:
                print(f"  ⚠️  Skip row: {e}")
    return trades


def parse_hodl_json(filepath: Path) -> list:
    """Parse JSON file with HODL positions.

    Expected format:
    {
      "positions": [
        {"token": "XRP", "exchange": "binance", "quantity": 100, "avg_buy_price": 0.55,
         "take_profit_1": 1.00, "take_profit_2": 1.50, "take_profit_3": 2.50,
         "stop_loss": 0.40, "trailing_stop_pct": 15},
        ...
      ]
    }
    """
    data = json.loads(filepath.read_text())
    positions = data.get("positions", data if isinstance(data, list) else [])
    return positions


# ─────────────────────── IMPORT TO DATABASE ───────────────────────

def import_trades(trades: list) -> int:
    """Import parsed trades into PostgreSQL."""
    from database.postgres import save_trade
    imported = 0
    for trade in trades:
        if save_trade(trade):
            imported += 1
    return imported


def import_hodl_positions(positions: list) -> int:
    """Import HODL positions into PostgreSQL."""
    from database.postgres import save_hodl_position
    imported = 0
    for pos in positions:
        if save_hodl_position(pos):
            imported += 1
    return imported


# ─────────────────────── MAIN ───────────────────────

def run_import(filepath: str, fmt: str = None):
    path = Path(filepath)
    if not path.exists():
        print(f"  ❌ File not found: {filepath}")
        return

    # Auto-detect format
    if not fmt:
        fmt = detect_format(path)
        print(f"  🔍 Detected format: {fmt}")

    if fmt == "unknown":
        print(f"  ❌ Could not detect format. Use --format to specify.")
        print(f"  Supported: binance-spot, binance-statement, binance-p2p, bitso, generic, hodl")
        return

    # Parse
    print(f"  📂 Parsing {path.name} as {fmt}...")

    parsers = {
        "binance-spot": parse_binance_spot,
        "binance-spot-v2": parse_binance_spot,
        "binance-statement": parse_binance_statement,
        "binance-p2p": parse_binance_p2p,
        "bitso": parse_bitso,
        "generic": parse_generic,
        "hodl-json": parse_hodl_json,
        "hodl": parse_hodl_json,
    }

    parser = parsers.get(fmt)
    if not parser:
        print(f"  ❌ No parser for format: {fmt}")
        return

    records = parser(path)
    print(f"  📊 Parsed {len(records)} records")

    if not records:
        print(f"  ⚠️  No records to import")
        return

    # Show preview
    print(f"\n  Preview (first 3 records):")
    for r in records[:3]:
        if fmt in ("hodl-json", "hodl"):
            print(f"    {r.get('token', '?')}: {r.get('quantity', 0)} @ ${r.get('avg_buy_price', 0)}")
        else:
            print(f"    {r.get('side', '?')} {r.get('quantity', 0)} {r.get('asset', '?')} @ ${r.get('price', 0)} [{r.get('ts', '?')}]")

    # Confirm
    print(f"\n  Import {len(records)} records? (y/n): ", end="")
    confirm = input().strip().lower()
    if confirm != "y":
        print(f"  Cancelled.")
        return

    # Import
    if fmt in ("hodl-json", "hodl"):
        imported = import_hodl_positions(records)
    else:
        imported = import_trades(records)

    print(f"\n  ✅ Imported {imported}/{len(records)} records into PostgreSQL")

    # Backup original file
    backup = IMPORT_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{path.name}"
    import shutil
    shutil.copy2(path, backup)
    print(f"  💾 Backup saved: {backup.name}")


def show_formats():
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║       🦇 BATMAN LAB — Supported Import Formats                   ║
╚══════════════════════════════════════════════════════════════════╝

  BINANCE:
    binance-spot       Spot Trade History CSV
                       (Orders > Spot > Trade History > Export)

    binance-statement  Transaction History / Statements CSV
                       (Wallet > Transaction History > Generate all statements)

    binance-p2p        P2P Order History CSV
                       (Orders > P2P Order > Export)

  OTHER EXCHANGES:
    bitso              Bitso Trade CSV

  UNIVERSAL:
    generic            Any CSV with columns: date, asset, side, price, quantity

  POSITIONS:
    hodl               JSON file with HODL positions
                       Format: {{"positions": [{{"token":"XRP","quantity":100,"avg_buy_price":0.55,...}}]}}

  USAGE:
    python tools/import_data.py ~/Downloads/binance_trades.csv
    python tools/import_data.py my_positions.json --format hodl
    """)


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--formats" in args or len(args) == 0:
        show_formats()
    else:
        filepath = args[0]
        fmt = None
        if "--format" in args:
            idx = args.index("--format")
            fmt = args[idx + 1] if idx + 1 < len(args) else None
        run_import(filepath, fmt)
