from datetime import date
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

import srd.models as domain_models
from srd.collection import collect_sources
from srd.delegation import plan_delegation
from srd.delta import compare_runs
from srd.errors import InvalidStateTransition, PacketSourceMismatch
from srd.models import (
    CaseOpenRequest,
    DelegationRequest,
    EvidenceCitation,
    Finding,
    ResearchPacket,
)
from srd.packets import render_brief, save_packet
from srd.store import CaseStore


async def public_dns(_: str) -> set[str]:
    return {"93.184.216.34"}


def test_findings_require_traceable_citations() -> None:
    citation_type = getattr(domain_models, "EvidenceCitation", None)
    assert citation_type is not None
    citation = citation_type(
        source_id="S-0001", locator="Risk oversight", excerpt="Captured evidence."
    )
    finding = Finding(
        finding_id="T-001", statement="Evidence", citations=[citation], confidence="medium"
    )
    assert not hasattr(finding, "source_ids")
    with pytest.raises(ValidationError):
        domain_models.SourceCapture.model_validate(
            {
                "source_id": "S-0001",
                "url": "https://example.test/evidence",
                "title": "Evidence",
                "captured_at": "2026-08-14T00:00:00Z",
                "retrieval_method": "rendered",
                "content_sha256": "0" * 64,
                "text_path": "/tmp/evidence.txt",
            }
        )


def request() -> CaseOpenRequest:
    return CaseOpenRequest(
        case_key="acme-governance-2026",
        issuer_name="Acme",
        question="Q?",
        theme="governance",
        reference_date=date(2026, 8, 14),
    )


def packet(source_id: str, excerpt: str) -> ResearchPacket:
    citation = EvidenceCitation(source_id=source_id, locator="Captured excerpt", excerpt=excerpt)
    thesis = Finding(
        finding_id="T-001",
        statement="Evidence",
        citations=[citation],
        confidence="medium",
    )
    return ResearchPacket(
        thesis=[thesis],
        counter_view=[
            Finding(
                finding_id="C-001",
                statement="Counter evidence",
                citations=[citation],
                confidence="medium",
                contradicts=["T-001"],
            )
        ],
        risks=[
            Finding(
                finding_id="R-001",
                statement="Risk evidence",
                citations=[citation],
                confidence="medium",
            )
        ],
        open_questions=["What changed?"],
    )


def test_models_and_lifecycle(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        CaseOpenRequest(
            case_key="../bad",
            issuer_name="Acme",
            question="Q?",
            theme="governance",
            reference_date=date(2026, 8, 14),
        )
    store = CaseStore(tmp_path)
    store.open_case(request())
    run = store.start_run(request().case_key, date(2026, 8, 14))
    store.transition(run.run_id, "COLLECTING")
    store.transition(run.run_id, "SYNTHESIS_PENDING")
    store.transition(run.run_id, "COMPLETE")
    with pytest.raises(InvalidStateTransition):
        store.transition(run.run_id, "COLLECTING")


def test_collection_packet_and_delta(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    store.open_case(request())
    first = store.start_run(request().case_key, date(2026, 8, 14))
    store.transition(first.run_id, "COLLECTING")
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body><p>Material evidence.</p></body></html>",
        )
    )
    result = collect_sources(
        store,
        first.run_id,
        ["https://example.test/a"],
        transport=transport,
        resolver=public_dns,
    )[0]
    assert result.source and Path(result.source.text_path).read_text() == "Material evidence."
    store.transition(first.run_id, "SYNTHESIS_PENDING")
    save_packet(
        store, first.run_id, packet(result.source.source_id, "Material evidence."), "Review."
    )
    brief = render_brief(store, first.run_id).read_text()
    assert "## Counter-view" in brief
    assert "[S-0001, Captured excerpt]" in brief
    assert "> [S-0001, Captured excerpt] Material evidence." in brief
    assert result.source.content_sha256 in brief
    later = store.start_run(request().case_key, date(2026, 8, 15))
    store.transition(later.run_id, "COLLECTING")
    changed = store.add_source(
        later.run_id,
        url="https://example.test/a",
        title="A",
        publisher=None,
        retrieval_method="static",
        text="Changed evidence.",
    )
    store.transition(later.run_id, "SYNTHESIS_PENDING")
    save_packet(store, later.run_id, packet(changed.source_id, "Changed evidence."), "Review.")
    render_brief(store, later.run_id)
    assert compare_runs(
        store, request().case_key, first.run_id, later.run_id, "Review."
    ).superseded == [(result.source.source_id, changed.source_id)]


