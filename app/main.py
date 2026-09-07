from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Cookie, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import io
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .auth import (
    approve_qr,
    consume_qr,
    create_qr_challenge,
    create_reset_token,
    create_session,
    create_user,
    delete_session,
    get_user_by_email,
    get_user_by_session,
    reset_password,
    verify_password,
)
from .db import (
    find_media_artifact_by_hash,
    get_investigation,
    get_media_artifact,
    init_db,
    list_investigations,
    save_investigation,
    save_media_artifact,
    update_investigation,
)
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
from .media import download_remote_media, ingest_media, transcribe_artifact
from .models import (
    EvidenceDiscoveryRequest,
    EvidenceDiscoveryResponse,
    EvidenceItem,
    MediaArtifactResponse,
    MediaSearchRequest,
    MediaUrlRequest,
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


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RecoveryRequest(BaseModel):
    email: str


class ResetRequest(BaseModel):
    token: str
    password: str


class QrApproveRequest(BaseModel):
    challenge_id: str
    secret: str


@app.post("/auth/register")
def register(req: RegisterRequest, response: Response):
    if "@" not in req.email:
        raise HTTPException(status_code=422, detail="valid email required")
    if len(req.password) < 8:
        raise HTTPException(status_code=422, detail="password must contain at least 8 characters")
    if get_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="email already registered")
    user_id = str(uuid4())
    create_user(user_id, req.email, req.password)
    response.set_cookie("rie_session", create_session(user_id), httponly=True, samesite="lax", secure=False, max_age=604800)
    return {"email": req.email.lower()}


@app.post("/auth/login")
def login(req: LoginRequest, response: Response):
    user = get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid credentials")
    response.set_cookie("rie_session", create_session(user["id"]), httponly=True, samesite="lax", secure=False, max_age=604800)
    return {"email": user["email"]}


@app.post("/auth/logout")
def logout(response: Response, session_id: str | None = Cookie(default=None, alias="rie_session")):
    delete_session(session_id)
    response.delete_cookie("rie_session")
    return {"ok": True}


