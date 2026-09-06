import json
import sqlite3
from pathlib import Path
from .config import settings

def _path() -> Path:
    prefix = "sqlite:///"
    if not settings.db_url.startswith(prefix):
        raise RuntimeError("MVP v0.1 only supports sqlite:/// URLs")
    p = Path(settings.db_url[len(prefix):])
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

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
