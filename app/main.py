from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import get_investigation, init_db, list_investigations, save_investigation, update_investigation
from .discovery import discover_evidence, reverse_search_statuses
from .engine import aggregate, evaluate_claim, extract_claims
from .fetcher import fetch_page
from .intelligence import (
    assign_evidence_scores,
    build_audit_trail,
    build_dimensions,
    build_evidence_graph,
    certificate_hash,
    certificate_payload,
    detect_input_type,
    enrich_claim,
    enrich_evidence,
    review_record,
    sha256_text,
)
from .models import (
    EvidenceDiscoveryRequest,
    EvidenceDiscoveryResponse,
    EvidenceItem,
    MediaSearchRequest,
    MediaSearchResponse,
    ReviewRequest,
    ReverseSearchProviderStatus,
    VerifyRequest,
    VerifyResponse,
)
from .security import require_api_key

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url=None,
)

@app.on_event("startup")
def startup() -> None:
    init_db()

@app.get("/v1/health")
def health():
    return {"status": "ok", "engine": "SWAT RIE", "version": settings.app_version}

@app.post("/v1/reality/verify", response_model=VerifyResponse, dependencies=[Depends(require_api_key)])
async def verify(req: VerifyRequest):
    if bool(req.text) == bool(req.url):
        raise HTTPException(status_code=422, detail="provide exactly one of text or url")

    source_text = req.text or ""
    source_url = str(req.url) if req.url else None
    input_type = detect_input_type(req.text, source_url)
    evidence_items: list[EvidenceItem] = []
    evidence_texts: list[str] = []

    if source_url:
        if input_type in {"IMAGE", "VIDEO", "AUDIO", "DOCUMENT"}:
            raise HTTPException(
                status_code=422,
                detail=f"{input_type.lower()} ingestion is declared in the v0.1 contract but requires the media pipeline",
            )
        try:
            page = await fetch_page(source_url)
            source_text = page.text
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"source fetch failed: {e}")

    evidence_urls = [str(url) for url in req.evidence_urls]
    discovery = None
    if req.autonomous_search:
        query = req.evidence_query or " ".join(extract_claims(source_text, limit=2)) or source_text[:300]
        discovery = await discover_evidence(query, limit=settings.max_discovered_evidence)
        evidence_urls.extend(result.url for result in discovery.results)
        evidence_urls = list(dict.fromkeys(evidence_urls))[:12]

    for index, ev_url in enumerate(evidence_urls):
        try:
            page = await fetch_page(ev_url)
            evidence_texts.append(page.text)
            evidence_items.append(enrich_evidence(
                url=page.url,
                title=page.title,
                text=page.text,
                status="FETCHED",
                index=index,
            ))
        except Exception as e:
            evidence_items.append(enrich_evidence(
                url=ev_url,
                status="FAILED",
                index=index,
                error=str(e)[:300],
            ))

    claims = extract_claims(source_text)
    results = [enrich_claim(c, evaluate_claim(c, evidence_texts), index) for index, c in enumerate(claims)]
    verdict, confidence = aggregate(results)
    evidence_items = assign_evidence_scores(evidence_items, results)
    content_hash = sha256_text(source_text)
    source = {
        "type": input_type,
        "url": source_url,
        "mode": req.mode,
        "extracted_chars": len(source_text),
    }
    dimensions = build_dimensions(source_text, input_type, results, evidence_items, confidence)

    explanation = [
        f"{len(claims)} claim(s) extracted.",
        f"{sum(1 for e in evidence_items if e.status == 'FETCHED')} evidence source(s) fetched.",
        "Dimensions are computed from fetched evidence, claim scores, source type and provenance coverage.",
        "Verdict is evidence-relative; it is not a certification of absolute truth.",
    ]
    if discovery is not None:
        explanation.insert(2, f"Autonomous evidence discovery: {discovery.status} via {discovery.provider}.")
    limitations = [
        "v0.1 accepts text and public web URLs as executable analysis paths.",
        "Image, video, audio and document ingestion are contract surfaces but not processed until the media pipeline is added.",
        "Autonomous search requires configured provider credentials; otherwise the analyst supplies evidence URLs.",
        "Semantic matching is lexical and heuristic; it is intentionally conservative.",
        "A low-confidence result must be treated as unresolved.",
    ]
    if discovery is not None and discovery.status != "READY":
        limitations.insert(3, discovery.message or "Autonomous evidence discovery did not return usable sources.")

    iid = str(uuid4())
    graph = build_evidence_graph(iid, results, evidence_items)
    audit_trail = build_audit_trail(input_type, len(results), len(evidence_items))
    if discovery is not None:
        audit_trail.append({
            "at": datetime.now(timezone.utc).isoformat(),
            "stage": "AUTONOMOUS_EVIDENCE_DISCOVERY",
            "detail": f"{discovery.provider}:{discovery.status}:results={len(discovery.results)}",
        })
    response = VerifyResponse(
        investigation_id=iid,
        engine="SWAT Reality Intelligence Engine",
        version=settings.app_version,
        input_type=input_type,
        source=source,
        content_hash=content_hash,
        verdict=verdict,
        confidence=confidence,
        dimensions=dimensions,
        claims=results,
        evidence=evidence_items,
        evidence_graph=graph,
        explanation=explanation,
        limitations=limitations,
        audit_trail=audit_trail,
        certificate_hash="pending",
    )
    payload = response.model_dump()
    payload["certificate_hash"] = certificate_hash(payload)
    response.certificate_hash = payload["certificate_hash"]
    save_investigation(
        iid,
        datetime.now(timezone.utc).isoformat(),
        verdict,
        confidence,
        req.model_dump(mode="json"),
        payload,
    )
    return response

