from datetime import date
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from srd import collection
from srd.collection import MAX_BYTES, collect_sources
from srd.delegation import plan_delegation
from srd.delta import compare_runs
from srd.errors import (
    CaseExists,
    ExtractionFailed,
    InvalidRequest,
    PacketIncomplete,
    PacketSourceMismatch,
    SourceUnavailable,
)
from srd.models import CaseOpenRequest, DelegationRequest, Finding, ResearchPacket
from srd.packets import render_brief, save_packet
from srd.pdfs import extract_pdf_bytes, ingest_pdf_path
from srd.store import CaseStore


def _request(case_key: str = "failure-case-2026") -> CaseOpenRequest:
    return CaseOpenRequest(
        case_key=case_key,
        issuer_name="Example Public Issuer",
        question="Does this evidence merit review?",
        theme="governance",
        reference_date=date(2026, 8, 14),
    )


def _store(tmp_path: Path, case_key: str = "failure-case-2026") -> tuple[CaseStore, str]:
    store = CaseStore(tmp_path)
    request = _request(case_key)
    store.open_case(request)
    return store, store.start_run(case_key, request.reference_date).run_id


def _packet(source_id: str) -> ResearchPacket:
    finding = Finding(statement="Captured evidence.", source_ids=[source_id], confidence="medium")
    return ResearchPacket(
        thesis=[finding], counter_view=[finding], risks=[finding], open_questions=["What changed?"]
    )


def _complete_run(store: CaseStore, run_id: str, text: str) -> str:
    store.transition(run_id, "COLLECTING")
    source = store.add_source(
        run_id,
        url="https://www.microsoft.com/investor/reports/ar24/",
        title="Frozen public-source excerpt",
        publisher="Microsoft",
        retrieval_method="static",
        text=text,
    )
    store.transition(run_id, "SYNTHESIS_PENDING")
    save_packet(store, run_id, _packet(source.source_id), "Review the source-linked evidence.")
    render_brief(store, run_id)
    return source.source_id


def test_collection_names_empty_html_mime_and_size_failures(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/empty":
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<html></html>")
        if request.url.path == "/mime":
            return httpx.Response(200, headers={"content-type": "application/json"}, text="{}")
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"x" * (MAX_BYTES + 1)
        )

    results = collect_sources(
        store,
        run_id,
        [
            "https://example.test/empty",
            "https://example.test/mime",
            "https://example.test/large",
        ],
        transport=httpx.MockTransport(handler),
    )

    assert [result.error.code if result.error else None for result in results] == [
        "EXTRACTION_FAILED",
        "UNSUPPORTED_CONTENT_TYPE",
        "SOURCE_UNAVAILABLE",
    ]


def test_pdf_extraction_and_size_failures_are_named(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    with pytest.raises(ExtractionFailed):
        extract_pdf_bytes(b"not a PDF")

    oversized = tmp_path / "oversized.pdf"
    oversized.write_bytes(b"0" * (MAX_BYTES + 1))
    store.transition(run_id, "COLLECTING")
    with pytest.raises(SourceUnavailable):
        ingest_pdf_path(store, run_id, oversized)


def test_hostname_resolution_rejects_private_answers(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)

    async def private_dns(hostname: str) -> set[str]:
        assert hostname == "private.example"
        return {"127.0.0.1"}

    result = collect_sources(
        store,
        run_id,
        ["https://private.example/evidence"],
        transport=httpx.MockTransport(lambda _: pytest.fail("request must not be sent")),
        resolver=private_dns,
    )[0]

    assert result.error and result.error.code == "SOURCE_UNAVAILABLE"


def test_duplicate_case_lifecycle_and_identifiers_fail_closed(tmp_path: Path) -> None:
    store, first_run_id = _store(tmp_path)
    first_request = (store.run_path(first_run_id) / "request.json").read_text()
    assert store.open_case(_request()).case_key == "failure-case-2026"
    with pytest.raises(CaseExists):
        store.open_case(_request("failure-case-2026").model_copy(update={"issuer_name": "Changed"}))

    second_run = store.start_run("failure-case-2026", date(2026, 8, 15))
    assert second_run.ordinal == 2
    assert (store.run_path(first_run_id) / "request.json").read_text() == first_request
    for identifier in (
        "../escape",
        "failure-case-2026:../../escape",
        "failure-case-2026:0000",
        "failure-case-2026:01",
    ):
        with pytest.raises(InvalidRequest):
            store.get_run(identifier)


def test_packet_failures_never_create_a_brief(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    store.transition(run_id, "COLLECTING")
    store.transition(run_id, "SYNTHESIS_PENDING")
    brief = store.run_path(run_id) / "brief.md"

    with pytest.raises(PacketIncomplete):
        render_brief(store, run_id)
    with pytest.raises(PacketSourceMismatch):
        save_packet(store, run_id, _packet("S-9999"), "Review the evidence.")
    with pytest.raises(ValidationError):
        ResearchPacket.model_validate(
            {
                "thesis": [{"statement": "Claim", "source_ids": ["S-0001"], "confidence": "low"}],
                "counter_view": [],
                "risks": [{"statement": "Risk", "source_ids": ["S-0001"], "confidence": "low"}],
                "open_questions": ["What changed?"],
            }
        )
    assert not brief.exists()


def test_delta_comparison_is_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store, first_run = _store(tmp_path)
    first_source = _complete_run(store, first_run, "Earlier frozen evidence.")
    later_run = store.start_run("failure-case-2026", date(2026, 8, 15)).run_id
    later_source = _complete_run(store, later_run, "Later frozen evidence.")

    monkeypatch.setattr(
        collection.httpx,
        "AsyncClient",
        lambda *args, **kwargs: pytest.fail("delta comparison must not use HTTP"),
    )
    delta = compare_runs(
        store, "failure-case-2026", first_run, later_run, "Revisit the earlier evidence."
    )

    assert delta.superseded == [(first_source, later_source)]


@pytest.mark.parametrize("cap, expected", [(0, 0), (1, 1), (2, 2), (3, 3), (4, 3), (5, 3)])
def test_delegation_caps_and_empty_sources(cap: int, expected: int) -> None:
    plan = plan_delegation(DelegationRequest(case_type="governance", available_worker_cap=cap), [])
    assert plan.max_workers == expected
    assert all(task.allowed_source_ids == [] for task in plan.tasks)
    assert (
        plan_delegation(
            DelegationRequest(case_type="mixed", available_worker_cap=4), ["S-0001"]
        ).max_workers
        == 4
    )
