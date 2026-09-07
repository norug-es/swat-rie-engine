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
        con.execute("""
        CREATE TABLE IF NOT EXISTS media_artifacts (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            input_type TEXT NOT NULL,
            response_json TEXT NOT NULL
        )
        """)
    from .auth import init_auth_db
    init_auth_db()

def save_investigation(iid: str, created_at: str, verdict: str, confidence: float, request: dict, response: dict, owner_id: str | None = None) -> None:
    init_db()
    with sqlite3.connect(_path()) as con:
        con.execute(
            "INSERT INTO investigations (id, created_at, verdict, confidence, request_json, response_json, owner_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (iid, created_at, verdict, confidence, json.dumps(request), json.dumps(response), owner_id),
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

def save_media_artifact(artifact: dict) -> None:
    init_db()
    with sqlite3.connect(_path()) as con:
        con.execute(
            "INSERT OR REPLACE INTO media_artifacts VALUES (?, ?, ?, ?, ?)",
            (
                artifact["artifact_id"],
                artifact["created_at"],
                artifact["sha256"],
                artifact["input_type"],
                json.dumps(artifact),
            ),
        )

def get_media_artifact(artifact_id: str) -> dict | None:
    init_db()
    with sqlite3.connect(_path()) as con:
        row = con.execute(
            "SELECT response_json FROM media_artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()
    return json.loads(row[0]) if row else None

def find_media_artifact_by_hash(sha256: str) -> dict | None:
    init_db()
    with sqlite3.connect(_path()) as con:
        row = con.execute(
            "SELECT response_json FROM media_artifacts WHERE sha256 = ? ORDER BY created_at DESC LIMIT 1",
            (sha256,),
        ).fetchone()
    return json.loads(row[0]) if row else None
