"""Bounded static public-source collection."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

from .errors import ExtractionFailed, SourceUnavailable, SrdError, UnsupportedContentType
from .models import SourceCapture
from .pdfs import extract_pdf_bytes
from .store import CaseStore

MAX_BYTES = 15 * 1024 * 1024
_ALLOWED_TYPES = {"text/html", "application/xhtml+xml", "application/pdf"}
Resolver = Callable[[str], Awaitable[set[str]]]


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


async def _test_transport_resolver(_: str) -> set[str]:
    """Mock transports do not make DNS connections, preserving isolated HTTP tests."""
    return {"93.184.216.34"}


async def _validate_public_url(url: str, resolver: Resolver) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SourceUnavailable(url, "Only public HTTP(S) URLs are allowed.")
    try:
        addresses = {str(ipaddress.ip_address(parsed.hostname))}
    except ValueError:
        addresses = await resolver(parsed.hostname)
    if not addresses:
        raise SourceUnavailable(url, "Hostname did not resolve to an address.")
    for raw_address in addresses:
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as error:
            raise SourceUnavailable(url, "Hostname returned an invalid address.") from error
        if not address.is_global or address.is_multicast or address.is_reserved:
            raise SourceUnavailable(url, "Private network targets are not allowed.")


async def _fetch(
    client: httpx.AsyncClient, url: str, semaphore: asyncio.Semaphore, resolver: Resolver
) -> tuple[httpx.Response, bytes]:
    current_url = url
    for _ in range(6):  # original request plus at most five redirects
        await _validate_public_url(current_url, resolver)
        async with semaphore, client.stream("GET", current_url) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise SourceUnavailable(
                        current_url, "Redirect response has no Location header."
                    )
                current_url = urljoin(current_url, location)
                await _validate_public_url(current_url, resolver)
                continue
            await _validate_public_url(str(response.url), resolver)
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
    resolver: Resolver,
) -> CaptureResult:
    try:
        response, data = await _fetch(client, url, semaphore, resolver)
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
        title = response.headers.get("x-srd-title") or host or "Captured source"
        source = store.add_source(
            run_id,
            url=final_url,
            title=title,
            publisher=host,
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
) -> list[CaptureResult]:
    """Capture each URL independently; a failure never aborts peer URLs."""

    run = store.get_run(run_id)
    if run.state == "OPEN":
        store.transition(run_id, "COLLECTING")

    active_resolver = resolver or (
        _test_transport_resolver if transport is not None else _resolve_hostname
    )

    async def collect() -> list[CaptureResult]:
        timeout = httpx.Timeout(30.0, connect=15.0)
        limits = httpx.Limits(max_connections=4)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
            limits=limits,
        ) as client:
            semaphore = asyncio.Semaphore(4)
            return await asyncio.gather(
                *[
                    _collect_one(client, store, run_id, url, semaphore, active_resolver)
                    for url in urls
                ]
            )

    results = asyncio.run(collect())
    final_state = store.get_run(run_id).state
    if final_state == "COLLECTING":
        store.transition(
            run_id, "SYNTHESIS_PENDING" if any(r.source for r in results) else "BLOCKED"
        )
    return results


def collect_rendered_source(store: CaseStore, run_id: str, url: str) -> CaptureResult:
    """Explicit optional rendered retrieval after static capture has failed."""
    try:
        asyncio.run(_validate_public_url(url, _resolve_hostname))
        try:
            from scrapling import Fetcher
        except ImportError as error:
            from .errors import OptionalDependencyMissing

            raise OptionalDependencyMissing("scrapling[fetchers]") from error
        response = Fetcher.get(url, timeout=30)
        final_url = str(response.url)
        asyncio.run(_validate_public_url(final_url, _resolve_hostname))
        status = getattr(response, "status", getattr(response, "status_code", 200))
        if not 200 <= status < 300:
            raise SourceUnavailable(url, f"HTTP {status}.")
        text = (trafilatura.extract(response.body, include_links=False) or "").strip()
        if not text:
            raise ExtractionFailed(url)
        run = store.get_run(run_id)
        if run.state == "OPEN":
            store.transition(run_id, "COLLECTING")
        source = store.add_source(
            run_id,
            url=final_url,
            title=urlparse(final_url).hostname or "Rendered source",
            publisher=urlparse(final_url).hostname,
            retrieval_method="rendered",
            text=text,
        )
        if store.get_run(run_id).state == "COLLECTING":
            store.transition(run_id, "SYNTHESIS_PENDING")
        return CaptureResult(url=url, source=source, error=None)
    except SrdError as error:
        return CaptureResult(url=url, source=None, error=error)
    except (OSError, ValueError) as error:
        return CaptureResult(url=url, source=None, error=SourceUnavailable(url, str(error)))
