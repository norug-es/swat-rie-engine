from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .config import settings
from .db import get_investigation, init_db, save_investigation
from .engine import aggregate, evaluate_claim, extract_claims
from .fetcher import fetch_page
from .models import EvidenceItem, VerifyRequest, VerifyResponse
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
    evidence_items: list[EvidenceItem] = []
    evidence_texts: list[str] = []

    if source_url:
        try:
            page = await fetch_page(source_url)
            source_text = page.text
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"source fetch failed: {e}")

    for ev_url_obj in req.evidence_urls:
        ev_url = str(ev_url_obj)
        try:
            page = await fetch_page(ev_url)
            evidence_texts.append(page.text)
            evidence_items.append(EvidenceItem(
                url=page.url, title=page.title,
                extracted_chars=len(page.text), status="FETCHED"
            ))
        except Exception as e:
            evidence_items.append(EvidenceItem(
                url=ev_url, extracted_chars=0, status="FAILED", error=str(e)[:300]
            ))

    claims = extract_claims(source_text)
    results = [evaluate_claim(c, evidence_texts) for c in claims]
    verdict, confidence = aggregate(results)

    explanation = [
        f"{len(claims)} claim(s) extracted.",
        f"{sum(1 for e in evidence_items if e.status == 'FETCHED')} evidence source(s) fetched.",
        "Verdict is evidence-relative; it is not a certification of absolute truth.",
    ]
    limitations = [
        "v0.1 does not autonomously search the web.",
        "v0.1 does not analyze video/audio/deepfakes.",
        "Semantic matching is lexical/heuristic; it is intentionally conservative.",
        "A low-confidence result must be treated as unresolved.",
    ]

    iid = str(uuid4())
    response = VerifyResponse(
        investigation_id=iid,
        engine="SWAT Reality Intelligence Engine",
        version=settings.app_version,
        verdict=verdict,
        confidence=confidence,
        claims=results,
        evidence=evidence_items,
        explanation=explanation,
        limitations=limitations,
    )
    payload = response.model_dump()
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
