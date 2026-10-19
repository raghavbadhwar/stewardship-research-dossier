import hashlib
import sqlite3
from datetime import date
from pathlib import Path

import httpx
import pymupdf
import pytest
from pydantic import ValidationError

from srd import collection
from srd.collection import MAX_BYTES, collect_sources, ingest_host_rendered_text
from srd.delegation import plan_delegation
from srd.delta import compare_runs
from srd.errors import (
    ArtifactUnavailable,
    CaseExists,
    EvidenceExcerptMismatch,
    ExtractionFailed,
    InvalidRequest,
    PacketIncomplete,
    PacketSourceMismatch,
    RunNotComparable,
    SourceUnavailable,
)
from srd.mcp_server import create_server
from srd.models import (
    CaseOpenRequest,
    DelegationRequest,
    EvidenceCitation,
    Finding,
    HostRenderedImport,
    ResearchPacket,
    WorkerHandoff,
)
from srd.packets import render_brief, save_packet
from srd.pdfs import extract_pdf_bytes, ingest_pdf_path
from srd.store import CaseStore


async def public_dns(_: str) -> set[str]:
    return {"93.184.216.34"}


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


def _packet(source_id: str, excerpt: str = "Captured evidence.") -> ResearchPacket:
    citation = EvidenceCitation(source_id=source_id, locator="Captured excerpt", excerpt=excerpt)
    thesis = Finding(
        finding_id="T-001",
        statement="Captured evidence.",
        citations=[citation],
        confidence="medium",
    )
    return ResearchPacket(
        thesis=[thesis],
        counter_view=[
            Finding(
                finding_id="C-001",
                statement="Counter evidence.",
                citations=[citation],
                confidence="medium",
                contradicts=["T-001"],
            )
        ],
        risks=[
            Finding(
                finding_id="R-001",
                statement="Risk evidence.",
                citations=[citation],
                confidence="medium",
            )
        ],
        open_questions=["What changed?"],
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
    save_packet(
        store,
        run_id,
        _packet(source.source_id, text),
        "Review the source-linked evidence.",
    )
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
        resolver=public_dns,
    )

    assert [result.error.code if result.error else None for result in results] == [
        "EXTRACTION_FAILED",
        "UNSUPPORTED_CONTENT_TYPE",
        "SOURCE_UNAVAILABLE",
    ]


def test_pdf_extraction_and_size_failures_are_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, run_id = _store(tmp_path)
    with pytest.raises(ExtractionFailed):
        extract_pdf_bytes(b"not a PDF")

    oversized = tmp_path / "oversized.pdf"
    oversized.write_bytes(b"0" * (MAX_BYTES + 1))
    store.transition(run_id, "COLLECTING")
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda _: pytest.fail("oversized PDF must be rejected before reading"),
    )
    with pytest.raises(SourceUnavailable):
        ingest_pdf_path(store, run_id, oversized)


def test_pdf_ingest_from_open_run_can_finish_collection(tmp_path: Path) -> None:
    pdf_path = tmp_path / "evidence.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Board oversight evidence")
    document.save(pdf_path)
    document.close()
    server = create_server(tmp_path / "cases")
    tool = server._tool_manager.get_tool  # type: ignore[attr-defined]
    opened = tool("case_open").fn(  # type: ignore[union-attr]
        {
            "case_key": "pdf-only-2026",
            "issuer_name": "Example Public Issuer",
            "question": "What board oversight evidence is available?",
            "theme": "governance",
            "reference_date": "2026-08-14",
        }
    )
    run_id = opened["data"]["run_id"]

    ingested = tool("filing_ingest").fn(run_id, str(pdf_path))  # type: ignore[union-attr]

    assert ingested["ok"] is True
    assert ingested["data"]["url"].startswith("file:")
    assert CaseStore(tmp_path / "cases").get_run(run_id).state == "COLLECTING"
    finished = tool("collection_finish").fn(run_id)  # type: ignore[union-attr]
    assert finished["ok"] is True
    assert finished["data"]["state"] == "SYNTHESIS_PENDING"
    repeated = tool("collection_finish").fn(run_id)  # type: ignore[union-attr]
    assert repeated["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_blocked_run_can_retry_collection(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    failed = collect_sources(
        store,
        run_id,
        ["https://example.test/evidence"],
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
        resolver=public_dns,
    )
    assert failed[0].error is not None
    assert store.get_run(run_id).state == "COLLECTING"
    store.transition(run_id, "BLOCKED")

    successful = collect_sources(
        store,
        run_id,
        ["https://example.test/evidence"],
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html><body><p>Board oversight evidence.</p></body></html>",
            )
        ),
        resolver=public_dns,
    )

    assert successful[0].source is not None
    assert store.get_run(run_id).state == "COLLECTING"


