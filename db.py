import sqlite3
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
DB_PATH = "audit_log.db"


def init_db():
    """Create the audit_log table if it doesn't exist.
    ALTER the table to add columns after creating it is unnecessary now.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    content_id TEXT,
                    creator_id TEXT,
                    timestamp TEXT,
                    attribution TEXT,
                    confidence REAL,
                    llm_score REAL,
                    stylometric_score REAL,
                    label TEXT,
                    status TEXT,
                    appeal_reasoning TEXT,
                    appeal_timestamp TEXT
                )
            """)
    except Exception:
        logger.exception("Failed to initialize audit_log database at %s", DB_PATH)
        raise

def log_event(entry):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO audit_log "
                "(content_id, creator_id, timestamp, attribution, confidence, llm_score, stylometric_score, label, status) "
                "VALUES (:content_id, :creator_id, :timestamp, :attribution, :confidence, :llm_score, :stylometric_score, :label, :status)",
                {**entry, "timestamp": datetime.now(timezone.utc).isoformat()},
            )
    except Exception:
        logger.exception("Failed to write audit log entry: %s", entry)
        raise

def get_entry(content_id):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM audit_log WHERE content_id = ?", (content_id,)
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        logger.exception("Failed to read audit log entry for content_id=%s", content_id)
        return None

def log_appeal(content_id, appeal_reasoning):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE audit_log SET status = 'under_review', "
                "appeal_reasoning = :reasoning, appeal_timestamp = :ts "
                "WHERE content_id = :content_id",
                {
                    "content_id": content_id,
                    "reasoning": appeal_reasoning,
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
            )
    except Exception:
        logger.exception("Failed to log appeal for content_id=%s", content_id)
        raise

def read_log(limit=20):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        logger.exception("Failed to read audit log (limit=%s)", limit)
        return []

