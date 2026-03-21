#!/usr/bin/env python3
"""
BATMAN LAB — DAILY TRADING JOURNAL

Records your P2P trading day: trades, observations, patterns, lessons.
Creates a daily markdown file in journal/ folder.

Usage:
  python tools/trading_journal.py                  # Start/continue today's journal
  python tools/trading_journal.py --trade          # Record a trade
  python tools/trading_journal.py --note "text"    # Add observation note
  python tools/trading_journal.py --close          # Close the day with summary
  python tools/trading_journal.py --review 7       # Review last 7 days
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
JOURNAL_DIR = BASE_DIR / "journal"
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)


def _today_file() -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return JOURNAL_DIR / f"{today}.md"


def _now() -> str:
    return datetime.now().strftime("%H:%M")


def start_day():
    """Create or open today's journal."""
    f = _today_file()
    today = datetime.now().strftime("%Y-%m-%d %A")

    if f.exists():
        print(f"Journal already exists for today: {f}")
        print("Use --trade, --note, or --close to add entries.")
        return

    content = f"""# BATMAN LAB — Trading Journal
## {today}

---

### Morning Briefing
- **Start time:** {_now()}
- **Starting capital:** $ _____ USD
- **Market mood:** _____
- **Batman overnight summary:** (run `python tools/multi_strategy_dashboard.py`)
- **Key news:** _____

---

### Trades Log

| # | Time | Exchange | Pair | Action | Amount USD | Buy Price | Sell Price | Edge % | P&L USD | Notes |
|---|------|----------|------|--------|-----------|-----------|------------|--------|---------|-------|

---

### Observations & Patterns

---

### End of Day Summary
- **End time:**
- **Ending capital:** $ _____ USD
- **Total trades:**
- **Total P&L:** $ _____ USD
- **Best trade:**
- **Worst trade:**
- **Key lesson:**
- **Tomorrow plan:**

---
"""
    f.write_text(content)
    print(f"📓 Journal created: {f}")
    print(f"   Start time: {_now()}")
    print("   Fill in your starting capital and market mood.")


def record_trade():
    """Interactive trade recording."""
    f = _today_file()
    if not f.exists():
        start_day()

    print("\n🦇 RECORD TRADE")
    print("=" * 40)

    time_str = _now()
    exchange = input("Exchange [binance]: ").strip() or "binance"
    pair = input("Pair [USDT/MXN]: ").strip() or "USDT/MXN"
    action = input("Action (buy/sell) [buy]: ").strip() or "buy"

    try:
        amount = float(input("Amount USD [28]: ").strip() or "28")
    except ValueError:
        amount = 28.0

    try:
        buy_price = float(input("Buy price: ").strip())
    except ValueError:
        print("Invalid price. Aborting.")
        return

    try:
        sell_price_input = input("Sell price [same]: ").strip()
        sell_price = float(sell_price_input) if sell_price_input else buy_price
    except ValueError:
        sell_price = buy_price

    try:
        edge = float(input("Edge % [0.5]: ").strip() or "0.5")
    except ValueError:
        edge = 0.5

    pnl = amount * (edge / 100)
    notes = input("Notes: ").strip() or ""

    # Count existing trades
    content = f.read_text()
    trade_count = content.count("| ") - 2  # Subtract header rows
    trade_num = max(1, trade_count)

    trade_line = f"| {trade_num} | {time_str} | {exchange} | {pair} | {action} | ${amount:.0f} | {buy_price} | {sell_price} | {edge:+.3f}% | ${pnl:+.2f} | {notes} |"

    # Insert before "### Observations"
    content = content.replace("### Observations", f"{trade_line}\n\n### Observations")
    f.write_text(content)

    print(f"\n✅ Trade #{trade_num} recorded: {pair} on {exchange}")
    print(f"   Edge: {edge:+.3f}% | P&L: ${pnl:+.2f} USD")

    # Also record in HARVEY
    try:
        sys.path.insert(0, str(BASE_DIR.parent / "nightwing_agent"))
        # Silent record — already done interactively
    except Exception:
        pass


def add_note(note: str):
    """Add observation note to today's journal."""
    f = _today_file()
    if not f.exists():
        start_day()

    content = f.read_text()
    timestamp = _now()
    note_entry = f"- **[{timestamp}]** {note}"

    content = content.replace("### End of Day Summary", f"{note_entry}\n\n### End of Day Summary")
    f.write_text(content)
    print(f"📝 Note added at {timestamp}: {note}")


def close_day():
    """Close the day with summary."""
    f = _today_file()
    if not f.exists():
        print("No journal for today. Run without arguments to start.")
        return

    print("\n🌙 CLOSE DAY")
    print("=" * 40)

    ending_capital = input("Ending capital USD: ").strip()
    total_trades = input("Total trades: ").strip()
    total_pnl = input("Total P&L USD: ").strip()
    best_trade = input("Best trade description: ").strip()
    worst_trade = input("Worst trade description: ").strip()
    lesson = input("Key lesson today: ").strip()
    tomorrow = input("Plan for tomorrow: ").strip()

    content = f.read_text()
    content = content.replace("- **End time:**", f"- **End time:** {_now()}")
    content = content.replace("- **Ending capital:** $ _____ USD", f"- **Ending capital:** ${ending_capital} USD")
    content = content.replace("- **Total trades:**", f"- **Total trades:** {total_trades}")
    content = content.replace("- **Total P&L:** $ _____ USD", f"- **Total P&L:** ${total_pnl} USD")
    content = content.replace("- **Best trade:**", f"- **Best trade:** {best_trade}")
    content = content.replace("- **Worst trade:**", f"- **Worst trade:** {worst_trade}")
    content = content.replace("- **Key lesson:**", f"- **Key lesson:** {lesson}")
    content = content.replace("- **Tomorrow plan:**", f"- **Tomorrow plan:** {tomorrow}")

    f.write_text(content)
    print(f"\n✅ Day closed at {_now()}")
    print(f"   Journal: {f}")


def review_days(days: int):
    """Review last N days of journals."""
    print(f"\n📊 JOURNAL REVIEW — Last {days} days")
    print("=" * 60)

    today = datetime.now()
    found = 0

    for i in range(days):
        date = today - timedelta(days=i)
        f = JOURNAL_DIR / f"{date.strftime('%Y-%m-%d')}.md"
        if f.exists():
            found += 1
            content = f.read_text()
            # Extract key info
            print(f"\n📅 {date.strftime('%Y-%m-%d %A')}")

            for line in content.split("\n"):
                if "Ending capital" in line and "___" not in line:
                    print(f"   {line.strip()}")
                if "Total P&L" in line and "___" not in line:
                    print(f"   {line.strip()}")
                if "Total trades" in line and "___" not in line:
                    print(f"   {line.strip()}")
                if "Key lesson" in line and "___" not in line:
                    print(f"   {line.strip()}")

    if found == 0:
        print("   No journals found for this period.")
    print(f"\n   Total journal days: {found}/{days}")


def main():
    parser = argparse.ArgumentParser(description="Batman Lab Trading Journal")
    parser.add_argument("--trade", action="store_true", help="Record a trade")
    parser.add_argument("--note", type=str, help="Add observation note")
    parser.add_argument("--close", action="store_true", help="Close the day")
    parser.add_argument("--review", type=int, help="Review last N days")
    args = parser.parse_args()

    if args.trade:
        record_trade()
    elif args.note:
        add_note(args.note)
    elif args.close:
        close_day()
    elif args.review:
        review_days(args.review)
    else:
        start_day()


if __name__ == "__main__":
    main()