@app.get("/auth/me")
def me(session_id: str | None = Cookie(default=None, alias="rie_session")):
    user = get_user_by_session(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    return {"email": user["email"]}


@app.get("/auth/status")
def auth_status(session_id: str | None = Cookie(default=None, alias="rie_session")):
    user = get_user_by_session(session_id)
    return {"authenticated": bool(user), "email": user["email"] if user else None}


@app.post("/auth/recover")
def recover(req: RecoveryRequest):
    # In production this token is emailed; returning it keeps the local MVP testable.
    token = create_reset_token(req.email)
    return {"ok": True, "reset_token": token}


@app.post("/auth/reset")
def reset(req: ResetRequest):
    if len(req.password) < 8 or not reset_password(req.token, req.password):
        raise HTTPException(status_code=422, detail="invalid or expired recovery token")
    return {"ok": True}


@app.post("/auth/qr/start")
def qr_start(request: Request, session_id: str | None = Cookie(default=None, alias="rie_session")):
    user = get_user_by_session(session_id)
    challenge_id, secret = create_qr_challenge(user["id"] if user else None)
    public_url = str(request.base_url).rstrip("/")
    return {"challenge_id": challenge_id, "secret": secret, "approve_url": f"{public_url}/login?qr={challenge_id}.{secret}"}


@app.get("/auth/qr/image")
def qr_image(url: str):
    import qrcode
    image = qrcode.make(url)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    return StreamingResponse(stream, media_type="image/png")


@app.post("/auth/qr/approve")
def qr_approve(req: QrApproveRequest, session_id: str | None = Cookie(default=None, alias="rie_session")):
    user = get_user_by_session(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="login on this phone before approving")
    if not approve_qr(req.challenge_id, req.secret, user["id"]):
        raise HTTPException(status_code=422, detail="QR expired or already used")
    return {"ok": True}


@app.get("/auth/qr/status")
def qr_status(challenge_id: str, secret: str, response: Response):
    user = consume_qr(challenge_id, secret)
    if not user:
        return {"approved": False}
    response.set_cookie("rie_session", create_session(user["id"]), httponly=True, samesite="lax", secure=False, max_age=604800)
    return {"approved": True, "email": user["email"]}

@app.on_event("startup")
def startup() -> None:
    init_db()

@app.get("/v1/health")
def health():
    return {"status": "ok", "engine": "SWAT RIE", "version": settings.app_version}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse("app/static/login.html")

@app.post("/v1/reality/verify", response_model=VerifyResponse, dependencies=[Depends(require_api_key)])
async def verify(req: VerifyRequest, user: dict = Depends(require_api_key)):
    if bool(req.text) == bool(req.url):
        raise HTTPException(status_code=422, detail="provide exactly one of text or url")

    source_text = req.text or ""
    source_url = str(req.url) if req.url else None
    input_type = detect_input_type(req.text, source_url)
    evidence_items: list[EvidenceItem] = []
    evidence_texts: list[str] = []

    source_fetch_error = None
    if source_url:
        if input_type in {"IMAGE", "VIDEO", "AUDIO", "DOCUMENT"}:
            source_text = f"Remote {input_type.lower()} content submitted for investigation: {source_url}"
            source_fetch_error = f"{input_type.lower()} remote downloader is not configured; upload the file through /v1/reality/media/ingest for artifact analysis"
        else:
            try:
                page = await fetch_page(source_url)
                source_text = page.text
            except Exception as e:
                raise HTTPException(status_code=422, detail=f"source fetch failed: {e}")

    evidence_urls = [str(url) for url in req.evidence_urls]
    discovery = None
    if req.autonomous_search:
        query = req.evidence_query or " ".join(extract_claims(source_text, limit=2)) or source_url or source_text[:300]
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
        "Local image, video, audio and document uploads are ingested as artifacts; OCR, transcription, keyframes and detector ensembles require worker tools.",
        "Autonomous search requires configured provider credentials; otherwise the analyst supplies evidence URLs.",
        "Semantic matching is lexical and heuristic; it is intentionally conservative.",
        "A low-confidence result must be treated as unresolved.",
    ]
    if discovery is not None and discovery.status != "READY":
        limitations.insert(3, discovery.message or "Autonomous evidence discovery did not return usable sources.")
    if source_fetch_error:
        limitations.insert(1, source_fetch_error)

    iid = str(uuid4())
    graph = build_evidence_graph(iid, results, evidence_items)
    audit_trail = build_audit_trail(input_type, len(results), len(evidence_items))
    if discovery is not None:
        audit_trail.append({
            "at": datetime.now(timezone.utc).isoformat(),
            "stage": "AUTONOMOUS_EVIDENCE_DISCOVERY",
            "detail": f"{discovery.provider}:{discovery.status}:results={len(discovery.results)}",
        })
    if source_fetch_error:
        audit_trail.append({
            "at": datetime.now(timezone.utc).isoformat(),
            "stage": "REMOTE_MEDIA_RESOLVER",
            "detail": source_fetch_error,
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
        owner_id=user["id"],
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
    inputs = [bool(req.text), bool(req.url), bool(req.sha256)]
    if sum(inputs) != 1:
        raise HTTPException(status_code=422, detail="provide exactly one of text, url or sha256")

    target_hash = sha256_text(req.text) if req.text else None
    target_url = str(req.url) if req.url else None
    if req.sha256:
        artifact = find_media_artifact_by_hash(req.sha256.lower())
        if artifact:
            return MediaSearchResponse(
                previously_seen=True,
                similarity=1.0,
                artifact_id=artifact["artifact_id"],
                matched_on="artifact_hash",
            )
        return MediaSearchResponse(previously_seen=False, similarity=0.0, matched_on="none")
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

@app.post("/v1/reality/media/ingest", response_model=MediaArtifactResponse, dependencies=[Depends(require_api_key)])
async def media_ingest(file: UploadFile = File(...)):
    data = await file.read()
    try:
        artifact = ingest_media(file.filename or "upload.bin", file.content_type, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    save_media_artifact(artifact)
    return artifact


@app.post("/v1/reality/media/ingest-url", response_model=MediaArtifactResponse, dependencies=[Depends(require_api_key)])
def media_ingest_url(req: MediaUrlRequest):
    try:
        filename, extension, data = download_remote_media(str(req.url))
        artifact = ingest_media(filename, f"video/{extension}" if extension else "video/mp4", data)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    save_media_artifact(artifact)
    return artifact

@app.get("/v1/reality/media/artifacts/{artifact_id}", response_model=MediaArtifactResponse, dependencies=[Depends(require_api_key)])
def media_artifact(artifact_id: str):
    artifact = get_media_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return artifact

@app.post("/v1/reality/media/artifacts/{artifact_id}/transcribe", response_model=MediaArtifactResponse, dependencies=[Depends(require_api_key)])
def media_artifact_transcribe(artifact_id: str):
    artifact = get_media_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    if artifact.get("input_type") not in {"AUDIO", "VIDEO"}:
        raise HTTPException(status_code=422, detail="artifact does not contain audio")
    artifact = transcribe_artifact(artifact)
    save_media_artifact(artifact)
    return artifact

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
