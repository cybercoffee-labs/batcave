import json
import logging
import sqlite3
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "storage" / "batman.db"
OPPORTUNITIES_LOG = BASE_DIR / "storage" / "logs" / "opportunities.jsonl"

logger = logging.getLogger("harvey")


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY,
            opp_id TEXT UNIQUE,
            timestamp TEXT,
            scanner_id TEXT,
            type TEXT,
            asset TEXT,
            venue TEXT,
            edge REAL,
            observe_only INTEGER,
            raw_json TEXT
        );

        CREATE TABLE IF NOT EXISTS scanner_stats (
            scanner_id TEXT PRIMARY KEY,
            signals INTEGER,
            avg_edge REAL,
            max_edge REAL,
            last_seen TEXT
        );
        """
    )


def _derive_edge(record: dict[str, Any]) -> float | None:
    """
    Derive edge value from opportunity record.

    Supports all scanner types A-H:
    - A/B/C: p2p_premium, basis_pct, spread_pct
    - D: edge_net (multi-exchange)
    - E: funding_rate, annualized_pct (funding rate)
    - F: edge_net (cross-currency)
    - G: merchant_spread_pct (merchant spread)
    - H: edge_net, deviation_pct, spread_pct (stablecoin depeg)
    """
    edge_fields = (
        "edge_net",  # D, F, H
        "p2p_premium",  # C
        "basis_pct",  # B
        "spread_pct",  # A, H
        "merchant_spread_pct",  # G
        "funding_rate",  # E
        "annualized_pct",  # E (alternative)
        "cross_premium_spread",  # F (alternative)
        "deviation_pct",  # H (alternative)
    )
    for field in edge_fields:
        value = record.get(field)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            logger.warning("Invalid edge value for opp_id=%s field=%s", record.get("opp_id"), field)
            return None
    return None


def _load_opportunities() -> list[dict[str, Any]]:
    if not OPPORTUNITIES_LOG.exists():
        logger.info("Opportunities log not found: %s", OPPORTUNITIES_LOG)
        return []

    opportunities: list[dict[str, Any]] = []
    with OPPORTUNITIES_LOG.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                record = json.loads(payload)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed JSON at line %d in %s", line_number, OPPORTUNITIES_LOG)
                continue
            if not isinstance(record, dict):
                logger.warning("Skipping non-object JSON at line %d in %s", line_number, OPPORTUNITIES_LOG)
                continue
            opportunities.append(record)
    return opportunities


def _insert_signals(conn: sqlite3.Connection, opportunities: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    inserted = 0
    new_records: list[dict[str, Any]] = []
    for record in opportunities:
        opp_id = record.get("opp_id")
        if not opp_id:
            logger.warning("Skipping opportunity without opp_id")
            continue

        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO signals (
                opp_id,
                timestamp,
                scanner_id,
                type,
                asset,
                venue,
                edge,
                observe_only,
                raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opp_id,
                record.get("ts"),
                record.get("scanner_id"),
                record.get("type"),
                record.get("asset"),
                record.get("venue"),
                _derive_edge(record),
                int(bool(record.get("observe_only", False))),
                json.dumps(record, sort_keys=True, default=str),
            ),
        )
        if cursor.rowcount:
            inserted += 1
            new_records.append(record)
    return inserted, new_records


def _refresh_scanner_stats(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM scanner_stats")
    conn.execute(
        """
        INSERT INTO scanner_stats (scanner_id, signals, avg_edge, max_edge, last_seen)
        SELECT
            scanner_id,
            COUNT(*) AS signals,
            AVG(edge) AS avg_edge,
            MAX(edge) AS max_edge,
            MAX(timestamp) AS last_seen
        FROM signals
        WHERE scanner_id IS NOT NULL
        GROUP BY scanner_id
        """
    )


def ingest_opportunities() -> dict[str, int]:
    opportunities = _load_opportunities()
    new_records: list[dict[str, Any]] = []
    with _get_conn() as conn:
        _ensure_schema(conn)
        inserted, new_records = _insert_signals(conn, opportunities)
        _refresh_scanner_stats(conn)
        conn.commit()

    if new_records:
        try:
            import sys as _sys

            _sys.path.insert(0, str(BASE_DIR))
            from database.postgres import save_opportunity

            for record in new_records:
                save_opportunity(record)
            logger.info("HARVEY→PG sync: %d new opportunities written", len(new_records))
        except Exception as e:
            logger.warning("HARVEY→PG sync failed (non-fatal): %s", e)

    logger.info(
        "HARVEY ingest complete: scanned=%d inserted=%d db=%s",
        len(opportunities),
        inserted,
        DB_PATH,
    )
    return {
        "scanned": len(opportunities),
        "inserted": inserted,
    }


def get_top_edges(limit: int = 10) -> list[dict[str, Any]]:
    """
    Return the highest-magnitude signals ordered by absolute edge descending.

    Args:
        limit: Maximum number of signals to return.
    """
    safe_limit = max(1, int(limit))
    with _get_conn() as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT
                opp_id,
                timestamp,
                scanner_id,
                type,
                asset,
                venue,
                edge,
                observe_only
            FROM signals
            WHERE edge IS NOT NULL
            ORDER BY ABS(edge) DESC, timestamp DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_scanner_performance() -> list[dict[str, Any]]:
    """
    Return scanner performance rows in a friendly list-of-dicts structure.
    """
    with _get_conn() as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT scanner_id, signals, avg_edge, max_edge, last_seen
            FROM scanner_stats
            ORDER BY signals DESC, scanner_id ASC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_asset_statistics() -> list[dict[str, Any]]:
    """
    Return counts of stored signals grouped by asset.
    """
    with _get_conn() as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT
                COALESCE(asset, 'UNKNOWN') AS asset,
                COUNT(*) AS signals
            FROM signals
            GROUP BY COALESCE(asset, 'UNKNOWN')
            ORDER BY signals DESC, asset ASC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_venue_statistics() -> list[dict[str, Any]]:
    """
    Return counts of stored signals grouped by venue.
    """
    with _get_conn() as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT
                COALESCE(venue, 'UNKNOWN') AS venue,
                COUNT(*) AS signals
            FROM signals
            GROUP BY COALESCE(venue, 'UNKNOWN')
            ORDER BY signals DESC, venue ASC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_signal_type_statistics() -> list[dict[str, Any]]:
    """
    Return counts of stored signals grouped by signal type.
    """
    with _get_conn() as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT
                COALESCE(type, 'UNKNOWN') AS type,
                COUNT(*) AS signals
            FROM signals
            GROUP BY COALESCE(type, 'UNKNOWN')
            ORDER BY signals DESC, type ASC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def daily_exposure(fiat: str, date: str | None = None) -> float:
    """
    Return total USD exposure for a given fiat market from batman.db for the given date.

    Aggregates depth_estimate (capped at $1,000 per opportunity) from today's signals.
    This is the single source of truth for exposure in Batman Lab.

    Args:
        fiat: Currency code (e.g., "MXN", "ARS").
        date: ISO date string YYYY-MM-DD. Defaults to today UTC.

    Returns:
        Total USD exposure rounded to 2 decimal places.

    Example output:
        >>> daily_exposure("MXN")
        800.0
        >>> daily_exposure("ARS", date="2026-03-26")
        300.0
    """
    import datetime as _dt

    if date is None:
        date = _dt.datetime.now(_dt.timezone.utc).date().isoformat()

    fiat_upper = fiat.upper()
    total_usd = 0.0

    with _get_conn() as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT raw_json FROM signals WHERE timestamp LIKE ?",
            (f"{date}%",),
        ).fetchall()

    for row in rows:
        try:
            record = json.loads(row["raw_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        market = record.get("market", "")
        if market.upper() != fiat_upper:
            continue
        depth = record.get("depth_estimate", 0)
        if depth and depth > 0:
            total_usd += min(float(depth), 1000.0)

    return round(total_usd, 2)
