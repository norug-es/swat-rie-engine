from app.engine import aggregate, evaluate_claim, extract_claims
from app import db
from app.config import settings
from app.media import sha256_bytes
from app.intelligence import assess_context
from app.models import EvidenceItem
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


def test_context_assessment_flags_geographic_and_temporal_mismatch():
    evidence = [EvidenceItem(
        evidence_id="ev-001",
        url="https://www.dailymail.co.uk/news/example",
        source_type="news",
        source_reliability=0.72,
        status="FETCHED",
    )]
    assessment = assess_context(
        "El vídeo ocurrió en Ceuta durante 2025.",
        evidence,
        ["The incident happened in Wakefield in 2024, according to the report."],
    )
    assert assessment.status == "POTENTIAL_FALSE_CONTEXT"
    assert assessment.confidence >= 0.7


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


def test_media_ingest_persists_audio_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "artifact_dir", str(tmp_path / "artifacts"))
    client = TestClient(app)
    media = b"ID3" + b"\x00" * 128

    response = client.post(
        "/v1/reality/media/ingest",
        headers={"X-API-Key": settings.api_key},
        files={"file": ("sample.mp3", media, "audio/mpeg")},
    )

    assert response.status_code == 200
    artifact = response.json()
    assert artifact["input_type"] == "AUDIO"
    assert artifact["sha256"] == sha256_bytes(media)
    assert artifact["pipeline"][0]["stage"] == "SIGNATURE_VALIDATION"
    stages = {item["stage"]: item["status"] for item in artifact["pipeline"]}
    assert "AUDIO_NORMALIZATION" in stages
    assert stages["TRANSCRIPTION"] in {"COMPLETE", "MISSING_CONFIG", "MISSING_TOOL", "FAILED", "SKIPPED"}

    loaded = client.get(
        f"/v1/reality/media/artifacts/{artifact['artifact_id']}",
        headers={"X-API-Key": settings.api_key},
    )
    assert loaded.status_code == 200
    assert loaded.json()["sha256"] == artifact["sha256"]

    transcribed = client.post(
        f"/v1/reality/media/artifacts/{artifact['artifact_id']}/transcribe",
        headers={"X-API-Key": settings.api_key},
    )
    assert transcribed.status_code == 200
    transcribed_stages = {item["stage"]: item["status"] for item in transcribed.json()["pipeline"]}
    assert "TRANSCRIPTION" in transcribed_stages

    search = client.post(
        "/v1/reality/media/search",
        headers={"X-API-Key": settings.api_key},
        json={"sha256": artifact["sha256"]},
    )
    assert search.status_code == 200
    assert search.json()["previously_seen"] is True
    assert search.json()["matched_on"] == "artifact_hash"


def test_remote_video_url_is_recorded_as_unverified_investigation():
    client = TestClient(app)

    response = client.post(
        "/v1/reality/verify",
        headers={"X-API-Key": settings.api_key},
        json={"url": "https://vm.tiktok.com/ZN8YxjmDs/"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["input_type"] == "VIDEO"
    assert payload["verdict"] == "INSUFFICIENT_EVIDENCE"
    if payload["source"].get("artifact_id"):
        assert payload["source"]["extracted_chars"] > 0
        assert any("downloaded and analyzed as artifact" in item for item in payload["explanation"])
    else:
        assert any("download failed" in item or "no readable transcription" in item for item in payload["limitations"])
    assert any("Local image, video, audio and document uploads are ingested" in item for item in payload["limitations"])
