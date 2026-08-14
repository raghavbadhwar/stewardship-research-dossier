from datetime import date
from pathlib import Path

import httpx

from srd.collection import collect_sources
from srd.models import CaseOpenRequest
from srd.store import CaseStore


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
    )
    assert results[0].error and results[0].error.code == "SOURCE_UNAVAILABLE"
    assert results[1].source is not None
