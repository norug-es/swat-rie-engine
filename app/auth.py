import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from .db import _path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return f"pbkdf2_sha256$240000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def init_auth_db() -> None:
    with __import__("sqlite3").connect(_path()) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, reset_token_hash TEXT, reset_expires_at TEXT
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS qr_challenges (
            id TEXT PRIMARY KEY, user_id TEXT, secret_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL, approved_at TEXT
        )
        """)
        try:
            con.execute("ALTER TABLE investigations ADD COLUMN owner_id TEXT")
        except __import__("sqlite3").OperationalError:
            pass


def create_user(user_id: str, email: str, password: str) -> None:
    init_auth_db()
    with __import__("sqlite3").connect(_path()) as con:
        con.execute("INSERT INTO users VALUES (?, ?, ?, ?, NULL, NULL)", (user_id, email.lower(), hash_password(password), now()))


def get_user_by_email(email: str) -> dict | None:
    init_auth_db()
    with __import__("sqlite3").connect(_path()) as con:
        con.row_factory = __import__("sqlite3").Row
        row = con.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    return dict(row) if row else None


def get_user(user_id: str) -> dict | None:
    init_auth_db()
    with __import__("sqlite3").connect(_path()) as con:
        con.row_factory = __import__("sqlite3").Row
        row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def create_session(user_id: str, days: int = 7) -> str:
    init_auth_db()
    session_id = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=days)
    with __import__("sqlite3").connect(_path()) as con:
        con.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", (session_id, user_id, now(), expires.isoformat()))
    return session_id


def get_user_by_session(session_id: str | None) -> dict | None:
    init_auth_db()
    if not session_id:
        return None
    with __import__("sqlite3").connect(_path()) as con:
        con.row_factory = __import__("sqlite3").Row
        row = con.execute("""
            SELECT u.* FROM users u JOIN sessions s ON s.user_id = u.id
            WHERE s.id = ? AND s.expires_at > ?
        """, (session_id, now())).fetchone()
    return dict(row) if row else None


def delete_session(session_id: str | None) -> None:
    init_auth_db()
    if session_id:
        with __import__("sqlite3").connect(_path()) as con:
            con.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def create_reset_token(email: str) -> str | None:
    user = get_user_by_email(email)
    if not user:
        return None
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=20)
    with __import__("sqlite3").connect(_path()) as con:
        con.execute("UPDATE users SET reset_token_hash = ?, reset_expires_at = ? WHERE id = ?", (hashlib.sha256(token.encode()).hexdigest(), expires.isoformat(), user["id"]))
    return token


def reset_password(token: str, password: str) -> bool:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with __import__("sqlite3").connect(_path()) as con:
        row = con.execute("SELECT id FROM users WHERE reset_token_hash = ? AND reset_expires_at > ?", (token_hash, now())).fetchone()
        if not row:
            return False
        con.execute("UPDATE users SET password_hash = ?, reset_token_hash = NULL, reset_expires_at = NULL WHERE id = ?", (hash_password(password), row[0]))
    return True


def create_qr_challenge(user_id: str | None = None) -> tuple[str, str]:
    init_auth_db()
    challenge_id = secrets.token_urlsafe(18)
    secret = secrets.token_urlsafe(28)
    expires = datetime.now(timezone.utc) + timedelta(minutes=3)
    with __import__("sqlite3").connect(_path()) as con:
        con.execute("INSERT INTO qr_challenges VALUES (?, ?, ?, ?, ?, NULL)", (challenge_id, user_id, hashlib.sha256(secret.encode()).hexdigest(), now(), expires.isoformat()))
    return challenge_id, secret


def approve_qr(challenge_id: str, secret: str, user_id: str) -> bool:
    init_auth_db()
    with __import__("sqlite3").connect(_path()) as con:
        row = con.execute("SELECT secret_hash FROM qr_challenges WHERE id = ? AND expires_at > ? AND approved_at IS NULL", (challenge_id, now())).fetchone()
        if not row or not hmac.compare_digest(row[0], hashlib.sha256(secret.encode()).hexdigest()):
            return False
        con.execute("UPDATE qr_challenges SET user_id = ?, approved_at = ? WHERE id = ?", (user_id, now(), challenge_id))
    return True


def consume_qr(challenge_id: str, secret: str) -> dict | None:
    init_auth_db()
    with __import__("sqlite3").connect(_path()) as con:
        con.row_factory = __import__("sqlite3").Row
        row = con.execute("""
            SELECT u.* FROM qr_challenges q JOIN users u ON q.user_id = u.id
            WHERE q.id = ? AND q.secret_hash = ? AND q.approved_at IS NOT NULL AND q.expires_at > ?
        """, (challenge_id, hashlib.sha256(secret.encode()).hexdigest(), now())).fetchone()
    return dict(row) if row else None