def test_host_rendered_text_import_is_bounded_and_hashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, run_id = _store(tmp_path)
    path = tmp_path / "rendered.txt"
    path.write_text("Exact rendered evidence.\n", encoding="utf-8")
    metadata = HostRenderedImport(
        url="https://example.test/rendered",
        title="Rendered evidence",
        publisher="Example",
        captured_at="2026-08-14T09:00:00Z",
    )

    source = ingest_host_rendered_text(store, run_id, path, metadata, resolver=public_dns)

    assert source.retrieval_method == "host_rendered"
    assert str(source.url) == "https://example.test/rendered"
    assert Path(source.text_path).read_text(encoding="utf-8") == "Exact rendered evidence.\n"
    assert source.content_sha256 == hashlib.sha256(b"Exact rendered evidence.\n").hexdigest()
    assert source.captured_at == metadata.captured_at
    assert store.get_run(run_id).state == "COLLECTING"

    oversized = tmp_path / "oversized.txt"
    oversized.write_bytes(b"x" * (MAX_BYTES + 1))
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *args, **kwargs: pytest.fail("oversized text must be rejected before reading"),
    )
    with pytest.raises(SourceUnavailable):
        ingest_host_rendered_text(store, run_id, oversized, metadata, resolver=public_dns)


def test_host_rendered_import_failures_do_not_mutate_open_run(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    metadata = HostRenderedImport(
        url="https://example.test/rendered",
        title="Rendered evidence",
        captured_at="2026-08-14T09:00:00Z",
    )
    with pytest.raises(ArtifactUnavailable):
        ingest_host_rendered_text(
            store, run_id, tmp_path / "missing.txt", metadata, resolver=public_dns
        )
    invalid = tmp_path / "invalid.txt"
    invalid.write_bytes(b"\xff")
    with pytest.raises(ExtractionFailed):
        ingest_host_rendered_text(store, run_id, invalid, metadata, resolver=public_dns)
    empty = tmp_path / "empty.txt"
    empty.write_text("  \n", encoding="utf-8")
    with pytest.raises(ExtractionFailed):
        ingest_host_rendered_text(store, run_id, empty, metadata, resolver=public_dns)

    async def private_dns(_: str) -> set[str]:
        return {"127.0.0.1"}

    valid = tmp_path / "valid.txt"
    valid.write_text("Evidence", encoding="utf-8")
    with pytest.raises(SourceUnavailable):
        ingest_host_rendered_text(store, run_id, valid, metadata, resolver=private_dns)
    assert store.get_run(run_id).state == "OPEN"


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


def test_source_insert_failure_closes_db_and_removes_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, run_id = _store(tmp_path)
    store.transition(run_id, "COLLECTING")
    with store._db("failure-case-2026") as conn, conn:
        conn.execute(
            "CREATE TRIGGER reject_source BEFORE INSERT ON sources "
            "BEGIN SELECT RAISE(FAIL, 'rejected'); END"
        )
    real_connect = sqlite3.connect
    opened: set[int] = set()
    closed: set[int] = set()

    class TrackingConnection(sqlite3.Connection):
        def close(self) -> None:
            closed.add(id(self))
            super().close()

    def tracking_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs, factory=TrackingConnection)
        opened.add(id(connection))
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)

    with pytest.raises(sqlite3.IntegrityError):
        store.add_source(
            run_id,
            url="https://example.test/evidence",
            title="Evidence",
            publisher="Example",
            retrieval_method="static",
            text="Captured evidence.",
        )

    assert list((store.run_path(run_id) / "sources").iterdir()) == []
    with store._db("failure-case-2026") as conn:
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0
    assert opened == closed


