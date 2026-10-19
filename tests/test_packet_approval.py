from __future__ import annotations

import importlib
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from srd.errors import SrdError
from srd.models import (
    CaseOpenRequest,
    EvidenceCitation,
    Finding,
    ResearchPacket,
    ResearchPlan,
)
from srd.store import CaseStore


def packet_module() -> Any:
    return importlib.import_module("srd.packets")


def packet(source_id: str, excerpt: str) -> ResearchPacket:
    citation = EvidenceCitation(source_id=source_id, locator="Evidence", excerpt=excerpt)
    return ResearchPacket(
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


def synthesis_run(tmp_path: Path, *, complete: bool) -> tuple[CaseStore, str, ResearchPacket]:
    store = CaseStore(tmp_path)
    request = CaseOpenRequest(
        case_key="approval-case-2026",
        issuer_name="Acme",
        question="Is governance effective?",
        theme="governance",
        reference_date=date(2026, 8, 14),
    )
    store.open_case(request)
    run_id = store.start_run(request.case_key, request.reference_date).run_id
    store.begin_collection(run_id)
    sources = [
        store.add_source(
            run_id,
            url=url,
            title=f"Evidence {index}",
            publisher=None,
            retrieval_method="static",
            text="Material evidence.",
        )
        for index, url in enumerate(
            [
                "https://issuer.example/report",
                "https://authority.example/action",
                "https://news.example/analysis",
            ],
            start=1,
        )
    ]
    coverage: dict[str, dict[str, object]] = {
        "primary": {"status": "satisfied", "source_ids": [sources[0].source_id]},
        "public_authority": {
            "status": "satisfied",
            "source_ids": [sources[1].source_id],
        },
        "independent_recent": {
            "status": "satisfied" if complete else "unavailable",
            "source_ids": [sources[2].source_id] if complete else [],
            "explanation": None if complete else "No eligible recent report was found.",
        },
        "counter_evidence": {
            "status": "satisfied",
            "source_ids": [sources[1].source_id],
        },
    }
    plan = ResearchPlan.model_validate(
        {
            "run_id": run_id,
            "issuer": "Acme",
            "question": request.question,
            "theme": request.theme,
            "reference_date": request.reference_date,
            "queries": [
                {"query_id": "Q-001", "query": "Acme report", "bucket": "primary"},
                {
                    "query_id": "Q-002",
                    "query": "Acme contrary evidence",
                    "bucket": "counter_evidence",
                },
            ],
            "coverage": coverage,
            "query_budget": 12,
            "lead_budget": 50,
            "capture_budget": 10,
            "issues": [
                {
                    "issue_id": "I-001",
                    "topic": "Board oversight",
                    "research_question": "Is oversight adequate?",
                    "materiality": "Oversight informs accountability.",
                    "status": "satisfied" if complete else "unavailable",
                    "source_ids": [sources[0].source_id] if complete else [],
                    "counter_source_ids": [sources[1].source_id] if complete else [],
                    "historical_status": "satisfied" if complete else "unavailable",
                    "periods": ["2024", "2025", "2026"] if complete else [],
                    "explanation": None if complete else "Evidence was unavailable.",
                }
            ],
        }
    )
    store.save_research_plan(run_id, plan)
    store.transition(run_id, "SYNTHESIS_PENDING")
    research_packet = packet(sources[0].source_id, "Material evidence.")
    if not complete:
        research_packet = research_packet.model_copy(
            update={
                "assessment_status": "inconclusive",
                "evidence_gaps": ["independent_recent:unavailable"],
            }
        )
    return store, run_id, research_packet


def test_draft_survives_reload_and_cannot_render_before_approval(tmp_path: Path) -> None:
    store, run_id, research_packet = synthesis_run(tmp_path, complete=True)
    module = packet_module()
    save = getattr(module, "save_packet_draft", None)
    assert save is not None

    draft = save(store, run_id, research_packet, "Review it.")
    reloaded = module.load_packet_draft(CaseStore(tmp_path), run_id)

    assert reloaded.draft_sha256 == draft.draft_sha256
    assert reloaded.packet == research_packet
    with pytest.raises(SrdError) as error:
        module.render_brief(store, run_id)
    assert error.value.code == "PACKET_NOT_APPROVED"


def test_approval_promotes_exact_draft_hash(tmp_path: Path) -> None:
    store, run_id, research_packet = synthesis_run(tmp_path, complete=True)
    module = packet_module()
    save = getattr(module, "save_packet_draft", None)
    approve = getattr(module, "approve_packet", None)
    assert save is not None and approve is not None

    draft = save(store, run_id, research_packet, "Review it.")
    approval = approve(store, run_id, "analyst", "Approved after review.")

    assert approval.draft_sha256 == draft.draft_sha256
    assert module.load_packet(store, run_id)[0] == research_packet
    assert module.render_brief(store, run_id).is_file()
    assert store.get_run(run_id).state == "COMPLETE"


def test_incomplete_coverage_requires_explicit_rationale(tmp_path: Path) -> None:
    store, run_id, research_packet = synthesis_run(tmp_path, complete=False)
    module = packet_module()
    save = getattr(module, "save_packet_draft", None)
    approve = getattr(module, "approve_packet", None)
    assert save is not None and approve is not None
    save(store, run_id, research_packet, "Review it.")

    with pytest.raises(SrdError) as missing_override:
        approve(store, run_id, "analyst", "")
    assert missing_override.value.code == "DRAFT_NOT_APPROVABLE"
    with pytest.raises(SrdError) as missing_rationale:
        approve(store, run_id, "analyst", "", accept_evidence_gaps=True)
    assert missing_rationale.value.code == "DRAFT_NOT_APPROVABLE"

    approved = approve(
        store,
        run_id,
        "analyst",
        "Accepted because recent reporting was unavailable.",
        accept_evidence_gaps=True,
    )
    assert approved.accepted_evidence_gaps is True
    assert "independent_recent:unavailable" in approved.evidence_gaps


def test_approval_rejects_a_tampered_draft(tmp_path: Path) -> None:
    store, run_id, research_packet = synthesis_run(tmp_path, complete=True)
    module = packet_module()
    save = getattr(module, "save_packet_draft", None)
    approve = getattr(module, "approve_packet", None)
    assert save is not None and approve is not None
    draft = save(store, run_id, research_packet, "Review it.")
    draft_path = Path(draft.path)
    draft_path.write_text(draft_path.read_text().replace("Thesis", "Changed"), encoding="utf-8")

    with pytest.raises(SrdError) as error:
        approve(store, run_id, "analyst", "Approved")
    assert error.value.code == "DRAFT_NOT_APPROVABLE"
