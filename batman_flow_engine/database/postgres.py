"""
Batman Lab — PostgreSQL Connection Module

Setup:
  brew install postgresql@16
  brew services start postgresql@16
  createdb batman_lab
  psql batman_lab < database/schema.sql
  pip install psycopg2-binary --break-system-packages
"""

import os
import json
import logging
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Any, Optional

logger = logging.getLogger("batman.postgres")

DB_CONFIG = {
    "host": os.environ.get("BATMAN_DB_HOST", "localhost"),
    "port": int(os.environ.get("BATMAN_DB_PORT", 5432)),
    "dbname": os.environ.get("BATMAN_DB_NAME", "batman_lab"),
    "user": os.environ.get("BATMAN_DB_USER", os.environ.get("USER", "batman")),
    "password": os.environ.get("BATMAN_DB_PASSWORD", ""),
}

_pool = None


def get_pool():
    global _pool
    if _pool is None:
        import psycopg2
        from psycopg2 import pool as pg_pool
        _pool = pg_pool.ThreadedConnectionPool(minconn=2, maxconn=10, **DB_CONFIG)
        logger.info("PostgreSQL pool created: %s@%s/%s", DB_CONFIG["user"], DB_CONFIG["host"], DB_CONFIG["dbname"])
    return _pool


@contextmanager
def get_conn():
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def get_cursor():
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()


def check_connection() -> dict:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
            tables = cur.fetchone()[0]
            return {"status": "ok", "version": version, "tables": tables}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ─────────────────────── OPPORTUNITIES ───────────────────────

def save_opportunity(opp: dict) -> bool:
    try:
        standard_keys = {
            "opp_id", "ts", "type", "scanner_id", "asset", "market", "venue",
            "buy_price", "sell_price", "spot_price", "gross_spread_pct",
            "total_friction_pct", "edge_net", "viable", "depth_estimate", "observe_only"
        }
        metadata = {k: v for k, v in opp.items() if k not in standard_keys}

        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO opportunities
                    (opp_id, ts, scanner_type, scanner_id, asset, market, venue,
                     buy_price, sell_price, spot_price, gross_spread_pct,
                     total_friction_pct, edge_net, viable, depth_estimate,
                     observe_only, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (opp_id) DO NOTHING
            """, (
                opp.get("opp_id"), opp.get("ts", datetime.now(timezone.utc).isoformat()),
                opp.get("type", "?"), opp.get("scanner_id", "unknown"),
                opp.get("asset", "USDT"), opp.get("market"), opp.get("venue"),
                opp.get("buy_price"), opp.get("sell_price"), opp.get("spot_price"),
                opp.get("gross_spread_pct"), opp.get("total_friction_pct"),
                opp.get("edge_net"), opp.get("viable", False),
                opp.get("depth_estimate"), opp.get("observe_only", True),
                json.dumps(metadata, default=str),
            ))
        return True
    except Exception as e:
        logger.error("Failed to save opportunity %s: %s", opp.get("opp_id"), e)
        return False


def get_viable_opportunities(hours: int = 24, scanner: str = None, limit: int = 100) -> list:
    try:
        with get_cursor() as cur:
            query = """
                SELECT opp_id, ts, scanner_type, asset, market, venue,
                       buy_price, sell_price, edge_net, viable, depth_estimate, metadata
                FROM opportunities WHERE viable = TRUE AND ts > NOW() - INTERVAL '%s hours'
            """
            params = [hours]
            if scanner:
                query += " AND scanner_type = %s"
                params.append(scanner)
            query += " ORDER BY edge_net DESC LIMIT %s"
            params.append(limit)
            cur.execute(query, params)
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to get opportunities: %s", e)
        return []


def get_best_opportunity() -> Optional[dict]:
    results = get_viable_opportunities(hours=1, limit=1)
    return results[0] if results else None


# ─────────────────────── TRADES ───────────────────────

def save_trade(trade: dict) -> bool:
    try:
        standard_keys = {
            "trade_id", "agent", "ts", "opp_id", "asset", "market",
            "side", "price", "quantity", "fee", "pnl", "status"
        }
        metadata = {k: v for k, v in trade.items() if k not in standard_keys}

        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO trades
                    (trade_id, agent, ts, opp_id, asset, market,
                     side, price, quantity, fee, pnl, status, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trade_id) DO NOTHING
            """, (
                trade.get("trade_id"), trade.get("agent", "unknown"),
                trade.get("ts", datetime.now(timezone.utc).isoformat()),
                trade.get("opp_id"), trade.get("asset", "USDT"), trade.get("market"),
                trade.get("side", "BUY"), trade.get("price", 0), trade.get("quantity", 0),
                trade.get("fee", 0), trade.get("pnl"), trade.get("status", "executed"),
                json.dumps(metadata, default=str),
            ))
        return True
    except Exception as e:
        logger.error("Failed to save trade %s: %s", trade.get("trade_id"), e)
        return False


def get_daily_pnl(agent: str = None, days: int = 30) -> list:
    try:
        with get_cursor() as cur:
            query = """
                SELECT agent, DATE(ts) as trade_date, COUNT(*) as trade_count,
                       COALESCE(SUM(pnl), 0) as total_pnl
                FROM trades WHERE ts > NOW() - INTERVAL '%s days'
            """
            params = [days]
            if agent:
                query += " AND agent = %s"
                params.append(agent)
            query += " GROUP BY agent, DATE(ts) ORDER BY trade_date DESC"
            cur.execute(query, params)
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to get daily P&L: %s", e)
        return []


# ─────────────────────── HODL POSITIONS ───────────────────────

