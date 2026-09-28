"""Password hashing and signed-cookie sessions (no external auth deps)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta

from fastapi import Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import settings
from .db import row

SESSION_COOKIE = "davish_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14 days
RESET_TTL_MINUTES = 60
_serializer = URLSafeTimedSerializer(settings.SECRET, salt="session")

_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS).hex()
    return f"pbkdf2${_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
    return hmac.compare_digest(candidate, digest)


def make_session(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session(token: str | None) -> int | None:
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None
    return data.get("uid")


def set_session_cookie(resp: Response, user_id: int) -> None:
    resp.set_cookie(SESSION_COOKIE, make_session(user_id), httponly=True, samesite="lax", secure=settings.SECURE_COOKIES,
                    max_age=SESSION_MAX_AGE, path="/")


def current_user(request: Request, conn: sqlite3.Connection) -> dict | None:
    uid = read_session(request.cookies.get(SESSION_COOKIE))
    if uid is None:
        return None
    return row(conn, "SELECT id, email, name, is_host, is_admin, email_verified, bio, phone, avatar_url, created_at FROM users WHERE id = ? AND is_banned = 0", (uid,))


# ---- password reset tokens: random token emailed to the user, only its hash stored.

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_reset_token(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.utcnow() + timedelta(minutes=RESET_TTL_MINUTES)).strftime("%Y-%m-%dT%H:%M")
    conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))
    conn.execute("INSERT INTO password_resets (token_hash, user_id, expires_at) VALUES (?,?,?)", (_hash_token(token), user_id, expires))
    return token


def consume_reset_token(conn: sqlite3.Connection, token: str) -> int | None:
    """Returns the user id if the token is valid and unused, marking it used."""
    r = row(conn, "SELECT user_id, expires_at, used FROM password_resets WHERE token_hash = ?", (_hash_token(token),))
    if not r or r["used"] or r["expires_at"] < datetime.utcnow().strftime("%Y-%m-%dT%H:%M"):
        return None
    conn.execute("UPDATE password_resets SET used = 1 WHERE token_hash = ?", (_hash_token(token),))
    return r["user_id"]


def peek_reset_token(conn: sqlite3.Connection, token: str) -> bool:
    r = row(conn, "SELECT used, expires_at FROM password_resets WHERE token_hash = ?", (_hash_token(token),))
    return bool(r and not r["used"] and r["expires_at"] >= datetime.utcnow().strftime("%Y-%m-%dT%H:%M"))
