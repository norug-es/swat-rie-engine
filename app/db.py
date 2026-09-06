import json
import logging
import os
import sqlite3
from pathlib import Path
from tempfile import gettempdir
from .config import settings

logger = logging.getLogger(__name__)

def _path() -> Path:
    prefix = "sqlite:///"
    if not settings.db_url.startswith(prefix):
        raise RuntimeError("MVP v0.1 only supports sqlite:/// URLs")

    candidate = Path(settings.db_url[len(prefix):])
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        if candidate.exists():
            if os.access(candidate, os.W_OK):
                return candidate
        elif os.access(candidate.parent, os.W_OK | os.X_OK):
            return candidate
    except OSError:
        pass

    fallback = Path(gettempdir()) / "rie.db"
    fallback.parent.mkdir(parents=True, exist_ok=True)
    if fallback != candidate:
        logger.warning("SQLite path %s is not writable; using %s instead", candidate, fallback)
    return fallback

def init_db() -> None:
    with sqlite3.connect(_path()) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS investigations (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            verdict TEXT NOT NULL,
            confidence REAL NOT NULL,
            request_json TEXT NOT NULL,
            response_json TEXT NOT NULL
        )
        """)

def save_investigation(iid: str, created_at: str, verdict: str, confidence: float, request: dict, response: dict) -> None:
    with sqlite3.connect(_path()) as con:
        con.execute(
            "INSERT INTO investigations VALUES (?, ?, ?, ?, ?, ?)",
            (iid, created_at, verdict, confidence, json.dumps(request), json.dumps(response)),
        )

def get_investigation(iid: str) -> dict | None:
    with sqlite3.connect(_path()) as con:
        row = con.execute(
            "SELECT response_json FROM investigations WHERE id = ?", (iid,)
        ).fetchone()
    return json.loads(row[0]) if row else None

def list_investigations() -> list[dict]:
    with sqlite3.connect(_path()) as con:
        rows = con.execute("SELECT response_json FROM investigations ORDER BY created_at DESC").fetchall()
    return [json.loads(row[0]) for row in rows]

def update_investigation(iid: str, response: dict) -> None:
    with sqlite3.connect(_path()) as con:
        con.execute(
            "UPDATE investigations SET verdict = ?, confidence = ?, response_json = ? WHERE id = ?",
            (response["verdict"], response["confidence"], json.dumps(response), iid),
        )