def test_packet_binding_and_delegation(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    store.open_case(request())
    run = store.start_run(request().case_key, date(2026, 8, 14))
    store.transition(run.run_id, "COLLECTING")
    store.transition(run.run_id, "SYNTHESIS_PENDING")
    with pytest.raises(PacketSourceMismatch):
        save_packet(store, run.run_id, packet("S-9999", "Missing evidence."), "Review")
    plan = plan_delegation(
        DelegationRequest(case_type="governance", available_worker_cap=4), ["S-0001"]
    )
    assert plan.max_workers == 3 and [x.role for x in plan.tasks] == [
        "governance-analyst",
        "filings-analyst",
        "thesis-skeptic",
    ]
    assert "governance mechanisms" in plan.tasks[0].objective


def test_exploration_plan_is_bounded_and_preserves_skepticism() -> None:
    plan = plan_delegation(
        DelegationRequest(case_type="exploration", available_worker_cap=3), ["S-0001"]
    )

    assert [task.role for task in plan.tasks] == ["outlier-mind", "polymath", "thesis-skeptic"]
    assert plan.max_workers == 3
    assert "falsifiable hypotheses" in plan.tasks[0].objective


def test_run_snapshot_and_bounded_source_reads(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    store.open_case(request().model_copy(update={"case_key": "resume-case-2026"}))
    run_id = store.start_run("resume-case-2026", date(2026, 8, 14)).run_id
    store.transition(run_id, "COLLECTING")
    source = store.add_source(
        run_id,
        url="https://example.test/long-evidence",
        title="Long evidence",
        publisher="Example",
        retrieval_method="static",
        text="x" * 25_000,
    )

    snapshot = store.inspect_run(run_id)
    assert snapshot.case.case_key == "resume-case-2026"
    assert snapshot.run.run_id == run_id
    assert [item.source_id for item in snapshot.sources] == [source.source_id]
    assert snapshot.packet is None

    first = store.read_source_chunk(run_id, source.source_id, offset=0, limit=12_000)
    assert len(first.text) == 12_000
    assert first.next_offset == 12_000
    assert first.complete is False
    last = store.read_source_chunk(run_id, source.source_id, offset=24_000, limit=12_000)
    assert len(last.text) == 1_000
    assert last.next_offset is None
    assert last.complete is True


def test_packet_finding_ids_and_counter_links() -> None:
    citation = EvidenceCitation(source_id="S-0001", locator="Captured excerpt", excerpt="Evidence")
    valid = ResearchPacket(
        thesis=[
            Finding(
                finding_id="T-001",
                statement="Thesis",
                citations=[citation],
                confidence="medium",
            )
        ],
        counter_view=[
            Finding(
                finding_id="C-001",
                statement="Counter",
                citations=[citation],
                confidence="low",
                contradicts=["T-001"],
            )
        ],
        risks=[
            Finding(
                finding_id="R-001",
                statement="Risk",
                citations=[citation],
                confidence="low",
            )
        ],
        open_questions=["What remains unresolved?"],
    )
    for section, field, value in [
        ("counter_view", "contradicts", []),
        ("counter_view", "contradicts", ["T-999"]),
        ("counter_view", "contradicts", ["C-001"]),
        ("counter_view", "finding_id", "T-001"),
        ("risks", "finding_id", "T-002"),
    ]:
        payload = valid.model_dump(mode="json")
        payload[section][0][field] = value
        with pytest.raises(ValidationError):
            ResearchPacket.model_validate(payload)