@app.get("/v1/reality/investigations/{investigation_id}", dependencies=[Depends(require_api_key)])
def investigation(investigation_id: str):
    row = get_investigation(investigation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    return JSONResponse(row)

@app.post("/v1/reality/media/search", response_model=MediaSearchResponse, dependencies=[Depends(require_api_key)])
def media_search(req: MediaSearchRequest):
    if bool(req.text) == bool(req.url):
        raise HTTPException(status_code=422, detail="provide exactly one of text or url")

    target_hash = sha256_text(req.text) if req.text else None
    target_url = str(req.url) if req.url else None
    for row in list_investigations():
        if target_hash and row.get("content_hash") == target_hash:
            return MediaSearchResponse(
                previously_seen=True,
                similarity=1.0,
                investigation_id=row["investigation_id"],
                matched_on="content_hash",
            )
        if target_url and row.get("source", {}).get("url") == target_url:
            return MediaSearchResponse(
                previously_seen=True,
                similarity=1.0,
                investigation_id=row["investigation_id"],
                matched_on="source_url",
            )
    return MediaSearchResponse(previously_seen=False, similarity=0.0, matched_on="none")

@app.get("/v1/reality/investigations/{investigation_id}/claims", dependencies=[Depends(require_api_key)])
def investigation_claims(investigation_id: str):
    row = get_investigation(investigation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    return {"investigation_id": investigation_id, "claims": row.get("claims", [])}

@app.get("/v1/reality/investigations/{investigation_id}/evidence", dependencies=[Depends(require_api_key)])
def investigation_evidence(investigation_id: str):
    row = get_investigation(investigation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    return {"investigation_id": investigation_id, "evidence": row.get("evidence", [])}

@app.get("/v1/reality/investigations/{investigation_id}/certificate", dependencies=[Depends(require_api_key)])
def investigation_certificate(investigation_id: str):
    row = get_investigation(investigation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    return certificate_payload(row)

@app.post("/v1/reality/investigations/{investigation_id}/review", dependencies=[Depends(require_api_key)])
def investigation_review(investigation_id: str, req: ReviewRequest):
    row = get_investigation(investigation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    record = review_record(req)
    if req.action == "OVERRIDE" and req.verdict is None:
        raise HTTPException(status_code=422, detail="verdict is required when action=OVERRIDE")
    if req.verdict is not None:
        row["verdict"] = req.verdict
    row["review_status"] = record.status
    row.setdefault("reviews", []).append(record.model_dump())
    row.setdefault("audit_trail", []).append({
        "at": record.reviewed_at,
        "stage": "HUMAN_REVIEW",
        "detail": f"{req.action} by {req.analyst}",
    })
    row["certificate_hash"] = certificate_hash(row)
    update_investigation(investigation_id, row)
    return row

@app.post("/v1/reality/evidence/discover", response_model=EvidenceDiscoveryResponse, dependencies=[Depends(require_api_key)])
async def evidence_discover(req: EvidenceDiscoveryRequest):
    return await discover_evidence(req.query, limit=req.limit)

@app.get("/v1/reality/reverse-search/providers", response_model=list[ReverseSearchProviderStatus], dependencies=[Depends(require_api_key)])
def reverse_search_providers():
    return reverse_search_statuses()

app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
