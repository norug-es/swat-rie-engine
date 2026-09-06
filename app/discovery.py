import httpx

from .config import settings
from .intelligence import source_profile
from .models import EvidenceDiscoveryResponse, EvidenceDiscoveryResult, ReverseSearchProviderStatus


async def discover_evidence(query: str, limit: int | None = None) -> EvidenceDiscoveryResponse:
    provider = settings.search_provider.lower().strip()
    result_limit = min(limit or settings.max_discovered_evidence, settings.max_discovered_evidence, 12)

    if provider != "bing":
        return EvidenceDiscoveryResponse(
            status="MISSING_CONFIG",
            provider=settings.search_provider,
            query=query,
            results=[],
            message="Only bing is implemented in v0.1; set RIE_SEARCH_PROVIDER=bing.",
        )

    if not settings.bing_search_api_key:
        return EvidenceDiscoveryResponse(
            status="MISSING_CONFIG",
            provider="bing",
            query=query,
            results=[],
            message="Set RIE_BING_SEARCH_API_KEY to enable autonomous evidence discovery.",
        )

    try:
        async with httpx.AsyncClient(timeout=settings.fetch_timeout_seconds) as client:
            response = await client.get(
                settings.bing_search_endpoint,
                params={"q": query, "count": result_limit, "responseFilter": "Webpages"},
                headers={"Ocp-Apim-Subscription-Key": settings.bing_search_api_key},
            )
            response.raise_for_status()
    except Exception as exc:
        return EvidenceDiscoveryResponse(
            status="FAILED",
            provider="bing",
            query=query,
            results=[],
            message=str(exc)[:300],
        )

    payload = response.json()
    results = []
    for item in payload.get("webPages", {}).get("value", [])[:result_limit]:
        url = item.get("url")
        if not url:
            continue
        source_type, reliability = source_profile(url)
        results.append(EvidenceDiscoveryResult(
            title=item.get("name"),
            url=url,
            snippet=item.get("snippet"),
            provider="bing",
            source_type=source_type,
            source_reliability=reliability,
        ))

    return EvidenceDiscoveryResponse(status="READY", provider="bing", query=query, results=results)


def reverse_search_statuses() -> list[ReverseSearchProviderStatus]:
    providers = [item.strip() for item in settings.reverse_search_providers.split(",") if item.strip()]
    statuses = []
    for provider in providers:
        status = "MANUAL_ONLY"
        capability = "reverse visual/media search connector placeholder"
        if provider.lower() == "bing visual search":
            status = "MISSING_CONFIG"
            capability = "API-backed reverse image search when RIE_BING_VISUAL_SEARCH_API_KEY is added"
        elif provider.lower() == "tineye":
            status = "MISSING_CONFIG"
            capability = "API-backed reverse image search when TinEye credentials are added"
        elif provider.lower() == "invid":
            status = "MANUAL_ONLY"
            capability = "video verification workflow and keyframe investigation guide"
        elif provider.lower() == "google lens":
            status = "MANUAL_ONLY"
            capability = "manual/browser-based visual search; no public server API configured"
        elif provider.lower() == "yandex images":
            status = "MANUAL_ONLY"
            capability = "manual/browser-based visual search; no public server API configured"
        statuses.append(ReverseSearchProviderStatus(provider=provider, status=status, capability=capability))
    statuses.append(ReverseSearchProviderStatus(
        provider="perceptual hashes",
        status="CONFIGURED",
        capability="SHA-256 exact content matching is active; pHash/dHash require media ingestion.",
    ))
    statuses.append(ReverseSearchProviderStatus(
        provider="semantic search propia",
        status="CONFIGURED",
        capability="claim/evidence lexical semantic matching is active; embeddings can replace it later.",
    ))
    return statuses
