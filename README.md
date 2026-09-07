# SWAT Reality Intelligence Engine — MVP v0.1.0

RIE is an evidence-relative verification microservice for SWAT.

It does **not** claim to certify absolute truth. It extracts claims from text/web pages,
compares them against supplied evidence pages, produces an explainable verdict and
persists the complete investigation.

## v0.1 scope

- `POST /v1/reality/verify`
- input: exactly one of `text` or `url`
- optional `evidence_urls`
- claim extraction
- evidence fetching + readable-text extraction
- conservative claim scoring
- content type detection for text/web URLs and declared media surfaces
- SHA-256 content and evidence fingerprints
- source classification and reliability weighting
- multidimensional Reality Scoring
- Evidence Graph generation
- reproducible audit trail
- certificate hash + certificate endpoint
- human review workflow
- autonomous evidence discovery through a configured search provider
- reverse/media search provider registry for Google Lens, Bing Visual Search, Yandex Images, TinEye, InVID, perceptual hashes, and local semantic search
- multimedia artifact ingestion for image, audio, video and document uploads
- media signature validation, SHA-256 artifact fingerprints, storage, ffprobe metadata, audio normalization, and video keyframe extraction when FFmpeg is available
- aggregate verdict
- SQLite persistence
- `GET /v1/reality/investigations/{id}`
- `GET /v1/reality/investigations/{id}/claims`
- `GET /v1/reality/investigations/{id}/evidence`
- `GET /v1/reality/investigations/{id}/certificate`
- `POST /v1/reality/investigations/{id}/review`
- `POST /v1/reality/media/search`
- `POST /v1/reality/evidence/discover`
- `GET /v1/reality/reverse-search/providers`
- `POST /v1/reality/media/ingest`
- `GET /v1/reality/media/artifacts/{artifact_id}`
- API-key protection
- SSRF protection against private/non-routable destinations
- container hardening: non-root, read-only root filesystem, dropped capabilities

Verdicts:

- `SUPPORTED`
- `CONTRADICTED`
- `MIXED`
- `MISLEADING`
- `FALSE_CONTEXT`
- `MANIPULATED_MEDIA`
- `AI_GENERATED`
- `SATIRE`
- `OUTDATED`
- `UNVERIFIED`
- `INSUFFICIENT_EVIDENCE`
- `INCONCLUSIVE`

## What v0.1 intentionally does NOT do

- autonomous search-engine discovery
- TikTok/social video remote download
- media transcription, OCR, frame extraction and deepfake ensemble execution
- deepfake detection
- geolocation
- source-reputation graph
- LLM adjudication

Those should be added only after the base contract and evidence provenance are stable.

## Run

```bash
cp .env.example .env
# edit .env and set a strong RIE_API_KEY
docker compose up -d --build
curl http://127.0.0.1:8082/v1/health
```

Frontend console:

```text
http://127.0.0.1:8082/
```

Use the `RIE_API_KEY` value from `.env`, choose `Texto` or `URL`, add up to 12
public evidence URLs, and run the verification from the browser. The console also
loads persisted results by `investigation_id`.

Docs:

```text
http://127.0.0.1:8082/docs
```

## First test

```bash
curl -sS -X POST http://127.0.0.1:8082/v1/reality/verify \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: replace-with-a-long-random-secret' \
  -d '{
    "text": "La ciudad anunció oficialmente una nueva medida de movilidad el martes.",
    "evidence_urls": [
      "https://example.com/"
    ]
  }'
```

With irrelevant evidence the expected behavior is **not** to invent certainty; typically
the result should remain `INSUFFICIENT_EVIDENCE` or `MIXED`.

## API contract

### POST `/v1/reality/verify`

```json
{
  "text": "claim or article text",
  "evidence_urls": [
    "https://primary-source.example/report"
  ]
}
```

or:

```json
{
  "url": "https://news.example/article",
  "evidence_urls": [
    "https://official.example/statement"
  ]
}
```

Representative response:

