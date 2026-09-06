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
- aggregate verdict
- SQLite persistence
- `GET /v1/reality/investigations/{id}`
- API-key protection
- SSRF protection against private/non-routable destinations
- container hardening: non-root, read-only root filesystem, dropped capabilities

Verdicts:

- `SUPPORTED`
- `CONTRADICTED`
- `MIXED`
- `INSUFFICIENT_EVIDENCE`

## What v0.1 intentionally does NOT do

- autonomous search-engine discovery
- TikTok/video download
- frame/audio analysis
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
curl http://127.0.0.1:8088/v1/health
```

Docs:

```text
http://127.0.0.1:8088/docs
```

## First test

```bash
curl -sS -X POST http://127.0.0.1:8088/v1/reality/verify \
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
  "engine": "SWAT Reality Intelligence Engine",
  "version": "0.1.0",
  "verdict": "INSUFFICIENT_EVIDENCE",
  "confidence": 0.0,
  "claims": [],
  "evidence": [],
  "explanation": [],
  "limitations": []
}
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
