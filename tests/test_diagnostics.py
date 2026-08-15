import json
from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from srd.cli import app
from srd.diagnostics import build_diagnostics
from srd.models import CaseOpenRequest, EvidenceCitation, Finding, ResearchPacket
from srd.packets import save_packet, save_packet_draft
from srd.store import CaseStore


def _saved_packet(root: Path, *, draft: bool = False) -> tuple[CaseStore, str]:
    store = CaseStore(root)
    request = CaseOpenRequest(
        case_key="diagnostics-case-2026",
        issuer_name="Acme",
        question="Q?",
        theme="governance",
        reference_date=date(2026, 8, 14),
    )
    store.open_case(request)
    run_id = store.start_run(request.case_key, request.reference_date).run_id
    store.begin_collection(run_id)
    sources = [
        store.add_source(
            run_id,
            url=f"https://example{index}.test/evidence",
            title=f"Evidence {index}",
            publisher="Example",
            retrieval_method="static",
            text=f"Evidence {index}.",
        )
        for index in range(1, 4)
    ]
    store.transition(run_id, "SYNTHESIS_PENDING")
    citations = [
        EvidenceCitation(
            source_id=source.source_id,
            locator="Evidence",
            excerpt=f"Evidence {index}.",
        )
        for index, source in enumerate(sources[:2], 1)
    ]
    packet = ResearchPacket(
        thesis=[
            Finding(
                finding_id="T-001",
                statement="Thesis",
                citations=citations,
                confidence="medium",
            )
        ],
        counter_view=[
            Finding(
                finding_id="C-001",
                statement="Counter",
                citations=[citations[0]],
                confidence="low",
                contradicts=["T-001"],
            )
        ],
        risks=[
            Finding(
                finding_id="R-001",
                statement="Risk",
                citations=[citations[1]],
                confidence="low",
            )
        ],
        open_questions=["What remains unresolved?"],
    )
    if draft:
        save_packet_draft(store, run_id, packet, "Review the evidence.")
    else:
        save_packet(store, run_id, packet, "Review the evidence.")
    return store, run_id


def test_diagnostics_describe_structure_without_scoring(tmp_path: Path) -> None:
    store, run_id = _saved_packet(tmp_path)

    diagnostics = build_diagnostics(store, run_id)

    assert diagnostics.captured_source_count == 3
    assert diagnostics.packet_stage == "canonical"
    assert diagnostics.cited_source_count == 2
    assert diagnostics.uncited_source_ids == ["S-0003"]
    assert diagnostics.finding_count == 3
    assert diagnostics.single_source_finding_ids == ["C-001", "R-001"]
    assert diagnostics.cross_source_finding_ids == ["T-001"]
    assert diagnostics.contradiction_pairs == [("C-001", "T-001")]
    assert diagnostics.open_question_count == 1
    assert "score" not in diagnostics.model_dump()
    assert "recommendation" not in diagnostics.model_dump()


def test_diagnostics_use_unapproved_draft_without_promoting_it(tmp_path: Path) -> None:
    store, run_id = _saved_packet(tmp_path, draft=True)

    diagnostics = build_diagnostics(store, run_id)

    assert diagnostics.packet_stage == "draft"
    assert store.packet_row(run_id) is None


def test_diagnostics_mark_missing_issue_depth_as_blocking(tmp_path: Path) -> None:
    from test_packet_approval import synthesis_run

    store, run_id, research_packet = synthesis_run(tmp_path, complete=False)
    save_packet_draft(store, run_id, research_packet, "Review the evidence.")

    diagnostics = build_diagnostics(store, run_id)

    assert diagnostics.evidence_depth_status == "blocked"
    assert diagnostics.evidence_depth_gaps == [
        "independent_recent:unavailable",
        "issue:I-001:unavailable",
        "issue:I-001:history_unavailable",
    ]


def test_diagnostics_cli_emits_json(tmp_path: Path) -> None:
    _, run_id = _saved_packet(tmp_path)

    result = CliRunner().invoke(app, ["diagnostics", run_id, "--root", str(tmp_path)])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["run_id"] == run_id