def test_source_ids_do_not_collide_after_row_deletion(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    store.transition(run_id, "COLLECTING")
    sources = [
        store.add_source(
            run_id,
            url=f"https://example.test/{index}",
            title=str(index),
            publisher="Example",
            retrieval_method="static",
            text=str(index),
        )
        for index in range(3)
    ]
    with store._db("failure-case-2026") as conn, conn:
        conn.execute("DELETE FROM sources WHERE source_id=?", (sources[1].source_id,))

    later = store.add_source(
        run_id,
        url="https://example.test/later",
        title="Later",
        publisher="Example",
        retrieval_method="static",
        text="Later",
    )

    assert later.source_id == "S-0004"


def test_handoffs_validate_finding_citations_and_use_case_stable_ids(tmp_path: Path) -> None:
    store, first_run = _store(tmp_path)
    store.transition(first_run, "COLLECTING")
    first_source = store.add_source(
        first_run,
        url="https://example.test/first",
        title="First",
        publisher="Example",
        retrieval_method="static",
        text="First evidence.",
    )

    def handoff(
        run_id: str, source_id: str, citation_id: str, excerpt: str = "Evidence."
    ) -> WorkerHandoff:
        return WorkerHandoff(
            run_id=run_id,
            role="governance-analyst",
            sources=[source_id],
            findings=[
                Finding(
                    finding_id="T-001",
                    statement="Evidence.",
                    citations=[
                        EvidenceCitation(
                            source_id=citation_id,
                            locator="Evidence",
                            excerpt=excerpt,
                        )
                    ],
                    confidence="medium",
                )
            ],
            open_questions=[],
            recommendations_for_lead=[],
        )

    with pytest.raises(PacketSourceMismatch):
        store.save_handoff(handoff(first_run, first_source.source_id, "S-9999"))
    assert (
        store.save_handoff(
            handoff(first_run, first_source.source_id, first_source.source_id, "First evidence.")
        )
        == "H-0001"
    )

    second_run = store.start_run("failure-case-2026", date(2026, 8, 15)).run_id
    store.transition(second_run, "COLLECTING")
    second_source = store.add_source(
        second_run,
        url="https://example.test/second",
        title="Second",
        publisher="Example",
        retrieval_method="static",
        text="Second evidence.",
    )
    assert (
        store.save_handoff(
            handoff(
                second_run,
                second_source.source_id,
                second_source.source_id,
                "Second evidence.",
            )
        )
        == "H-0002"
    )


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
                "thesis": [
                    {
                        "statement": "Claim",
                        "citations": [
                            {
                                "source_id": "S-0001",
                                "locator": "Claim",
                                "excerpt": "Evidence",
                            }
                        ],
                        "confidence": "low",
                    }
                ],
                "counter_view": [],
                "risks": [
                    {
                        "statement": "Risk",
                        "citations": [
                            {
                                "source_id": "S-0001",
                                "locator": "Risk",
                                "excerpt": "Evidence",
                            }
                        ],
                        "confidence": "low",
                    }
                ],
                "open_questions": ["What changed?"],
            }
        )
    assert not brief.exists()


def test_packet_rejects_excerpt_absent_from_captured_source(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    store.transition(run_id, "COLLECTING")
    source = store.add_source(
        run_id,
        url="https://example.test/evidence",
        title="Evidence",
        publisher="Example",
        retrieval_method="static",
        text="Captured evidence.",
    )
    store.transition(run_id, "SYNTHESIS_PENDING")

    with pytest.raises(EvidenceExcerptMismatch):
        save_packet(store, run_id, _packet(source.source_id, "Invented excerpt."), "Review.")


def test_missing_packet_artifact_has_named_failure(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    _complete_run(store, run_id, "Captured evidence.")
    packet_path = store.run_path(run_id) / "packet.json"
    packet_path.unlink()

    with pytest.raises(ArtifactUnavailable):
        render_brief(store, run_id)


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


def test_delta_rejects_non_chronological_runs_and_tracks_withdrawals(tmp_path: Path) -> None:
    store, first_run = _store(tmp_path)
    store.transition(first_run, "COLLECTING")
    retained = store.add_source(
        first_run,
        url="https://www.microsoft.com/investor/reports/ar24/",
        title="Retained",
        publisher="Example",
        retrieval_method="static",
        text="Earlier evidence.",
    )
    withdrawn = store.add_source(
        first_run,
        url="https://example.test/withdrawn",
        title="Withdrawn",
        publisher="Example",
        retrieval_method="static",
        text="Withdrawn evidence.",
    )
    store.transition(first_run, "SYNTHESIS_PENDING")
    save_packet(store, first_run, _packet(retained.source_id, "Earlier evidence."), "Review.")
    render_brief(store, first_run)
    later_run = store.start_run("failure-case-2026", date(2026, 8, 15)).run_id
    _complete_run(store, later_run, "Later evidence.")

    delta = compare_runs(store, "failure-case-2026", first_run, later_run, "Review.")
    assert delta.withdrawn == [withdrawn.source_id]
    with pytest.raises(RunNotComparable):
        compare_runs(store, "failure-case-2026", later_run, first_run, "Review.")
    with pytest.raises(RunNotComparable):
        compare_runs(store, "failure-case-2026", first_run, first_run, "Review.")


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
