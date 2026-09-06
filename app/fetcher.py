from dataclasses import dataclass
from urllib.parse import urlparse
import ipaddress
import socket

import httpx
from trafilatura import extract
from .config import settings

@dataclass
class FetchedPage:
    url: str
    title: str | None
    text: str

def _reject_private_host(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError("URL without hostname")
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only http/https URLs are allowed")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"cannot resolve host: {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified
        ):
            raise ValueError("private or non-routable destinations are blocked")

async def fetch_page(url: str) -> FetchedPage:
    _reject_private_host(url)
    headers = {"User-Agent": settings.user_agent, "Accept": "text/html,application/xhtml+xml"}
    timeout = httpx.Timeout(settings.fetch_timeout_seconds)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        final_url = str(response.url)
        _reject_private_host(final_url)
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            raise ValueError(f"unsupported content-type: {content_type}")
        text = extract(
            response.text,
            url=final_url,
            include_comments=False,
            include_tables=False,
        ) or ""
        text = text.strip()[: settings.max_source_chars]
        if not text:
            raise ValueError("no readable text extracted")
        title = None
        return FetchedPage(url=final_url, title=title, text=text)
