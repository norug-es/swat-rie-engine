import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from .models import AuditEntry, EvidenceGraph, EvidenceItem, RealityDimensions, ReviewRequest, ReviewRecord

ENTITY_RE = re.compile(r"\b[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÜÑáéíóúüñ-]{2,}\b")
TEMPORAL_TERMS = {
    "hoy", "ayer", "mañana", "today", "yesterday", "tomorrow", "ahora", "now",
    "actualmente", "current", "currently", "reciente", "recent",
}
GEO_TERMS = {
    "madrid", "valencia", "barcelona", "ankara", "turquia", "turkey", "españa",
    "spain", "francia", "france", "europa", "europe",
}
PRIMARY_HINTS = (".gov", ".gob", ".edu", ".europa.eu", "boe.es", "who.int", "un.org")
NEWS_HINTS = ("reuters.com", "apnews.com", "efe.com", "bbc.", "elpais.com", "elmundo.es")
SOCIAL_HINTS = ("x.com", "twitter.com", "tiktok.com", "youtube.com", "facebook.com", "instagram.com")
VIDEO_HOSTS = ("tiktok.com", "youtube.com", "youtu.be", "vimeo.com")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov")
AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".ogg")
DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".html")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def detect_input_type(text: str | None, url: str | None) -> str:
    if text:
        return "TEXT"
    if not url:
        return "UNKNOWN"
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    if host.endswith(VIDEO_HOSTS) or path.endswith(VIDEO_EXTENSIONS):
        return "VIDEO"
    if path.endswith(IMAGE_EXTENSIONS):
        return "IMAGE"
    if path.endswith(AUDIO_EXTENSIONS):
        return "AUDIO"
    if path.endswith(DOCUMENT_EXTENSIONS):
        return "DOCUMENT"
    return "URL"


def source_profile(url: str) -> tuple[str, float]:
    host = (urlparse(url).hostname or "").lower()
    if any(hint in host for hint in PRIMARY_HINTS):
        return "primary", 0.9
    if any(hint in host for hint in NEWS_HINTS):
        return "news", 0.72
    if any(hint in host for hint in SOCIAL_HINTS):
        return "social", 0.42
    if host:
        return "web", 0.55
    return "unknown", 0.3


def extract_entities(text: str) -> list[str]:
    seen = []
    for match in ENTITY_RE.findall(text):
        if match not in seen:
            seen.append(match)
    return seen[:12]


def enrich_claim(claim: str, result: dict, index: int) -> dict:
    return {
        "claim_id": f"claim-{index + 1:03d}",
        "claim": claim,
        "support_score": result["support_score"],
        "contradiction_score": result["contradiction_score"],
        "matched_evidence": result["matched_evidence"],
        "verdict": result["verdict"],
        "entities": extract_entities(claim),
    }


def enrich_evidence(url: str, status: str, index: int, text: str = "", title: str | None = None, error: str | None = None) -> EvidenceItem:
    source_type, reliability = source_profile(url)
    content_hash = sha256_text(text) if text else None
    return EvidenceItem(
        evidence_id=f"ev-{index + 1:03d}",
        type="WEB_SOURCE" if status == "FETCHED" else "SOURCE_FETCH_ERROR",
        url=url,
        source=urlparse(url).hostname,
        source_type=source_type,
        source_reliability=reliability,
        title=title,
        extracted_chars=len(text),
        status=status,
        acquired_at=now_iso(),
        content_hash=content_hash,
        error=error,
    )


def assign_evidence_scores(evidence: list[EvidenceItem], claims: list[dict]) -> list[EvidenceItem]:
    best_support = max((claim["support_score"] for claim in claims), default=0.0)
    best_contra = max((claim["contradiction_score"] for claim in claims), default=0.0)
    for item in evidence:
        if item.status == "FETCHED":
            item.supports = round(best_support * item.source_reliability, 3)
            item.contradicts = round(best_contra * item.source_reliability, 3)
    return evidence


