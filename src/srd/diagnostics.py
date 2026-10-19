from typing import Literal
from urllib.parse import urlparse

from .errors import ArtifactUnavailable
from .models import DossierDiagnostics, ResearchPlan
from .packets import evidence_depth_gaps, load_packet, load_packet_draft
from .store import CaseStore


def build_diagnostics(store: CaseStore, run_id: str) -> DossierDiagnostics:
    if store.packet_row(run_id) is not None:
        packet, _ = load_packet(store, run_id)
        stage: Literal["draft", "canonical"] = "canonical"
    else:
        draft = load_packet_draft(store, run_id)
        packet = draft.packet
        stage = "draft"
    sources = store.list_sources(run_id)
    depth_gaps = evidence_depth_gaps(store, run_id)
    findings = [*packet.thesis, *packet.counter_view, *packet.risks]
    cited = {citation.source_id for finding in findings for citation in finding.citations}
    single = sorted(
        finding.finding_id
        for finding in findings
        if len({citation.source_id for citation in finding.citations}) == 1
    )
    cross = sorted(
        finding.finding_id
        for finding in findings
        if len({citation.source_id for citation in finding.citations}) > 1
    )
    domains = {
        hostname
        for source in sources
        if (hostname := urlparse(str(source.url)).hostname) is not None
    }
    return DossierDiagnostics(
        run_id=run_id,
        packet_stage=stage,
        captured_source_count=len(sources),
        cited_source_count=len(cited),
        uncited_source_ids=sorted(
            source.source_id for source in sources if source.source_id not in cited
        ),
        source_domains=sorted(domains),
        retrieval_methods=sorted({source.retrieval_method for source in sources}),
        finding_count=len(findings),
        single_source_finding_ids=single,
        cross_source_finding_ids=cross,
        contradiction_pairs=sorted(
            (finding.finding_id, target) for finding in findings for target in finding.contradicts
        ),
        challenge_pairs=sorted(
            (finding.finding_id, target) for finding in findings for target in finding.challenges
        ),
        incomplete_issue_ids=sorted(
            issue.issue_id
            for issue in _plan(store, run_id).issues
            if issue.status not in {"satisfied", "not_applicable"}
        ),
        missing_historical_issue_ids=sorted(
            issue.issue_id
            for issue in _plan(store, run_id).issues
            if issue.historical_status not in {"satisfied", "not_applicable"}
        ),
        missing_counter_source_issue_ids=sorted(
            issue.issue_id
            for issue in _plan(store, run_id).issues
            if issue.status == "satisfied" and not issue.counter_source_ids
        ),
        evidence_depth_status="blocked" if depth_gaps else "ready",
        evidence_depth_gaps=depth_gaps,
        open_question_count=len(packet.open_questions),
    )


def _plan(store: CaseStore, run_id: str) -> ResearchPlan:
    try:
        return store.load_research_plan(run_id)
    except ArtifactUnavailable:
        return ResearchPlan.model_construct(issues=[])
