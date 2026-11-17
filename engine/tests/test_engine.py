"""End-to-end tests on the bundled demo: these are the promises the product makes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from onoma.api import create_app
from onoma.engine import Onoma
from onoma.ingest import infer_columns


@pytest.fixture()
def eng() -> Onoma:
    e = Onoma(":memory:")
    e.load_demo()
    return e


def titles(res: dict) -> list[str]:
    return [h["title"] for h in res["hits"]]


def test_schema_scout_roles_and_personal_data_skipped():
    rows = [{"Full Name": f"Person {i}", "Skills": "k8s, Go", "Experience (yrs)": str(i),
             "Phone": f"+91 98200 1{i:04d}", "Note ID": f"N-{1000 + i}"} for i in range(20)]
    roles = {m.name: m.role for m in infer_columns(rows)}
    assert roles["Phone"] == "personal"
    assert roles["Experience (yrs)"] == "number"
    assert roles["Note ID"] != "number"  # "N-1008" is an identifier, not a number
    assert roles["Full Name"] == "title"


def test_personal_columns_never_stored(eng):
    for r in eng.db.query("SELECT fields FROM records"):
        assert "Phone" not in r["fields"]


def test_lay_term_finds_clinical_terms_with_numeric_filter(eng):
    res = eng.search("heart attack in patients over 60")
    found = titles(res)
    assert any("NSTEMI" in t for t in found)
    assert any("post-MI" in t for t in found)
    assert not any("ruled out" in t for t in found)  # age 44 and not an MI alias
    for h in res["hits"]:
        assert any(w["step"] == "filter" for w in h["why"])


def test_typo_correction_and_percent_filter(eng):
    res = eng.search("hydrocloric acid under 40%")
    assert res["understood"]["corrections"][0]["to"] == "hydrochloric acid"
    found = titles(res)
    assert "Muriatic acid, drum 200 kg" in found
    assert "ACL 30 PCT BULK TK-4" in found
    assert not any("knee" in t for t in found)  # scoped alias must not leak into clinical notes
    assert all(float(h["fields"]["Concentration"].rstrip("%")) < 40 for h in res["hits"])


def test_same_abbreviation_means_different_things_per_dataset(eng):
    res = eng.search("ACL")
    by_dataset = {h["dataset"]: h["matched_via"]["entity"] for h in res["hits"]}
    assert by_dataset["Clinical Notes"] == "Anterior cruciate ligament injury"
    assert by_dataset["Parts Stock"] == "Hydrochloric acid"


def test_units_and_grades_match_written_variants(eng):
    found = titles(eng.search("SS304 flange 2in"))
    assert set(found) == {"Flange WN DN50 AISI304", 'Slip-on flange 2" SS 304', "Blind flange 50NB stainless 304"}


def test_alias_miner_suggests_and_human_decision_goes_live(eng):
    queue = {c["term"]: c for c in eng.review.queue()}
    assert "k8s" in queue and queue["k8s"]["entity"] == "Kubernetes"
    assert "Reactjs" in queue or "React.js" in queue

    before = eng.search("kubernetes")
    assert "A. Menon" not in titles(before)  # writes "k8s"

    eng.review.decide(queue["k8s"]["id"], "same")
    after = eng.search("kubernetes")
    assert "A. Menon" in titles(after)
    hit = next(h for h in after["hits"] if h["title"] == "A. Menon")
    assert hit["matched_via"]["source"] == "agent:alias-miner"


def test_rejected_suggestion_is_not_suggested_again(eng):
    card = next(c for c in eng.review.queue() if c["term"] == "Kubernets")
    eng.review.decide(card["id"], "different")
    eng.miner.run()
    assert not any(c["term"] == "Kubernets" for c in eng.review.queue())


def test_agents_only_write_suggestions(eng):
    before = eng.db.one("SELECT COUNT(*) FROM aliases")[0]
    eng.miner.run()
    eng.search("cardiac arest icd")
    eng.insights.run()
    assert eng.db.one("SELECT COUNT(*) FROM aliases")[0] == before


def test_api_round_trip(eng):
    client = TestClient(create_app(eng))
    assert client.get("/v1/health").json()["ok"]
    res = client.post("/v1/search", json={"query": "high blood pressure"}).json()
    assert res["total"] >= 2
    sugg = client.get("/v1/suggestions").json()
    assert sugg and sugg[0]["reason"]
    r = client.post(f"/v1/suggestions/{sugg[0]['id']}/decision", json={"decision": "same"})
    assert r.status_code == 200
    packs = client.get("/v1/packs").json()
    assert all(p["installed"] for p in packs)
    up = client.post("/v1/datasets", files={"file": ("tiny.csv", b"Product,Category\nRunning trainers,Shoes\n")})
    assert up.status_code == 200
    assert "Running trainers" in [h["title"] for h in client.post("/v1/search", json={"query": "sneakers"}).json()["hits"]]


def test_mcp_tools_search_and_suggest_only(eng):
    from onoma.mcp import handle

    init = handle(eng, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
    assert init["result"]["serverInfo"]["name"] == "onoma"
    tools = handle(eng, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert {t["name"] for t in tools} == {"onoma_search", "onoma_resolve", "onoma_suggest_alias"}
    res = handle(eng, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "onoma_search", "arguments": {"query": "high blood pressure"}}})
    assert "amlodipine" in res["result"]["content"][0]["text"]
    before = eng.db.one("SELECT COUNT(*) FROM aliases")[0]
    sug = handle(eng, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                       "params": {"name": "onoma_suggest_alias",
                                  "arguments": {"term": "BP", "meaning": "Hypertension", "reason": "common shorthand"}}})
    assert '"queued": true' in sug["result"]["content"][0]["text"]
    assert eng.db.one("SELECT COUNT(*) FROM aliases")[0] == before  # agents cannot make anything live
    assert any(c["term"] == "BP" and c["agent"] == "mcp-agent" for c in eng.review.queue())
    assert handle(eng, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_near_meaning_fallback(eng):
    res = eng.search("hypertensoin meds")  # misspelt beyond the typo threshold, plus an unknown word
    assert res["understood"]["did_you_mean"] or res["total"] > 0
    for h in res["hits"]:
        if h["matched_via"] is None:
            assert "not a known meaning" in h["why"][0]["text"]


def test_api_keys_when_configured(eng):
    client = TestClient(create_app(eng, api_keys=["secret"]))
    assert client.get("/v1/health").status_code == 200
    assert client.get("/v1/stats").status_code == 401
    assert client.get("/v1/stats", headers={"Authorization": "Bearer secret"}).status_code == 200
    assert client.get("/v1/config", headers={"X-API-Key": "secret"}).json()["auth"] == "api-key"


def test_golden_queries_quality_gate():
    from onoma.eval import check, run

    report = run()
    assert check(report) == [], report["summary"]
    assert report["summary"]["leaks"] == 0


class ConceptEmbedder:
    """Stand-in for a real embedding model: words map to shared concept dimensions."""

    name = "test:concepts"
    CONCEPTS = {"troponin": 0, "enzyme": 0, "enzymes": 0, "marker": 0, "cardiac": 1, "heart": 1,
                "raised": 2, "rising": 2, "elevated": 2, "high": 2}

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * 8
            for w in t.lower().replace(",", " ").replace(".", " ").split():
                if w in self.CONCEPTS:
                    v[self.CONCEPTS[w]] += 1.0
            v[7] = 0.1  # avoid zero vectors
            out.append(v)
        return out


def test_meaning_search_adds_labelled_rows():
    e = Onoma(":memory:", embedder=ConceptEmbedder())
    e.load_demo()
    assert e.db.one("SELECT COUNT(*) FROM record_vectors")[0] == e.db.one("SELECT COUNT(*) FROM records")[0]
    res = e.search("elevated cardiac enzyme")
    hit = next(h for h in res["hits"] if h["title"].startswith("NSTEMI"))
    assert hit["matched_via"] is None
    assert any(w["step"] == "meaning" for w in hit["why"])


def test_meaning_search_outage_degrades_gracefully():
    class Broken(ConceptEmbedder):
        fail = False

        def embed(self, texts):
            if self.fail:
                raise ConnectionError("provider down")
            return super().embed(texts)

    emb = Broken()
    e = Onoma(":memory:", embedder=emb)
    e.load_demo()
    emb.fail = True
    res = e.search("heart attack")
    assert res["total"] >= 4  # vocabulary search still works


def test_export_import_round_trip(eng):
    card = next(c for c in eng.review.queue() if c["term"] == "k8s")
    eng.review.decide(card["id"], "same")
    pack = eng.vocab.export_pack()
    kube = next(e for e in pack["entities"] if e["label"] == "Kubernetes")
    assert [a["term"] for a in kube["aliases"]] == ["k8s"]  # only the team's own decisions
    acid = next(e for e in pack["entities"] if e["label"] == "Hydrochloric acid")
    assert acid["aliases"][0]["scope"] == "Parts Stock"

    fresh = Onoma(":memory:")
    fresh.load_demo()
    assert fresh.vocab.import_pack(pack) >= 2
    assert "A. Menon" in titles(fresh.search("kubernetes"))
    with pytest.raises(ValueError):
        fresh.vocab.import_pack({"oops": 1})



def test_accounts_roles_and_audit(eng):
    from onoma.auth import Accounts

    client = TestClient(create_app(eng))
    assert client.get("/v1/health").json()["auth"] == "open"
    acc = Accounts(eng.db)
    acc.create("dana@example.org", "Dana", "correct horse battery", "steward")
    acc.create("vic@example.org", "Vic", "another long pass", "viewer")
    assert client.get("/v1/stats").status_code == 401  # sign-in now required

    bad = client.post("/v1/auth/login", json={"email": "dana@example.org", "password": "wrong password"})
    assert bad.status_code == 401
    dana = client.post("/v1/auth/login", json={"email": "dana@example.org", "password": "correct horse battery"}).json()
    vic = client.post("/v1/auth/login", json={"email": "vic@example.org", "password": "another long pass"}).json()
    H = lambda t: {"Authorization": f"Bearer {t['token']}"}  # noqa: E731

    assert client.get("/v1/auth/me", headers=H(vic)).json()["role"] == "viewer"
    assert client.post("/v1/search", json={"query": "stroke"}, headers=H(vic)).status_code == 200
    card = client.get("/v1/suggestions", headers=H(vic)).json()[0]
    assert client.post(f"/v1/suggestions/{card['id']}/decision", json={"decision": "same"}, headers=H(vic)).status_code == 403
    assert client.post(f"/v1/suggestions/{card['id']}/decision", json={"decision": "same"}, headers=H(dana)).status_code == 200
    last = eng.db.one("SELECT actor FROM audit_log WHERE action = 'suggestion.decided' ORDER BY id DESC LIMIT 1")
    assert last["actor"] == "dana@example.org"  # audit records the signed-in person
    assert client.post("/v1/packs/retail/install", headers=H(dana)).status_code == 403  # admin only

    client.post("/v1/auth/logout", headers=H(dana))
    assert client.get("/v1/stats", headers=H(dana)).status_code == 401
    stored = eng.db.one("SELECT pw_hash FROM users WHERE email = 'dana@example.org'")["pw_hash"]
    assert stored.startswith("scrypt$") and "battery" not in stored



def test_oidc_sign_in_with_pkce(eng, monkeypatch):
    from urllib.parse import parse_qs, urlparse

    import httpx

    from onoma.auth import Accounts
    from onoma.oidc import Oidc

    monkeypatch.setenv("ONOMA_OIDC_ISSUER", "https://idp.test")
    monkeypatch.setenv("ONOMA_OIDC_CLIENT_ID", "onoma")
    monkeypatch.setenv("ONOMA_OIDC_ALLOWED_DOMAINS", "example.org")
    seen, who = {}, {"email": "sam@example.org"}

    def idp(req):
        if req.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json={"authorization_endpoint": "https://idp.test/auth",
                                             "token_endpoint": "https://idp.test/token",
                                             "userinfo_endpoint": "https://idp.test/me"})
        if req.url.path == "/token":
            seen["form"] = parse_qs(req.content.decode())
            return httpx.Response(200, json={"access_token": "at"})
        return httpx.Response(200, json={"email": who["email"], "email_verified": True, "name": "Sam"})

    acc = Accounts(eng.db)
    root = acc.create("root@example.org", "Root", "a long admin pass", "admin")
    sso = Oidc(eng.db, acc, httpx.Client(transport=httpx.MockTransport(idp)))
    client = TestClient(create_app(eng, oidc=sso))
    assert client.get("/v1/health").json()["sso"] is True

    def begin():
        q = parse_qs(urlparse(client.get("/v1/auth/oidc/start").json()["url"]).query)
        assert q["code_challenge_method"] == ["S256"]
        return q["state"][0]

    state = begin()
    res = client.post("/v1/auth/oidc/callback", json={"code": "c1", "state": state}).json()
    assert res["user"]["role"] == "viewer" and seen["form"]["code_verifier"]
    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {res['token']}"}).json()
    assert me["email"] == "sam@example.org"
    assert client.post("/v1/auth/oidc/callback", json={"code": "c1", "state": state}).status_code == 401  # single use
    assert acc.login("sam@example.org", "external:oidc") is None  # SSO accounts have no password
    who["email"] = "eve@elsewhere.test"
    assert client.post("/v1/auth/oidc/callback", json={"code": "c2", "state": begin()}).status_code == 401
    with pytest.raises(ValueError):
        acc.set_role(root.id, "viewer", "root@example.org")  # last admin stays admin
