"""REST API (v1). Run with: onoma serve"""

from __future__ import annotations

import json
import os

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import __version__
from .auth import ROLES, Accounts, User
from .engine import Onoma
from .oidc import Oidc, OidcError


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    datasets: list[int] | None = None
    limit: int = Field(20, ge=1, le=100)


class ResolveIn(BaseModel):
    term: str = Field(min_length=1, max_length=200)


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(same|different|scope)$")


class AliasIn(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    type: str = "alias"
    scope_dataset_id: int | None = None


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class UserIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    name: str = Field("", max_length=120)
    password: str = Field(min_length=10, max_length=200)
    role: str = Field("viewer", pattern="^(viewer|steward|admin)$")


class OidcIn(BaseModel):
    code: str = Field(min_length=1, max_length=4000)
    state: str = Field(min_length=1, max_length=200)


class RoleIn(BaseModel):
    role: str = Field(pattern="^(viewer|steward|admin)$")


def create_app(engine: Onoma | None = None, api_keys: list[str] | None = None,
               oidc: Oidc | None = None) -> FastAPI:
    eng = engine or Onoma(os.getenv("ONOMA_DB", "onoma.db"))
    accounts = Accounts(eng.db)
    sso = oidc or Oidc(eng.db, accounts)
    keys = set(api_keys if api_keys is not None else [k for k in os.getenv("ONOMA_API_KEYS", "").split(",") if k])

    def principal(authorization: str | None = Header(None), x_api_key: str | None = Header(None)) -> User:
        """Who is calling. Open mode (no users, no keys) acts as a local admin."""
        token = x_api_key or (authorization or "").removeprefix("Bearer ").strip()
        if token and token in keys:
            return User(0, "api-key", "API key", "admin")
        if token:
            user = accounts.user_for_token(token)
            if user:
                return user
        if not keys and not accounts.enabled:
            return User(0, "local", "Local user", "admin")
        raise HTTPException(401, "Sign in or provide an API key")

    def role(minimum: str):
        def check(user: User = Depends(principal)) -> User:
            if not user.can(minimum):
                raise HTTPException(403, f"Needs the {minimum} role (you are {user.role})")
            return user
        return check

    viewer, steward, admin = role("viewer"), role("steward"), role("admin")

    app = FastAPI(title="Onoma", version=__version__,
                  description="Search by meaning, with a vocabulary people can see and fix.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("ONOMA_CORS", "http://localhost:3000").split(","),
        allow_methods=["*"], allow_headers=["*"],
    )
    app.state.engine = eng

    # ---------- public ----------

    @app.get("/v1/health")
    def health():
        return {"ok": True, "version": __version__, "sso": sso.enabled,
                "auth": "accounts" if accounts.enabled else ("api-key" if keys else "open")}

    @app.get("/v1/auth/oidc/start")
    def oidc_start():
        if not sso.enabled:
            raise HTTPException(404, "Single sign-on is not configured")
        try:
            return {"url": sso.start()}
        except Exception as e:
            raise HTTPException(502, "Could not reach the identity provider") from e

    @app.post("/v1/auth/oidc/callback")
    def oidc_callback(body: OidcIn):
        if not sso.enabled:
            raise HTTPException(404, "Single sign-on is not configured")
        try:
            token, user = sso.finish(body.code, body.state)
        except OidcError as e:
            raise HTTPException(401, str(e)) from e
        return {"token": token, "user": user.__dict__}

    @app.post("/v1/auth/login")
    def login(body: LoginIn):
        res = accounts.login(body.email, body.password)
        if not res:
            raise HTTPException(401, "Wrong email or password")
        token, user = res
        return {"token": token, "user": user.__dict__}

    # ---------- account ----------

    @app.get("/v1/auth/me")
    def me(user: User = Depends(principal)):
        return user.__dict__

    @app.post("/v1/auth/logout")
    def logout(authorization: str | None = Header(None)):
        token = (authorization or "").removeprefix("Bearer ").strip()
        if token:
            accounts.logout(token)
        return {"ok": True}

    @app.get("/v1/users")
    def users(_: User = Depends(admin)):
        return accounts.list()

    @app.post("/v1/users")
    def create_user(body: UserIn, user: User = Depends(admin)):
        try:
            return accounts.create(body.email, body.name, body.password, body.role).__dict__
        except Exception as e:  # duplicate email or validation
            raise HTTPException(400, str(e)) from e

    @app.patch("/v1/users/{user_id}")
    def set_role(user_id: int, body: RoleIn, user: User = Depends(admin)):
        try:
            accounts.set_role(user_id, body.role, user.email)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True}

    # ---------- viewer ----------

    @app.get("/v1/config")
    def config(_: User = Depends(viewer)):
        from .models import ModelGateway

        gw = ModelGateway()
        return {"version": __version__,
                "auth": "accounts" if accounts.enabled else ("api-key" if keys else "open"),
                "roles": list(ROLES),
                "model": {"enabled": gw.enabled, "provider": gw.provider or None, "name": gw.model or None},
                "meaning_search": eng.vectors is not None,
                "mcp": {"command": "onoma", "args": ["--db", eng.db.path, "mcp"]},
                "tools": ["onoma_search", "onoma_resolve", "onoma_suggest_alias"]}

    @app.get("/v1/stats")
    def stats(_: User = Depends(viewer)):
        return eng.stats()

    @app.post("/v1/search")
    def search(body: SearchIn, _: User = Depends(viewer)):
        return eng.search(body.query, body.datasets, body.limit)

    @app.post("/v1/resolve")
    def resolve(body: ResolveIn, _: User = Depends(viewer)):
        return {"term": body.term, "entities": eng.searcher.resolve(body.term)}

    @app.get("/v1/datasets")
    def datasets(_: User = Depends(viewer)):
        return eng.ingestor.datasets()

    @app.get("/v1/entities")
    def entities(q: str = "", limit: int = 50, _: User = Depends(viewer)):
        return eng.vocab.list_entities(q, limit)

    @app.get("/v1/entities/{entity_id}")
    def entity(entity_id: int, _: User = Depends(viewer)):
        e = eng.vocab.entity(entity_id)
        if not e:
            raise HTTPException(404, "Entity not found")
        return e

    @app.get("/v1/suggestions")
    def suggestions(limit: int = 50, _: User = Depends(viewer)):
        return eng.review.queue(limit)

    @app.get("/v1/insights")
    def insights(_: User = Depends(viewer)):
        return {"failed_queries": eng.insights.failed_queries(), "stats": eng.stats()}

    @app.get("/v1/packs")
    def packs(_: User = Depends(viewer)):
        installed = eng.vocab.installed_packs()
        return [p | {"installed": p["id"] in installed} for p in eng.vocab.available_packs()]

    @app.get("/v1/vocabulary/export")
    def export(include_packs: bool = False, _: User = Depends(viewer)):
        return eng.vocab.export_pack(include_packs=include_packs)

    # ---------- steward ----------

    @app.post("/v1/datasets")
    async def upload(file: UploadFile = File(...), name: str | None = Form(None), user: User = Depends(steward)):
        data = await file.read()
        if len(data) > 50 * 1024 * 1024:
            raise HTTPException(413, "File larger than 50 MB")
        try:
            res = eng.import_file(file.filename or "upload.csv", data, name)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        eng.db.audit(user.email, "dataset.uploaded", {"file": file.filename})
        eng.db.commit()
        return res

    @app.post("/v1/entities/{entity_id}/aliases")
    def add_alias(entity_id: int, body: AliasIn, user: User = Depends(steward)):
        if not eng.vocab.entity(entity_id):
            raise HTTPException(404, "Entity not found")
        alias_id = eng.vocab.add_alias(entity_id, body.term, body.type, "manual", body.scope_dataset_id,
                                       actor=user.email)
        eng.db.commit()
        return {"id": alias_id}

    @app.delete("/v1/aliases/{alias_id}")
    def remove_alias(alias_id: int, user: User = Depends(steward)):
        eng.vocab.remove_alias(alias_id, actor=user.email)
        eng.db.commit()
        return {"ok": True}

    @app.post("/v1/suggestions/{suggestion_id}/decision")
    def decide(suggestion_id: int, body: DecisionIn, user: User = Depends(steward)):
        try:
            return eng.review.decide(suggestion_id, body.decision, user.email)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e

    # ---------- admin ----------

    @app.post("/v1/agents/{agent}/run")
    def run_agent(agent: str, _: User = Depends(admin)):
        if agent == "alias-miner":
            return {"created": eng.miner.run()}
        if agent == "insights-analyst":
            return {"created": eng.insights.run()}
        raise HTTPException(404, "Unknown agent")

    @app.post("/v1/vocabulary/import")
    async def import_vocab(file: UploadFile = File(...), user: User = Depends(admin)):
        try:
            data = json.loads((await file.read()).decode("utf-8"))
            return {"entities": eng.vocab.import_pack(data, actor=user.email)}
        except (ValueError, UnicodeDecodeError) as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/v1/packs/{pack_id}/install")
    def install(pack_id: str, user: User = Depends(admin)):
        try:
            return {"entities": eng.vocab.install_pack(pack_id, actor=user.email)}
        except KeyError as e:
            raise HTTPException(404, str(e)) from e

    return app