def save_hodl_position(pos: dict) -> bool:
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO hodl_positions
                    (token, exchange, quantity, avg_buy_price,
                     take_profit_1, take_profit_2, take_profit_3,
                     stop_loss, trailing_stop_pct)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                pos["token"], pos["exchange"], pos["quantity"], pos["avg_buy_price"],
                pos.get("take_profit_1"), pos.get("take_profit_2"), pos.get("take_profit_3"),
                pos.get("stop_loss"), pos.get("trailing_stop_pct", 15.0),
            ))
        return True
    except Exception as e:
        logger.error("Failed to save HODL position: %s", e)
        return False


def update_hodl_prices(prices: dict) -> int:
    updated = 0
    try:
        with get_cursor() as cur:
            for token, price in prices.items():
                cur.execute("""
                    UPDATE hodl_positions
                    SET current_price = %s,
                        peak_price = GREATEST(COALESCE(peak_price, 0), %s),
                        updated_at = NOW()
                    WHERE token = %s AND status = 'active'
                """, (price, price, token))
                updated += cur.rowcount
    except Exception as e:
        logger.error("Failed to update HODL prices: %s", e)
    return updated


def get_hodl_alerts() -> list:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM v_hodl_alerts WHERE signal != 'HOLD' AND signal != 'NO_PRICE'")
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to get HODL alerts: %s", e)
        return []


def get_all_hodl() -> list:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM v_hodl_alerts ORDER BY unrealized_pnl_pct DESC")
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to get HODL positions: %s", e)
        return []


# ─────────────────────── VENTURE POSITIONS ───────────────────────

def save_venture_position(pos: dict) -> bool:
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO venture_positions
                    (token, chain, wallet_address, dexscreener_pair,
                     quantity, avg_buy_price, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                pos["token"], pos["chain"], pos.get("wallet_address"),
                pos.get("dexscreener_pair"), pos["quantity"],
                pos.get("avg_buy_price", 0), pos.get("notes"),
            ))
        return True
    except Exception as e:
        logger.error("Failed to save venture position: %s", e)
        return False


def get_all_ventures() -> list:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM venture_positions WHERE status = 'active' ORDER BY updated_at DESC")
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to get ventures: %s", e)
        return []


# ─────────────────────── PORTFOLIO BALANCES ───────────────────────

def save_portfolio_snapshot(balances: list) -> int:
    saved = 0
    today = datetime.now().date()
    try:
        with get_cursor() as cur:
            for b in balances:
                cur.execute("""
                    INSERT INTO portfolio_balances
                        (platform, instrument, balance, currency, interest_rate, category, snapshot_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    b["platform"], b["instrument"], b["balance"],
                    b.get("currency", "MXN"), b.get("interest_rate"),
                    b.get("category", "other"), today,
                ))
                saved += 1
    except Exception as e:
        logger.error("Failed to save portfolio snapshot: %s", e)
    return saved


def get_portfolio_overview() -> list:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM v_portfolio_overview")
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to get portfolio overview: %s", e)
        return []


# ─────────────────────── SCANNER RUNS ───────────────────────

def log_scanner_run(scanner_type: str, scanner_name: str, duration_sec: float,
                    opps_found: int, viable_found: int, errors: int = 0,
                    status: str = "ok", error_msg: str = None) -> bool:
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO scanner_runs
                    (scanner_type, scanner_name, duration_sec,
                     opportunities_found, viable_found, errors, status, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (scanner_type, scanner_name, duration_sec,
                  opps_found, viable_found, errors, status, error_msg))
        return True
    except Exception as e:
        logger.error("Failed to log scanner run: %s", e)
        return False


def get_scanner_performance(days: int = 7) -> list:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM v_scanner_performance")
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to get scanner performance: %s", e)
        return []


# ─────────────────────── ENGINE RUNS ───────────────────────

def save_engine_run_pg(result: dict) -> bool:
    try:
        meta = result.get("meta", {})
        stress = result.get("stress", {})
        regime = stress.get("regime", {}) if isinstance(stress, dict) else {}

        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO engine_runs
                    (ts, duration_sec, equities_total, equities_ok,
                     crypto_total, crypto_ok, regime, dq_score,
                     corr_stress, errors, full_report)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                result.get("timestamp", datetime.now(timezone.utc).isoformat()),
                meta.get("duration_sec"), meta.get("equities_total"), meta.get("equities_ok"),
                meta.get("crypto_total"), meta.get("crypto_ok"),
                regime.get("label") if isinstance(regime, dict) else None,
                None, stress.get("corr_stress") if isinstance(stress, dict) else None,
                meta.get("errors", 0), json.dumps(result, default=str),
            ))
        return True
    except Exception as e:
        logger.error("Failed to save engine run: %s", e)
        return False


# ─────────────────────── ALERTS ───────────────────────

def save_alert(source: str, title: str, message: str = None,
               severity: str = "info", metadata: dict = None) -> bool:
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO alerts (source, severity, title, message, metadata)
                VALUES (%s, %s, %s, %s, %s)
            """, (source, severity, title, message, json.dumps(metadata or {}, default=str)))
        return True
    except Exception as e:
        logger.error("Failed to save alert: %s", e)
        return False


def get_unread_alerts(limit: int = 50) -> list:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM alerts WHERE acknowledged = FALSE ORDER BY ts DESC LIMIT %s", (limit,))
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to get alerts: %s", e)
        return []


# ─────────────────────── STATS ───────────────────────

def get_database_stats() -> dict:
    try:
        stats = {}
        with get_cursor() as cur:
            for table in ["opportunities", "trades", "hodl_positions",
                          "venture_positions", "portfolio_balances",
                          "scanner_runs", "engine_runs", "alerts"]:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                stats[table] = cur.fetchone()[0]
        return stats
    except Exception as e:
        logger.error("Failed to get stats: %s", e)
        return {}
