import sqlite3
from datetime import datetime, timezone

DB_PATH = "audit_log.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                content_id TEXT,
                creator_id TEXT,
                timestamp  TEXT,
                attribution TEXT,
                confidence REAL,
                llm_score REAL,
                stylometric_score REAL,
                status TEXT
            )
        """)
        for col in ("llm_score REAL", "stylometric_score REAL"):
            try:
                conn.execute(f"ALTER TABLE audit_log ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass

def log_event(entry):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO audit_log "
            "(content_id, creator_id, timestamp, attribution, confidence, llm_score, stylometric_score, status) "
            "VALUES (:content_id, :creator_id, :timestamp, :attribution, :confidence, :llm_score, :stylometric_score, :status)",
            {**entry, "timestamp": datetime.now(timezone.utc).isoformat()},
        )

def read_log(limit=20):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]

