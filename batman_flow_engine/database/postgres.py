"""
Batman Lab — PostgreSQL Connection Module

Setup:
  brew install postgresql@16
  brew services start postgresql@16
  createdb batman_lab
  psql batman_lab < database/schema.sql
  pip install psycopg2-binary --break-system-packages
"""

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime

logger = logging.getLogger("batman.postgres")

DB_CONFIG = {
    "host": os.environ.get("BATMAN_DB_HOST", "localhost"),
    "port": int(os.environ.get("BATMAN_DB_PORT", 5432)),
    "dbname": os.environ.get("BATMAN_DB_NAME", "batman_lab"),
    "user": os.environ.get("BATMAN_DB_USER", os.environ.get("USER", "batman")),
    "password": os.environ.get("BATMAN_DB_PASSWORD", ""),
}

_pool = None


def _is_expected_connection_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "connection refused",
            "could not connect to server",
            "connection to server at",
            "server closed the connection unexpectedly",
        )
    )


def _log_db_error(message: str, exc: Exception) -> None:
    if _is_expected_connection_error(exc):
        logger.debug("%s: %s", message, exc)
    else:
        logger.error("%s: %s", message, exc)


def get_pool():
    global _pool
    if _pool is None:
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


# ─────────────────────── SHARED AVAILABILITY STATE ───────────────────────
#
# This block is the single, canonical source of truth for PostgreSQL
# availability across the Batman process.
#
# BEFORE (2026-04-20 dry-cycle audit): dual_writer owned its own
# _pg_available / _pg_last_check_ts cache. HARVEY and engine.py's
# risk-scores block had no availability cache at all — they called
# save_opportunity / save_risk_score directly and discarded the return
# value. Observed divergence: dual_writer marked PG DOWN early in a
# cycle; a few seconds later PG was started; HARVEY wrote successfully
# at the end of the same cycle while dual_writer still believed PG was
# DOWN. Two views of the same external resource in one process.
#
# AFTER (2026-04-21): all consumers go through pg_available() and
# mark_pg_unavailable() below. No module-local availability state.
# See tests/test_dual_writer.py and tests/test_harvey_pg_gate.py.

PG_RECHECK_INTERVAL_SEC = 60.0

_pg_available: bool | None = None
_pg_last_check_ts: float | None = None
_pg_state_lock = threading.Lock()


def pg_reset_pool() -> None:
    """Close and discard the pool. The next get_pool() rebuilds from scratch."""
    global _pool
    if _pool is None:
        return
    try:
        _pool.closeall()
    except Exception as exc:
        logger.debug("Pool closeall failed (non-fatal): %s", exc)
    _pool = None


def _pg_probe_locked(now: float) -> None:
    """
    Probe PG availability and update cached state + timestamp.

    MUST be called while holding _pg_state_lock.
    """
    global _pg_available, _pg_last_check_ts
    previous = _pg_available
    _pg_last_check_ts = now
    try:
        result = check_connection()
        is_ok = result.get("status") == "ok"
    except Exception as exc:
        logger.error(
            "PostgreSQL availability probe raised (will retry in %.0fs): %s",
            PG_RECHECK_INTERVAL_SEC,
            exc,
            exc_info=True,
        )
        _pg_available = False
        return
    _pg_available = is_ok
    if is_ok and previous is not True:
        logger.info("PostgreSQL reachable — writes enabled")
    elif not is_ok and previous is not False:
        logger.info(
            "PostgreSQL unavailable — writes deferred (will retry every %.0fs)",
            PG_RECHECK_INTERVAL_SEC,
        )


def pg_probe() -> bool:
    """Force an immediate probe; return True if PG is reachable. Public API."""
    now = time.monotonic()
    with _pg_state_lock:
        _pg_probe_locked(now)
        return bool(_pg_available)


def pg_available() -> bool:
    """
    Return True if PostgreSQL is believed available.

    Semantics (identical to the previous dual_writer._check_pg):
      - Probe on first call (state == None).
      - While believed unavailable, re-probe every PG_RECHECK_INTERVAL_SEC
        seconds so a recovered PG is picked up mid-run.
      - While believed available, do NOT re-probe — rely on write failures
        to invalidate via mark_pg_unavailable().
    """
    global _pg_available, _pg_last_check_ts
    now = time.monotonic()
    with _pg_state_lock:
        if _pg_available is None:
            _pg_probe_locked(now)
        elif _pg_available is False:
            if _pg_last_check_ts is None or (now - _pg_last_check_ts) >= PG_RECHECK_INTERVAL_SEC:
                _pg_probe_locked(now)
        return bool(_pg_available)