def build_dimensions(
    source_text: str,
    input_type: str,
    claims: list[dict],
    evidence: list[EvidenceItem],
    confidence: float,
) -> RealityDimensions:
    fetched = [item for item in evidence if item.status == "FETCHED"]
    source_reliability = round(sum(item.source_reliability for item in fetched) / len(fetched), 3) if fetched else 0.0
    decisive = [claim for claim in claims if claim["verdict"] in {"SUPPORTED", "CONTRADICTED"}]
    claim_factuality = round(sum(claim["support_score"] for claim in claims) / len(claims), 3) if claims else 0.0
    has_temporal = bool(set(source_text.lower().split()) & TEMPORAL_TERMS)
    has_geo = any(term in source_text.lower() for term in GEO_TERMS)
    media_authenticity = 0.5 if input_type in {"IMAGE", "VIDEO", "AUDIO"} else 1.0
    deepfake_probability = 0.5 if input_type in {"VIDEO", "AUDIO"} else 0.0

    return RealityDimensions(
        media_authenticity=round(media_authenticity, 3),
        claim_factuality=claim_factuality,
        source_reliability=source_reliability,
        temporal_consistency=round(confidence if has_temporal and decisive else 0.0, 3),
        geolocation_consistency=round(confidence if has_geo and decisive else 0.0, 3),
        provenance_confidence=round(min(0.95, (len(fetched) / 4) * source_reliability), 3) if fetched else 0.0,
        deepfake_probability=deepfake_probability,
    )


def build_evidence_graph(investigation_id: str, claims: list[dict], evidence: list[EvidenceItem]) -> EvidenceGraph:
    nodes = [{"id": investigation_id, "type": "INVESTIGATION", "label": investigation_id}]
    edges = []
    for claim in claims:
        nodes.append({"id": claim["claim_id"], "type": "CLAIM", "label": claim["claim"][:120]})
        edges.append({"from": investigation_id, "to": claim["claim_id"], "type": "HAS_CLAIM"})
    for item in evidence:
        nodes.append({
            "id": item.evidence_id,
            "type": item.type,
            "label": item.source or item.url,
            "status": item.status,
            "source_reliability": item.source_reliability,
        })
        for claim in claims:
            edge_type = "SUPPORTS" if claim["support_score"] >= claim["contradiction_score"] else "CONTRADICTS"
            edges.append({"from": item.evidence_id, "to": claim["claim_id"], "type": edge_type})
    return EvidenceGraph(nodes=nodes, edges=edges)


def build_audit_trail(input_type: str, claims_count: int, evidence_count: int) -> list[AuditEntry]:
    acquired_at = now_iso()
    return [
        AuditEntry(at=acquired_at, stage="CONTENT_RESOLVER", detail=f"input_type={input_type}"),
        AuditEntry(at=acquired_at, stage="CLAIM_EXTRACTION", detail=f"claims={claims_count}"),
        AuditEntry(at=acquired_at, stage="EVIDENCE_COLLECTION", detail=f"sources={evidence_count}"),
        AuditEntry(at=acquired_at, stage="REALITY_SCORING", detail="heuristic lexical scoring v0.1"),
    ]


def certificate_hash(payload: dict) -> str:
    base = "|".join([
        payload["investigation_id"],
        payload["content_hash"],
        payload["verdict"],
        str(payload["confidence"]),
        payload["version"],
    ])
    return sha256_text(base)


def certificate_payload(investigation: dict) -> dict:
    return {
        "certificate": "SWAT Reality Certificate",
        "investigation_id": investigation["investigation_id"],
        "content_hash": investigation["content_hash"],
        "evidence_hashes": [item.get("content_hash") for item in investigation.get("evidence", []) if item.get("content_hash")],
        "verdict": investigation["verdict"],
        "confidence": investigation["confidence"],
        "engine": investigation["engine"],
        "version": investigation["version"],
        "review_status": investigation["review_status"],
        "certificate_hash": investigation["certificate_hash"],
    }


def review_record(req: ReviewRequest) -> ReviewRecord:
    status_by_action = {
        "CONFIRM": "HUMAN_REVIEWED",
        "OVERRIDE": "HUMAN_REVIEWED",
        "REQUEST_MORE_EVIDENCE": "PENDING_REVIEW",
        "REOPEN": "REOPENED",
        "CERTIFY": "CERTIFIED",
        "DISPUTE": "DISPUTED",
    }
    return ReviewRecord(
        status=status_by_action[req.action],
        action=req.action,
        analyst=req.analyst,
        notes=req.notes,
        verdict=req.verdict,
        reviewed_at=now_iso(),
    )
