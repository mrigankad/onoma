"""Single sign-on with any OpenID Connect provider (Entra ID, Google, Okta, Keycloak, Authentik...).

Authorization-code flow with PKCE. The engine talks to the provider over the back channel, so the
browser never sees the client secret. Configure with:
  ONOMA_OIDC_ISSUER          https://login.example.com/realms/acme
  ONOMA_OIDC_CLIENT_ID       onoma
  ONOMA_OIDC_CLIENT_SECRET   (optional for public clients)
  ONOMA_OIDC_REDIRECT        http://localhost:3000/login/callback   (the console page)
  ONOMA_OIDC_DEFAULT_ROLE    viewer
  ONOMA_OIDC_ALLOWED_DOMAINS example.org,example.com   (optional)
First sign-in creates the account with the default role; admins promote people afterwards.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode

import httpx

from .auth import Accounts, User
from .db import Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS oidc_states (
  state      TEXT PRIMARY KEY,
  verifier   TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
"""


class OidcError(Exception):
    pass


class Oidc:
    def __init__(self, db: Database, accounts: Accounts, http: httpx.Client | None = None) -> None:
        self.db, self.accounts = db, accounts
        self.issuer = os.getenv("ONOMA_OIDC_ISSUER", "").rstrip("/")
        self.client_id = os.getenv("ONOMA_OIDC_CLIENT_ID", "")
        self.secret = os.getenv("ONOMA_OIDC_CLIENT_SECRET", "")
        self.redirect = os.getenv("ONOMA_OIDC_REDIRECT", "http://localhost:3000/login/callback")
        self.role = os.getenv("ONOMA_OIDC_DEFAULT_ROLE", "viewer")
        self.domains = {d.strip().lower() for d in os.getenv("ONOMA_OIDC_ALLOWED_DOMAINS", "").split(",") if d.strip()}
        self.http = http or httpx.Client(timeout=15)
        self._meta: dict | None = None
        with db.lock:
            db.conn.executescript(SCHEMA)

    @property
    def enabled(self) -> bool:
        return bool(self.issuer and self.client_id)

    def metadata(self) -> dict:
        if self._meta is None:
            r = self.http.get(f"{self.issuer}/.well-known/openid-configuration")
            r.raise_for_status()
            self._meta = r.json()
        return self._meta

    def start(self) -> str:
        state = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.db.execute("DELETE FROM oidc_states WHERE expires_at < datetime('now')")
        self.db.execute("INSERT INTO oidc_states VALUES (?, ?, datetime('now', '+10 minutes'))", (state, verifier))
        self.db.commit()
        q = {"response_type": "code", "client_id": self.client_id, "redirect_uri": self.redirect,
             "scope": "openid email profile", "state": state,
             "code_challenge": challenge, "code_challenge_method": "S256"}
        return f"{self.metadata()['authorization_endpoint']}?{urlencode(q)}"

    def finish(self, code: str, state: str) -> tuple[str, User]:
        row = self.db.one("SELECT verifier FROM oidc_states WHERE state = ? AND expires_at > datetime('now')", (state,))
        self.db.execute("DELETE FROM oidc_states WHERE state = ?", (state,))  # single use
        self.db.commit()
        if not row:
            raise OidcError("Sign-in link expired or was already used. Try again.")
        meta = self.metadata()
        form = {"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect,
                "client_id": self.client_id, "code_verifier": row["verifier"]}
        if self.secret:
            form["client_secret"] = self.secret
        tok = self.http.post(meta["token_endpoint"], data=form)
        if tok.status_code != 200:
            raise OidcError("The identity provider refused the sign-in code.")
        access = tok.json().get("access_token")
        info = self.http.get(meta["userinfo_endpoint"], headers={"Authorization": f"Bearer {access}"})
        if info.status_code != 200:
            raise OidcError("Could not read your profile from the identity provider.")
        claims = info.json()
        email = (claims.get("email") or "").strip()
        if not email or claims.get("email_verified") is False:
            raise OidcError("Your identity provider did not share a verified email.")
        if self.domains and email.split("@")[-1].lower() not in self.domains:
            raise OidcError("This email domain is not allowed in this workspace.")
        user = self.accounts.find_or_create_external(email, claims.get("name") or email, self.role, "oidc")
        return self.accounts.new_session(user, via="oidc"), user