def mark_pg_unavailable(reason: str, exc: Exception | None = None) -> None:
    """
    Flip the cache to unavailable and start the backoff clock.

    Callers use this after a PG write unexpectedly fails so subsequent
    pg_available() calls stop hammering PG until PG_RECHECK_INTERVAL_SEC
    elapses.

    If exc is a connection-class error (e.g. "connection refused"), the
    shared pool is also flushed — the next probe will rebuild fresh
    connections instead of reusing sockets to a server that just died.
    """
    global _pg_available, _pg_last_check_ts
    with _pg_state_lock:
        was_available = _pg_available
        _pg_available = False
        _pg_last_check_ts = time.monotonic()
        should_flush = exc is not None and _is_expected_connection_error(exc)
    # Run side-effects OUTSIDE the state lock to avoid deadlocks if pool
    # teardown ever blocks on something that itself wants the state lock.
    if should_flush:
        pg_reset_pool()
    if was_available:
        logger.error(
            "PostgreSQL marked unavailable after write failure (%s); will retry in %.0fs",
            reason,
            PG_RECHECK_INTERVAL_SEC,
        )


# ─────────────────────── OPPORTUNITIES ───────────────────────


def save_opportunity(opp: dict) -> bool:
    try:
        standard_keys = {
            "opp_id",
            "ts",
            "cycle_id",  # audit Section C #9: stored in its own column, not metadata
            "type",
            "scanner_id",
            "asset",
            "market",
            "venue",
            "buy_price",
            "sell_price",
            "spot_price",
            "gross_spread_pct",
            "total_friction_pct",
            "edge_net",
            "viable",
            "depth_estimate",
            "observe_only",
        }
        metadata = {k: v for k, v in opp.items() if k not in standard_keys}

        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO opportunities
                    (opp_id, ts, cycle_id, scanner_type, scanner_id, asset, market, venue,
                     buy_price, sell_price, spot_price, gross_spread_pct,
                     total_friction_pct, edge_net, viable, depth_estimate,
                     observe_only, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (opp_id) DO NOTHING
            """,
                (
                    opp.get("opp_id"),
                    opp.get("ts", datetime.now(UTC).isoformat()),
                    opp.get("cycle_id"),
                    opp.get("type", "?"),
                    opp.get("scanner_id", "unknown"),
                    opp.get("asset", "USDT"),
                    opp.get("market"),
                    opp.get("venue"),
                    opp.get("buy_price"),
                    opp.get("sell_price"),
                    opp.get("spot_price"),
                    opp.get("gross_spread_pct"),
                    opp.get("total_friction_pct"),
                    opp.get("edge_net"),
                    opp.get("viable", False),
                    opp.get("depth_estimate"),
                    opp.get("observe_only", True),
                    json.dumps(metadata, default=str),
                ),
            )
        return True
    except Exception as e:
        _log_db_error(f"Failed to save opportunity {opp.get('opp_id')}", e)
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
            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
    except Exception as e:
        _log_db_error("Failed to get opportunities", e)
        return []


def get_best_opportunity() -> dict | None:
    results = get_viable_opportunities(hours=1, limit=1)
    return results[0] if results else None


# ─────────────────────── TRADES ───────────────────────


def save_trade(trade: dict) -> bool:
    try:
        standard_keys = {
            "trade_id",
            "agent",
            "ts",
            "opp_id",
            "asset",
            "market",
            "side",
            "price",
            "quantity",
            "fee",
            "pnl",
            "status",
        }
        metadata = {k: v for k, v in trade.items() if k not in standard_keys}

        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO trades
                    (trade_id, agent, ts, opp_id, asset, market,
                     side, price, quantity, fee, pnl, status, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trade_id) DO NOTHING
            """,
                (
                    trade.get("trade_id"),
                    trade.get("agent", "unknown"),
                    trade.get("ts", datetime.now(UTC).isoformat()),
                    trade.get("opp_id"),
                    trade.get("asset", "USDT"),
                    trade.get("market"),
                    trade.get("side", "BUY"),
                    trade.get("price", 0),
                    trade.get("quantity", 0),
                    trade.get("fee", 0),
                    trade.get("pnl"),
                    trade.get("status", "executed"),
                    json.dumps(metadata, default=str),
                ),
            )
        return True
    except Exception as e:
        _log_db_error(f"Failed to save trade {trade.get('trade_id')}", e)
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
            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
    except Exception as e:
        _log_db_error("Failed to get daily P&L", e)
        return []


# ─────────────────────── HODL POSITIONS ───────────────────────


