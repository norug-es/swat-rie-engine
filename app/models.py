from typing import Any, Literal
from pydantic import BaseModel, Field, HttpUrl

Verdict = Literal[
    "SUPPORTED",
    "CONTRADICTED",
    "MIXED",
    "MISLEADING",
    "FALSE_CONTEXT",
    "MANIPULATED_MEDIA",
    "AI_GENERATED",
    "SATIRE",
    "OUTDATED",
    "UNVERIFIED",
    "INSUFFICIENT_EVIDENCE",
    "INCONCLUSIVE",
]
ReviewStatus = Literal["AI_ANALYSIS", "PENDING_REVIEW", "HUMAN_REVIEWED", "CERTIFIED", "DISPUTED", "REOPENED"]
ReviewAction = Literal["CONFIRM", "OVERRIDE", "REQUEST_MORE_EVIDENCE", "REOPEN", "CERTIFY", "DISPUTE"]

class VerifyRequest(BaseModel):
    text: str | None = Field(default=None, min_length=3, max_length=50000)
    url: HttpUrl | None = None
    evidence_urls: list[HttpUrl] = Field(default_factory=list, max_length=12)
    mode: Literal["quick", "full"] = "full"
    autonomous_search: bool = False
    evidence_query: str | None = Field(default=None, max_length=500)

class MediaSearchRequest(BaseModel):
    text: str | None = Field(default=None, min_length=3, max_length=50000)
    url: HttpUrl | None = None
    sha256: str | None = Field(default=None, min_length=64, max_length=64)


class MediaUrlRequest(BaseModel):
    url: HttpUrl

class EvidenceDiscoveryRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    limit: int = Field(default=5, ge=1, le=12)

class EvidenceDiscoveryResult(BaseModel):
    title: str | None = None
    url: str
    snippet: str | None = None
    provider: str
    source_type: str
    source_reliability: float

class EvidenceDiscoveryResponse(BaseModel):
    status: Literal["READY", "MISSING_CONFIG", "FAILED"]
    provider: str
    query: str
    results: list[EvidenceDiscoveryResult]
    message: str | None = None

class ReverseSearchProviderStatus(BaseModel):
    provider: str
    status: Literal["CONFIGURED", "MISSING_CONFIG", "MANUAL_ONLY"]
    capability: str

class MediaPipelineStage(BaseModel):
    stage: str
    status: Literal["COMPLETE", "MISSING_CONFIG", "MISSING_TOOL", "SKIPPED", "FAILED"]
    detail: str | None = None

class MediaArtifactResponse(BaseModel):
    artifact_id: str
    filename: str
    input_type: Literal["IMAGE", "VIDEO", "AUDIO", "DOCUMENT", "UNKNOWN"]
    mime_type: str
    size_bytes: int
    sha256: str
    storage_path: str
    metadata: dict[str, Any]
    pipeline: list[MediaPipelineStage]
    created_at: str

class EvidenceItem(BaseModel):
    evidence_id: str
    type: Literal["WEB_SOURCE", "SOURCE_FETCH_ERROR"] = "WEB_SOURCE"
    url: str
    source: str | None = None
    source_type: str = "unknown"
    source_reliability: float = 0.3
    title: str | None = None
    extracted_chars: int = 0
    status: Literal["FETCHED", "FAILED"]
    acquired_at: str | None = None
    content_hash: str | None = None
    supports: float = 0.0
    contradicts: float = 0.0
    error: str | None = None

class ClaimResult(BaseModel):
    claim_id: str
    claim: str
    support_score: float
    contradiction_score: float
    matched_evidence: int
    verdict: Verdict
    entities: list[str] = Field(default_factory=list)

class RealityDimensions(BaseModel):
    media_authenticity: float
    claim_factuality: float
    source_reliability: float
    temporal_consistency: float
    geolocation_consistency: float
    provenance_confidence: float
    deepfake_probability: float

class EvidenceGraph(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]

class AuditEntry(BaseModel):
    at: str
    stage: str
    detail: str

class ReviewRequest(BaseModel):
    action: ReviewAction
    analyst: str = Field(min_length=2, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    verdict: Verdict | None = None

class ReviewRecord(BaseModel):
    status: ReviewStatus
    action: ReviewAction
    analyst: str
    notes: str | None = None
    verdict: Verdict | None = None
    reviewed_at: str

class MediaSearchResponse(BaseModel):
    previously_seen: bool
    similarity: float
    investigation_id: str | None = None
    artifact_id: str | None = None
    matched_on: Literal["content_hash", "source_url", "artifact_hash", "none"]

class VerifyResponse(BaseModel):
    investigation_id: str
    status: Literal["COMPLETE"] = "COMPLETE"
    review_status: ReviewStatus = "AI_ANALYSIS"
    engine: str
    version: str
    input_type: Literal["TEXT", "URL", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT", "UNKNOWN"]
    source: dict[str, Any]
    content_hash: str
    verdict: Verdict
    confidence: float
    dimensions: RealityDimensions
    claims: list[ClaimResult]
    evidence: list[EvidenceItem]
    evidence_graph: EvidenceGraph
    explanation: list[str]
    limitations: list[str]
    audit_trail: list[AuditEntry]
    reviews: list[ReviewRecord] = Field(default_factory=list)
    certificate_hash: str
