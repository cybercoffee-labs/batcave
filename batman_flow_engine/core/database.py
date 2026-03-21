import sqlite3
import pathlib
import pandas as pd
from datetime import datetime

DB_PATH = pathlib.Path("storage/batman.db")


def get_conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        ts TEXT NOT NULL,
        px REAL,
        UNIQUE(symbol, ts)
    );
    CREATE TABLE IF NOT EXISTS returns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        ts TEXT NOT NULL,
        ret_log REAL,
        ret_1d REAL,
        UNIQUE(symbol, ts)
    );
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        ts TEXT NOT NULL,
        vol_z REAL,
        rvol REAL,
        flow_score REAL,
        risk_score REAL,
        regime TEXT,
        UNIQUE(symbol, ts)
    );
    CREATE TABLE IF NOT EXISTS engine_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        regime TEXT,
        dq_status TEXT,
        eq_ratio REAL,
        narrative_hits INTEGER
    );
    """)
    conn.commit()
    conn.close()
    print("✅ DB inicializada:", DB_PATH)


def save_engine_run(data: dict):
    conn = get_conn()
    stress = data.get("stress", {}).get("regime", {})
    dq = data.get("dq", {})
    narrative = data.get("narrative", {})
    conn.execute(
        """
        INSERT INTO engine_runs (ts, regime, dq_status, eq_ratio, narrative_hits)
        VALUES (?, ?, ?, ?, ?)
    """,
        (
            datetime.utcnow().isoformat(),
            stress.get("label"),
            dq.get("overall_status"),
            dq.get("equities_ok_ratio"),
            narrative.get("total_hits", 0),
        ),
    )
    conn.commit()
    conn.close()


def save_metrics(symbol: str, metrics: dict):
    conn = get_conn()
    conn.execute(
        """
        INSERT OR REPLACE INTO metrics (symbol, ts, vol_z, rvol, flow_score, risk_score, regime)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            symbol,
            datetime.utcnow().isoformat(),
            metrics.get("vol_z"),
            metrics.get("rvol"),
            metrics.get("flow_score"),
            metrics.get("risk_score"),
            metrics.get("regime"),
        ),
    )
    conn.commit()
    conn.close()


def query(sql: str) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(sql, conn)
    conn.close()
    return df


if __name__ == "__main__":
    init_db()