def save_hodl_position(pos: dict) -> bool:
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO hodl_positions
                    (token, exchange, quantity, avg_buy_price,
                     take_profit_1, take_profit_2, take_profit_3,
                     stop_loss, trailing_stop_pct)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    pos["token"],
                    pos["exchange"],
                    pos["quantity"],
                    pos["avg_buy_price"],
                    pos.get("take_profit_1"),
                    pos.get("take_profit_2"),
                    pos.get("take_profit_3"),
                    pos.get("stop_loss"),
                    pos.get("trailing_stop_pct", 15.0),
                ),
            )
        return True
    except Exception as e:
        logger.error("Failed to save HODL position: %s", e)
        return False


def update_hodl_prices(prices: dict) -> int:
    updated = 0
    try:
        with get_cursor() as cur:
            for token, price in prices.items():
                cur.execute(
                    """
                    UPDATE hodl_positions
                    SET current_price = %s,
                        peak_price = GREATEST(COALESCE(peak_price, 0), %s),
                        updated_at = NOW()
                    WHERE token = %s AND status = 'active'
                """,
                    (price, price, token),
                )
                updated += cur.rowcount
    except Exception as e:
        logger.error("Failed to update HODL prices: %s", e)
    return updated


def get_hodl_alerts() -> list:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM v_hodl_alerts WHERE signal != 'HOLD' AND signal != 'NO_PRICE'")
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
    except Exception as e:
        _log_db_error("Failed to get HODL alerts", e)
        return []


def get_all_hodl() -> list:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM v_hodl_alerts ORDER BY unrealized_pnl_pct DESC")
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
    except Exception as e:
        _log_db_error("Failed to get HODL positions", e)
        return []


# ─────────────────────── VENTURE POSITIONS ───────────────────────


def save_venture_position(pos: dict) -> bool:
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO venture_positions
                    (token, chain, wallet_address, dexscreener_pair,
                     quantity, avg_buy_price, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    pos["token"],
                    pos["chain"],
                    pos.get("wallet_address"),
                    pos.get("dexscreener_pair"),
                    pos["quantity"],
                    pos.get("avg_buy_price", 0),
                    pos.get("notes"),
                ),
            )
        return True
    except Exception as e:
        logger.error("Failed to save venture position: %s", e)
        return False


def get_all_ventures() -> list:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM venture_positions WHERE status = 'active' ORDER BY updated_at DESC")
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
    except Exception as e:
        _log_db_error("Failed to get ventures", e)
        return []


# ─────────────────────── PORTFOLIO BALANCES ───────────────────────


def save_portfolio_snapshot(balances: list) -> int:
    saved = 0
    today = datetime.now().date()
    try:
        with get_cursor() as cur:
            for b in balances:
                cur.execute(
                    """
                    INSERT INTO portfolio_balances
                        (platform, instrument, balance, currency, interest_rate, category, snapshot_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        b["platform"],
                        b["instrument"],
                        b["balance"],
                        b.get("currency", "MXN"),
                        b.get("interest_rate"),
                        b.get("category", "other"),
                        today,
                    ),
                )
                saved += 1
    except Exception as e:
        logger.error("Failed to save portfolio snapshot: %s", e)
    return saved


def get_portfolio_overview() -> list:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM v_portfolio_overview")
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
    except Exception as e:
        _log_db_error("Failed to get portfolio overview", e)
        return []


# ─────────────────────── SCANNER RUNS ───────────────────────


def log_scanner_run(
    scanner_type: str,
    scanner_name: str,
    duration_sec: float,
    opps_found: int,
    viable_found: int,
    errors: int = 0,
    status: str = "ok",
    error_msg: str = None,
) -> bool:
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO scanner_runs
                    (scanner_type, scanner_name, duration_sec,
                     opportunities_found, viable_found, errors, status, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (scanner_type, scanner_name, duration_sec, opps_found, viable_found, errors, status, error_msg),
            )
        return True
    except Exception as e:
        logger.error("Failed to log scanner run: %s", e)
        return False


def get_scanner_performance(days: int = 7) -> list:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM v_scanner_performance")
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
    except Exception as e:
        _log_db_error("Failed to get scanner performance", e)
        return []


# ─────────────────────── ENGINE RUNS ───────────────────────


def save_engine_run_pg(result: dict) -> bool:
    try:
        meta = result.get("meta", {})
        stress = result.get("stress", {})
        regime = stress.get("regime", {}) if isinstance(stress, dict) else {}

        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO engine_runs
                    (ts, cycle_id, duration_sec, equities_total, equities_ok,
                     crypto_total, crypto_ok, regime, dq_score,
                     corr_stress, errors, full_report)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    result.get("timestamp", datetime.now(UTC).isoformat()),
                    result.get("cycle_id"),
                    meta.get("duration_sec"),
                    meta.get("equities_total"),
                    meta.get("equities_ok"),
                    meta.get("crypto_total"),
                    meta.get("crypto_ok"),
                    regime.get("label") if isinstance(regime, dict) else None,
                    None,
                    stress.get("corr_stress") if isinstance(stress, dict) else None,
                    meta.get("errors", 0),
                    json.dumps(result, default=str),
                ),
            )
        return True
    except Exception as e:
        _log_db_error("Failed to save engine run", e)
        return False


# ─────────────────────── ALERTS ───────────────────────


def save_alert(source: str, title: str, message: str = None, severity: str = "info", metadata: dict = None) -> bool:
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO alerts (source, severity, title, message, metadata)
                VALUES (%s, %s, %s, %s, %s)
            """,
                (source, severity, title, message, json.dumps(metadata or {}, default=str)),
            )
        return True
    except Exception as e:
        _log_db_error("Failed to save alert", e)
        return False


