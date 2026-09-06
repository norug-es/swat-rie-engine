from typing import Literal
from pydantic import BaseModel, Field, HttpUrl

Verdict = Literal["SUPPORTED", "CONTRADICTED", "MIXED", "INSUFFICIENT_EVIDENCE"]

class VerifyRequest(BaseModel):
    text: str | None = Field(default=None, min_length=3, max_length=50000)
    url: HttpUrl | None = None
    evidence_urls: list[HttpUrl] = Field(default_factory=list, max_length=12)

class EvidenceItem(BaseModel):
    url: str
    title: str | None = None
    extracted_chars: int = 0
    status: Literal["FETCHED", "FAILED"]
    error: str | None = None

class ClaimResult(BaseModel):
    claim: str
    support_score: float
    contradiction_score: float
    matched_evidence: int
    verdict: Verdict

class VerifyResponse(BaseModel):
    investigation_id: str
    engine: str
    version: str
    verdict: Verdict
    confidence: float
    claims: list[ClaimResult]
    evidence: list[EvidenceItem]
    explanation: list[str]
    limitations: list[str]
