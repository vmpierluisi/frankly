"""Fetch text from a candidate-supplied portfolio / personal site.

Hard guardrails — this fetches arbitrary URLs, so SSRF + resource-exhaustion
defenses are mandatory:

* HTTPS only.
* Block private / loopback / link-local IPs after DNS resolution.
* 10s connect/read timeout, 5MB max response body, max 8 pages, depth ≤ 2.
* Same-origin link traversal only.
* Identifies User-Agent so site owners can filter us if they want.
* Strip scripts/styles, return prose only.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "Frankly-Profile-Extractor/0.1 (+https://frankly.example)"
HTTP_TIMEOUT = 10.0
MAX_BYTES = 5 * 1024 * 1024  # 5MB
MAX_PAGES = 8
MAX_DEPTH = 2
SAMPLE_CHAR_LIMIT = 1500
PROSE_MIN_CHARS = 200


class UnsafeUrlError(ValueError):
    """Raised for URLs that fail SSRF / scheme guards."""


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_url(url: str) -> str:
    """Validate scheme + resolve host and reject private/loopback addresses.

    Returns the canonical URL on success. Raises UnsafeUrlError otherwise.
    """
    if not url:
        raise UnsafeUrlError("empty url")
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"scheme not allowed: {parsed.scheme}")
    if parsed.scheme == "http":
        raise UnsafeUrlError("only https allowed")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("missing host")

    # If host is literal IP, check directly. Otherwise resolve.
    try:
        ipaddress.ip_address(host)
        ips = [host]
    except ValueError:
        try:
            ips = [info[4][0] for info in socket.getaddrinfo(host, None)]
        except socket.gaierror as exc:
            raise UnsafeUrlError(f"dns lookup failed: {exc}") from exc

    for ip in ips:
        if _is_blocked_ip(ip):
            raise UnsafeUrlError(f"resolves to blocked address: {ip}")

    return parsed.geturl()


_TAG_STRIP = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_LINK_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


def _extract_prose(html: str) -> str:
    if not html:
        return ""
    cleaned = _TAG_STRIP.sub(" ", html)
    cleaned = _TAG_RE.sub(" ", cleaned)
    return _WS_RE.sub(" ", cleaned).strip()


def _extract_same_origin_links(html: str, base_url: str) -> list[str]:
    base_origin = urlparse(base_url)
    links: list[str] = []
    seen: set[str] = set()
    for match in _LINK_RE.findall(html or ""):
        target = urljoin(base_url, match)
        parsed = urlparse(target)
        if parsed.scheme != "https":
            continue
        if (parsed.hostname or "").lower() != (base_origin.hostname or "").lower():
            continue
        clean = parsed._replace(fragment="").geturl()
        if clean in seen:
            continue
        seen.add(clean)
        links.append(clean)
    return links


async def _fetch_one(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        async with client.stream("GET", url, headers={"User-Agent": USER_AGENT}) as resp:
            if resp.status_code >= 400:
                return None
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                return None
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > MAX_BYTES:
                    return None
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8", errors="ignore")
    except httpx.HTTPError as exc:
        logger.info("portfolio fetch failed for %s: %s", url, exc)
        return None


async def fetch_portfolio(portfolio_url: str) -> dict[str, Any]:
    """Fetch up to MAX_PAGES same-origin pages from a portfolio.

    Returns ``{prose_samples: [...], pages_fetched: int, root: str | None}``.
    Empty defaults on any failure or when the URL is rejected by SSRF guard.
    """
    if not portfolio_url:
        return {"prose_samples": [], "pages_fetched": 0, "root": None}

    try:
        root = _validate_url(portfolio_url)
    except UnsafeUrlError as exc:
        logger.info("portfolio rejected: %s", exc)
        return {"prose_samples": [], "pages_fetched": 0, "root": None}

    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(root, 0)]
    samples: list[str] = []

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        while queue and len(visited) < MAX_PAGES:
            url, depth = queue.pop(0)
            if url in visited:
                continue
            try:
                _validate_url(url)
            except UnsafeUrlError:
                continue
            visited.add(url)

            html = await _fetch_one(client, url)
            if not html:
                continue

            prose = _extract_prose(html)
            if len(prose) >= PROSE_MIN_CHARS:
                samples.append(prose[:SAMPLE_CHAR_LIMIT])

            if depth < MAX_DEPTH:
                for link in _extract_same_origin_links(html, url):
                    if link not in visited:
                        queue.append((link, depth + 1))

    return {"prose_samples": samples, "pages_fetched": len(visited), "root": root}
