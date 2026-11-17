"""Built-in accounts, sessions and roles.

Auth is off until the first user exists (solo mode stays zero-setup). Once on, every /v1 call
needs a session token or an API key. Roles:
  viewer   search, browse vocabulary, insights
  steward  + decide suggestions, edit aliases, upload data
  admin    + install/import packs, run agents, manage users
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from .db import Database

ROLES = ("viewer", "steward", "admin")
SESSION_HOURS = 12

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id         INTEGER PRIMARY KEY,
  email      TEXT NOT NULL UNIQUE COLLATE NOCASE,
  name       TEXT NOT NULL,
  role       TEXT NOT NULL CHECK (role IN ('viewer', 'steward', 'admin')),
  pw_hash    TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL
);
"""


@dataclass
class User:
    id: int
    email: str
    name: str
    role: str

    def can(self, role: str) -> bool:
        return ROLES.index(self.role) >= ROLES.index(role)


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def _check_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    candidate = _hash_password(password, bytes.fromhex(salt_hex)).split("$")[2]
    return hmac.compare_digest(candidate, digest_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    def __init__(self, db: Database) -> None:
        self.db = db
        with db.lock:
            db.conn.executescript(SCHEMA)

    @property
    def enabled(self) -> bool:
        return self.db.one("SELECT COUNT(*) FROM users")[0] > 0

    def create(self, email: str, name: str, password: str, role: str = "viewer") -> User:
        if role not in ROLES:
            raise ValueError(f"role must be one of {', '.join(ROLES)}")
        if len(password) < 10:
            raise ValueError("password must be at least 10 characters")
        if "@" not in email:
            raise ValueError("email looks invalid")
        cur = self.db.execute(
            "INSERT INTO users (email, name, role, pw_hash) VALUES (?, ?, ?, ?)",
            (email.strip(), name.strip() or email, role, _hash_password(password)),
        )
        self.db.audit("system", "user.created", {"email": email, "role": role})
        self.db.commit()
        return User(cur.lastrowid, email.strip(), name.strip() or email, role)

    def list(self) -> list[dict]:
        return [dict(r) for r in self.db.query("SELECT id, email, name, role, created_at FROM users ORDER BY email")]

    def set_role(self, user_id: int, role: str, actor: str) -> None:
        if role not in ROLES:
            raise ValueError("unknown role")
        others = self.db.one("SELECT COUNT(*) FROM users WHERE role = 'admin' AND id != ?", (user_id,))[0]
        if role != "admin" and others == 0:
            raise ValueError("Keep at least one admin")
        self.db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        self.db.audit(actor, "user.role", {"user_id": user_id, "role": role})
        self.db.commit()

    def login(self, email: str, password: str) -> tuple[str, User] | None:
        row = self.db.one("SELECT * FROM users WHERE email = ?", (email.strip(),))
        # Always run the hash so timing doesn't reveal which emails exist.
        ok = _check_password(password, row["pw_hash"] if row else _hash_password("x"))
        if not (row and ok):
            return None
        user = User(row["id"], row["email"], row["name"], row["role"])
        return self.new_session(user), user

    def new_session(self, user: User, via: str = "password") -> str:
        token = secrets.token_urlsafe(32)
        self.db.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, datetime('now', ?))",
            (_token_hash(token), user.id, f"+{SESSION_HOURS} hours"),
        )
        self.db.execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
        self.db.audit(user.email, "user.login", {"via": via})
        self.db.commit()
        return token

    def find_or_create_external(self, email: str, name: str, role: str, via: str) -> User:
        """Single sign-on accounts have no password; they can only sign in through the provider."""
        row = self.db.one("SELECT * FROM users WHERE email = ?", (email,))
        if row:
            return User(row["id"], row["email"], row["name"], row["role"])
        cur = self.db.execute("INSERT INTO users (email, name, role, pw_hash) VALUES (?, ?, ?, ?)",
                              (email, name, role, f"external:{via}"))
        self.db.audit("system", "user.created", {"email": email, "role": role, "via": via})
        self.db.commit()
        return User(cur.lastrowid, email, name, role)

    def user_for_token(self, token: str) -> User | None:
        row = self.db.one(
            """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ? AND s.expires_at > datetime('now')""",
            (_token_hash(token),),
        )
        return User(row["id"], row["email"], row["name"], row["role"]) if row else None

    def logout(self, token: str) -> None:
        self.db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
        self.db.commit()