def get_unread_alerts(limit: int = 50) -> list:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM alerts WHERE acknowledged = FALSE ORDER BY ts DESC LIMIT %s", (limit,))
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
    except Exception as e:
        _log_db_error("Failed to get alerts", e)
        return []


# ─────────────────────── STATS ───────────────────────


def get_concentration_risk() -> dict:
    """
    Compute portfolio concentration risk from active portfolio_positions.

    Returns:
        hhi              — Herfindahl-Hirschman Index (sum of squared position shares)
        top_position_pct — largest single position as share of total (0.0–1.0)
        score            — 1.0 − HHI  (1.0 = perfectly diversified, 0.0 = single position)
        positions        — number of active positions included
    """
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT position_id,
                       cost_basis_native * fx_rate_entry AS cost_basis_usd
                FROM portfolio_positions
                WHERE status = 'active'
            """)
            rows = cur.fetchall()

        if not rows:
            # No active positions → no concentration risk by definition
            return {"hhi": 0.0, "top_position_pct": 0.0, "score": 1.0, "positions": 0}

        values = [float(r[1]) for r in rows if r[1] is not None and float(r[1]) > 0]
        if not values:
            # Rows exist but all have zero/null cost basis → treat as empty
            return {"hhi": 0.0, "top_position_pct": 0.0, "score": 1.0, "positions": len(rows)}

        total = sum(values)
        if total <= 0:
            return {"hhi": 0.0, "top_position_pct": 0.0, "score": 1.0, "positions": len(values)}

        shares = [v / total for v in values]
        hhi = sum(s**2 for s in shares)
        top_pct = max(shares)
        score = round(max(0.0, 1.0 - hhi), 4)

        return {
            "hhi": round(hhi, 6),
            "top_position_pct": round(top_pct, 4),
            "score": score,
            "positions": len(values),
        }
    except Exception as e:
        _log_db_error("Failed to compute concentration risk", e)
        return {"hhi": None, "top_position_pct": None, "score": None, "positions": 0, "error": str(e)}


def save_risk_score(scores: dict) -> bool:
    """
    Persist one risk_scores row per engine cycle.

    Args:
        scores: Dict produced by engine.py's _compute_risk_scores() block.
                Keys mirror risk_scores table columns.
    """
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO risk_scores
                    (ts, cycle_id,
                     operational_readiness, concentration_risk, technical_risk,
                     governance_risk, market_behavior, financial_attractiveness,
                     composite_score,
                     dq_score, gordon_status, regime_label, viable_pct,
                     top_position_pct, hhi, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    scores.get("ts", datetime.now(UTC).isoformat()),
                    scores.get("cycle_id"),
                    scores.get("operational_readiness"),
                    scores.get("concentration_risk"),
                    scores.get("technical_risk"),
                    scores.get("governance_risk"),
                    scores.get("market_behavior"),
                    scores.get("financial_attractiveness"),
                    scores.get("composite_score"),
                    scores.get("dq_score"),
                    scores.get("gordon_status"),
                    scores.get("regime_label"),
                    scores.get("viable_pct"),
                    scores.get("top_position_pct"),
                    scores.get("hhi"),
                    json.dumps(scores.get("metadata", {}), default=str),
                ),
            )
        return True
    except Exception as e:
        _log_db_error("Failed to save risk score", e)
        return False


def get_database_stats() -> dict:
    try:
        stats = {}
        with get_cursor() as cur:
            for table in [
                "opportunities",
                "trades",
                "hodl_positions",
                "venture_positions",
                "portfolio_balances",
                "scanner_runs",
                "engine_runs",
                "alerts",
            ]:
                cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                stats[table] = cur.fetchone()[0]
        return stats
    except Exception as e:
        _log_db_error("Failed to get stats", e)
        return {}
