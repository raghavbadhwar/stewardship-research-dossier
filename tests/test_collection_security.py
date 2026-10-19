from datetime import date
from pathlib import Path

import httpx

from srd.collection import collect_sources
from srd.models import CaseOpenRequest
from srd.store import CaseStore


async def public_dns(_: str) -> set[str]:
    return {"93.184.216.34"}


def test_private_redirect_is_named_failure_and_peers_continue(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    request = CaseOpenRequest(
        case_key="redirect-case",
        issuer_name="Acme",
        question="Q?",
        theme="risk",
        reference_date=date(2026, 8, 14),
    )
    store.open_case(request)
    run = store.start_run(request.case_key, request.reference_date)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/bad":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body><p>Good evidence.</p></body></html>",
        )

    results = collect_sources(
        store,
        run.run_id,
        ["https://example.test/bad", "https://example.test/good"],
        transport=httpx.MockTransport(handler),
        resolver=public_dns,
    )
    assert results[0].error and results[0].error.code == "SOURCE_UNAVAILABLE"
    assert results[1].source is not None


def test_transport_pins_connection_once_and_captures_html_metadata(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    request = CaseOpenRequest(
        case_key="pinned-case",
        issuer_name="Acme",
        question="Q?",
        theme="governance",
        reference_date=date(2026, 8, 14),
    )
    store.open_case(request)
    run = store.start_run(request.case_key, request.reference_date)
    seen: list[httpx.Request] = []
    resolutions: list[str] = []

    async def resolver(hostname: str) -> set[str]:
        resolutions.append(hostname)
        return {"93.184.216.34"} if len(resolutions) == 1 else {"127.0.0.1"}

    def handler(transport_request: httpx.Request) -> httpx.Response:
        seen.append(transport_request)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><head><title>Board Oversight Report</title></head>"
            "<body><p>Good evidence.</p></body></html>",
        )

    result = collect_sources(
        store,
        run.run_id,
        ["https://public.example/report"],
        transport=httpx.MockTransport(handler),
        resolver=resolver,
    )[0]

    assert result.source is not None
    assert str(result.source.url) == "https://public.example/report"
    assert result.source.title == "Board Oversight Report"
    assert resolutions == ["public.example"]
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "public.example"
    assert seen[0].extensions["sni_hostname"] == "public.example"
    assert seen[0].headers["user-agent"].startswith("StewardshipResearchDossier/")
    assert "text/html" in seen[0].headers["accept"]