```json
{
  "investigation_id": "uuid",
  "status": "COMPLETE",
  "review_status": "AI_ANALYSIS",
  "engine": "SWAT Reality Intelligence Engine",
  "version": "0.1.0",
  "input_type": "TEXT",
  "source": {},
  "content_hash": "sha256",
  "verdict": "INSUFFICIENT_EVIDENCE",
  "confidence": 0.0,
  "dimensions": {
    "media_authenticity": 1.0,
    "claim_factuality": 0.0,
    "source_reliability": 0.0,
    "temporal_consistency": 0.0,
    "geolocation_consistency": 0.0,
    "provenance_confidence": 0.0,
    "deepfake_probability": 0.0
  },
  "claims": [],
  "evidence": [],
  "evidence_graph": {
    "nodes": [],
    "edges": []
  },
  "explanation": [],
  "limitations": [],
  "audit_trail": [],
  "reviews": [],
  "certificate_hash": "sha256"
}
```

### Review and certificate

```bash
curl -sS http://127.0.0.1:8082/v1/reality/investigations/{id}/certificate \
  -H 'X-API-Key: replace-with-a-long-random-secret'
```

```bash
curl -sS -X POST http://127.0.0.1:8082/v1/reality/investigations/{id}/review \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: replace-with-a-long-random-secret' \
  -d '{
    "action": "CERTIFY",
    "analyst": "SWAT Analyst",
    "notes": "Reviewed against provided evidence."
  }'
```

## SWAT integration target

RIE should remain a separately deployable internal service:

```text
SWAT Core / Gateway
       |
       | POST /v1/reality/verify
       v
      RIE
       |
       +--> evidence / claims / verdict
       |
       v
Unified Threat Graph
```

Recommended next contract for the Gateway:

```text
POST /v1/intelligence/reality/verify
```

The Gateway forwards to RIE and writes the normalized RIE result into the Unified Threat Graph.

## Autonomous evidence discovery

`POST /v1/reality/verify` can discover evidence URLs before scoring when
`autonomous_search` is true:

```json
{
  "text": "El Banco Central prohibio todos los pagos con Bitcoin ayer.",
  "autonomous_search": true,
  "evidence_query": "Banco Central Bitcoin pagos comunicado oficial"
}
```

The first executable provider is Bing Web Search:

```env
RIE_SEARCH_PROVIDER=bing
RIE_BING_SEARCH_API_KEY=...
RIE_MAX_DISCOVERED_EVIDENCE=5
```

Without provider credentials, RIE returns `MISSING_CONFIG` and records that in
the investigation explanation and audit trail instead of fabricating evidence.

Visual reverse search providers are exposed through:

```text
GET /v1/reality/reverse-search/providers
```

Google Lens, Yandex Images and InVID are currently manual/browser workflow
connectors. Bing Visual Search and TinEye are ready to become API-backed once
their credentials and request contracts are added. Exact SHA-256 matching and
local claim/evidence matching are active now; pHash/dHash require the media
ingestion pipeline.

## Multimedia ingestion

Upload local media as an untrusted artifact:

```bash
curl -sS -X POST http://127.0.0.1:8082/v1/reality/media/ingest \
  -H 'X-API-Key: replace-with-a-long-random-secret' \
  -F 'file=@sample.mp3'
```

RIE stores the artifact under `RIE_ARTIFACT_DIR`, calculates SHA-256, validates
basic file signatures, runs `ffprobe` for audio/video metadata, normalizes audio
to WAV 16 kHz mono, and extracts up to 12 video keyframes when FFmpeg is available.

Transcription uses `faster-whisper` only when explicitly enabled:

```env
RIE_TRANSCRIPTION_ENABLED=true
RIE_WHISPER_MODEL=tiny
```

Install/cache the selected Whisper model in the runtime environment before
enabling transcription. If the model is unavailable, the pipeline records
`TRANSCRIPTION: FAILED` instead of blocking artifact ingestion.

OCR, perceptual hashes and deepfake/audio detectors are explicit pipeline stages
and return `MISSING_TOOL` until those workers are installed.

## Production gates before v0.2

1. deterministic API-contract tests
2. SSRF test suite
3. redirect-to-private-IP test
4. max-body/timeout controls
5. provenance hashes for fetched evidence
6. Postgres migration
7. idempotency key / request fingerprint
8. structured audit log
9. source-class/reliability model
10. E2E Gateway -> RIE -> Threat Graph
