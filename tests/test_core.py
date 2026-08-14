from datetime import date
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from srd.collection import collect_sources
from srd.delegation import plan_delegation
from srd.delta import compare_runs
from srd.errors import InvalidStateTransition, PacketSourceMismatch
from srd.models import CaseOpenRequest, DelegationRequest, Finding, ResearchPacket
from srd.packets import render_brief, save_packet
from srd.store import CaseStore


def request() -> CaseOpenRequest:
    return CaseOpenRequest(
        case_key="acme-governance-2026",
        issuer_name="Acme",
        question="Q?",
        theme="governance",
        reference_date=date(2026, 8, 14),
    )


def packet(source_id: str) -> ResearchPacket:
    finding = Finding(statement="Evidence", source_ids=[source_id], confidence="medium")
    return ResearchPacket(
        thesis=[finding], counter_view=[finding], risks=[finding], open_questions=["What changed?"]
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
    result = collect_sources(store, first.run_id, ["https://example.test/a"], transport=transport)[
        0
    ]
    assert result.source and Path(result.source.text_path).read_text() == "Material evidence."
    save_packet(store, first.run_id, packet(result.source.source_id), "Review.")
    assert "## Counter-view" in render_brief(store, first.run_id).read_text()
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
    save_packet(store, later.run_id, packet(changed.source_id), "Review.")
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
        save_packet(store, run.run_id, packet("S-9999"), "Review")
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
