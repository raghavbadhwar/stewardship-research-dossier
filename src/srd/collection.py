"""Bounded static public-source collection."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

from .errors import (
    ArtifactUnavailable,
    ExtractionFailed,
    SourceUnavailable,
    SrdError,
    UnsupportedContentType,
)
from .models import HostRenderedImport, SourceCapture
from .pdfs import extract_pdf_bytes
from .store import CaseStore

MAX_BYTES = 15 * 1024 * 1024
_ALLOWED_TYPES = {"text/html", "application/xhtml+xml", "application/pdf"}
PUBLIC_HEADERS = {
    "User-Agent": "StewardshipResearchDossier/0.3.3 (local research prototype)",
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.1",
}
Resolver = Callable[[str], Awaitable[set[str]]]
Waiter = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class CaptureResult:
    url: str
    source: SourceCapture | None
    error: SrdError | None


async def _resolve_hostname(hostname: str) -> set[str]:
    try:
        results = await asyncio.to_thread(
            socket.getaddrinfo, hostname, None, type=socket.SOCK_STREAM
        )
    except socket.gaierror as error:
        raise SourceUnavailable(hostname, "Hostname could not be resolved.") from error
    return {str(result[4][0]) for result in results}


async def _public_address(url: httpx.URL, resolver: Resolver) -> str:
    hostname = url.host
    if url.scheme not in {"http", "https"} or not hostname:
        raise SourceUnavailable(str(url), "Only public HTTP(S) URLs are allowed.")
    try:
        addresses = {str(ipaddress.ip_address(hostname))}
    except ValueError:
        addresses = await resolver(hostname)
    if not addresses:
        raise SourceUnavailable(str(url), "Hostname did not resolve to an address.")
    approved: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for raw_address in addresses:
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as error:
            raise SourceUnavailable(str(url), "Hostname returned an invalid address.") from error
        if not address.is_global or address.is_multicast or address.is_reserved:
            raise SourceUnavailable(str(url), "Private network targets are not allowed.")
        approved.append(address)
    return str(min(approved, key=lambda address: (address.version, int(address))))


class PinnedPublicTransport(httpx.AsyncBaseTransport):
    """Connect only to an address validated for the current logical request."""

    def __init__(
        self,
        resolver: Resolver,
        inner: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._resolver = resolver
        self._inner = inner or httpx.AsyncHTTPTransport(
            trust_env=False, limits=httpx.Limits(max_connections=4)
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        address = await _public_address(request.url, self._resolver)
        headers = request.headers.copy()
        headers["host"] = request.url.netloc.decode("ascii")
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=address),
            headers=headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": request.url.host},
        )
        response = await self._inner.handle_async_request(pinned)
        response.request = request
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


async def _fetch(
    client: httpx.AsyncClient, url: str, semaphore: asyncio.Semaphore, wait: Waiter
) -> tuple[httpx.Response, bytes]:
    current_url = url
    retried = False
    for _ in range(6):  # original request plus at most five redirects
        async with semaphore, client.stream("GET", current_url) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise SourceUnavailable(
                        current_url, "Redirect response has no Location header."
                    )
                current_url = urljoin(current_url, location)
                continue
            retry_after = response.headers.get("retry-after")
            if (
                response.status_code in {429, 503}
                and not retried
                and retry_after is not None
                and retry_after.isdecimal()
                and 1 <= int(retry_after) <= 30
            ):
                retried = True
                await wait(float(retry_after))
                continue
            if not 200 <= response.status_code < 300:
                raise SourceUnavailable(current_url, f"HTTP {response.status_code}.")
            payload = bytearray()
            async for chunk in response.aiter_bytes():
                payload.extend(chunk)
                if len(payload) > MAX_BYTES:
                    raise SourceUnavailable(current_url, "Response exceeds 15 MB limit.")
            return response, bytes(payload)
    raise SourceUnavailable(url, "Redirect limit exceeded.")


async def _collect_one(
    client: httpx.AsyncClient,
    store: CaseStore,
    run_id: str,
    url: str,
    semaphore: asyncio.Semaphore,
    wait: Waiter,
) -> CaptureResult:
    try:
        response, data = await _fetch(client, url, semaphore, wait)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in _ALLOWED_TYPES:
            raise UnsupportedContentType(url, content_type)
        if content_type == "application/pdf":
            text = extract_pdf_bytes(data)
            method = "pdf"
        else:
            text = (trafilatura.extract(data, include_links=False) or "").strip()
            if not text:
                raise ExtractionFailed(url)
            method = "static"
        final_url = str(response.url)
        host = urlparse(final_url).hostname
        metadata = trafilatura.extract_metadata(data) if method == "static" else None
        title = (metadata.title if metadata else None) or host or "Captured source"
        publisher = (metadata.sitename if metadata else None) or host
        source = store.add_source(
            run_id,
            url=final_url,
            title=title,
            publisher=publisher,
            retrieval_method=method,
            text=text,
        )
        return CaptureResult(url=url, source=source, error=None)
    except SrdError as error:
        return CaptureResult(url=url, source=None, error=error)
    except (httpx.HTTPError, OSError) as error:
        return CaptureResult(url=url, source=None, error=SourceUnavailable(url, str(error)))


def collect_sources(
    store: CaseStore,
    run_id: str,
    urls: list[str],
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: Resolver | None = None,
    wait: Waiter = asyncio.sleep,
) -> list[CaptureResult]:
    """Capture each URL independently; a failure never aborts peer URLs."""

    store.begin_collection(run_id)

    active_resolver = resolver or _resolve_hostname

    async def collect() -> list[CaptureResult]:
        timeout = httpx.Timeout(30.0, connect=15.0)
        limits = httpx.Limits(max_connections=4)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            transport=PinnedPublicTransport(active_resolver, transport),
            limits=limits,
            headers=PUBLIC_HEADERS,
        ) as client:
            semaphore = asyncio.Semaphore(4)
            return await asyncio.gather(
                *[_collect_one(client, store, run_id, url, semaphore, wait) for url in urls]
            )

    return asyncio.run(collect())


def ingest_host_rendered_text(
    store: CaseStore,
    run_id: str,
    path: Path,
    metadata: HostRenderedImport,
    resolver: Resolver | None = None,
) -> SourceCapture:
    try:
        resolved = path.expanduser().resolve(strict=True)
        if not resolved.is_file():
            raise OSError
        size = resolved.stat().st_size
    except OSError as error:
        raise ArtifactUnavailable(str(path)) from error
    if size > MAX_BYTES:
        raise SourceUnavailable(str(metadata.url), "Rendered text exceeds 15 MB limit.")
    try:
        text = resolved.read_text(encoding="utf-8")
    except UnicodeError as error:
        raise ExtractionFailed(str(metadata.url), "Rendered text is not valid UTF-8.") from error
    except OSError as error:
        raise ArtifactUnavailable(str(resolved)) from error
    if not text.strip():
        raise ExtractionFailed(str(metadata.url), "Rendered text artifact is empty.")
    asyncio.run(_public_address(httpx.URL(str(metadata.url)), resolver or _resolve_hostname))
    store.begin_collection(run_id)
    return store.add_source(
        run_id,
        url=str(metadata.url),
        title=metadata.title,
        publisher=metadata.publisher,
        retrieval_method="host_rendered",
        text=text,
        captured_at=metadata.captured_at,
    )
