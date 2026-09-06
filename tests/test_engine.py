from app.engine import aggregate, evaluate_claim, extract_claims
from app import db
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient
from pathlib import Path
from tempfile import gettempdir

def test_claim_extraction():
    claims = extract_claims(
        "El ayuntamiento aprobó la medida el martes. "
        "La resolución fue publicada oficialmente el miércoles."
    )
    assert len(claims) == 2

def test_insufficient_without_evidence():
    r = evaluate_claim("El ayuntamiento aprobó la medida el martes.", [])
    assert r["verdict"] == "INSUFFICIENT_EVIDENCE"

def test_aggregate_insufficient():
    verdict, confidence = aggregate([{
        "verdict": "INSUFFICIENT_EVIDENCE",
        "support_score": 0.0,
        "contradiction_score": 0.0
    }])
    assert verdict == "INSUFFICIENT_EVIDENCE"
    assert confidence == 0.0


def test_db_path_falls_back_when_configured_path_is_not_writable(monkeypatch):
    monkeypatch.setattr(db.settings, "db_url", "sqlite:///./data/rie.db")
    monkeypatch.setattr(db.os, "access", lambda *args, **kwargs: False)

    resolved = db._path()

    assert resolved == Path(gettempdir()) / "rie.db"


def test_frontend_is_served():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "SWAT RIE Console" in response.text


def test_verify_contract_includes_rie_mvp_surfaces():
    client = TestClient(app)

    response = client.post(
        "/v1/reality/verify",
        headers={"X-API-Key": settings.api_key},
        json={
            "text": "El Banco Central prohibio todos los pagos con Bitcoin ayer.",
            "evidence_urls": [],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    investigation_id = payload["investigation_id"]
    assert payload["status"] == "COMPLETE"
    assert payload["review_status"] == "AI_ANALYSIS"
    assert payload["input_type"] == "TEXT"
    assert payload["content_hash"]
    assert payload["certificate_hash"]
    assert payload["certificate_hash"] != "pending"
    assert "dimensions" in payload
    assert "evidence_graph" in payload
    assert payload["audit_trail"]

    claims = client.get(
        f"/v1/reality/investigations/{investigation_id}/claims",
        headers={"X-API-Key": settings.api_key},
    )
    assert claims.status_code == 200
    assert claims.json()["claims"][0]["claim_id"] == "claim-001"

    certificate = client.get(
        f"/v1/reality/investigations/{investigation_id}/certificate",
        headers={"X-API-Key": settings.api_key},
    )
    assert certificate.status_code == 200
    assert certificate.json()["certificate"] == "SWAT Reality Certificate"

    review = client.post(
        f"/v1/reality/investigations/{investigation_id}/review",
        headers={"X-API-Key": settings.api_key},
        json={"action": "CERTIFY", "analyst": "SWAT QA", "notes": "Regression certification."},
    )
    assert review.status_code == 200
    assert review.json()["review_status"] == "CERTIFIED"

    search = client.post(
        "/v1/reality/media/search",
        headers={"X-API-Key": settings.api_key},
        json={"text": "El Banco Central prohibio todos los pagos con Bitcoin ayer."},
    )
    assert search.status_code == 200
    assert search.json()["previously_seen"] is True
    assert search.json()["matched_on"] == "content_hash"

    discovery = client.post(
        "/v1/reality/evidence/discover",
        headers={"X-API-Key": settings.api_key},
        json={"query": "Banco Central Bitcoin pagos", "limit": 3},
    )
    assert discovery.status_code == 200
    assert discovery.json()["status"] in {"READY", "MISSING_CONFIG", "FAILED"}

    providers = client.get(
        "/v1/reality/reverse-search/providers",
        headers={"X-API-Key": settings.api_key},
    )
    assert providers.status_code == 200
    names = {item["provider"] for item in providers.json()}
    assert "Google Lens" in names
    assert "Bing Visual Search" in names
    assert "TinEye" in names
