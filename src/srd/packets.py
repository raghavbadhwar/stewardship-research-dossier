from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from .errors import (
    ArtifactUnavailable,
    DraftNotApprovable,
    DraftNotFound,
    InvalidStateTransition,
    PacketIncomplete,
    PacketNotApproved,
)
from .models import ApprovalRecord, DraftRef, PacketDraft, PacketRef, ResearchPacket
from .store import CaseStore, _write_atomic


def _packet_text(packet: ResearchPacket, decision_implication: str) -> str:
    if not decision_implication.strip():
        raise PacketIncomplete("Decision implication is required.")
    payload = {**packet.model_dump(mode="json"), "decision_implication": decision_implication}
    return json.dumps(payload, sort_keys=True, indent=2) + "\n"


def _packet_from_text(text: str) -> tuple[ResearchPacket, str]:
    try:
        data = json.loads(text)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PacketIncomplete("Stored packet is invalid.") from error
    if not isinstance(data, dict):
        raise PacketIncomplete("Stored packet is invalid.")
    decision_implication = data.pop("decision_implication", None)
    if not isinstance(decision_implication, str) or not decision_implication.strip():
        raise PacketIncomplete("Stored packet has no decision implication.")
    try:
        packet = ResearchPacket.model_validate(data)
    except ValidationError as error:
        raise PacketIncomplete("Stored packet is invalid.") from error
    return packet, decision_implication


def _validate_packet(store: CaseStore, run_id: str, packet: ResearchPacket) -> None:
    for finding in [*packet.thesis, *packet.counter_view, *packet.risks]:
        for citation in finding.citations:
            store.validate_citation(run_id, citation)
    try:
        plan = store.load_research_plan(run_id)
    except ArtifactUnavailable:
        return
    missing = []
    if plan.coverage["primary"].status != "satisfied":
        missing.append("primary")
    if plan.coverage["public_authority"].status != "satisfied":
        missing.append("public_authority")
    if missing and (
        packet.assessment_status != "inconclusive"
        or not any(
            any(missing_name in gap for missing_name in missing) for gap in packet.evidence_gaps
        )
    ):
        raise PacketIncomplete(
            "Missing primary or public-authority coverage requires labelled gaps."
        )


def _save_packet_text(store: CaseStore, run_id: str, text: str) -> PacketRef:
    run = store.get_run(run_id)
    if store.packet_row(run_id) is not None:
        raise PacketIncomplete("Packet already saved for run.")
    path = store.run_path(run_id) / "packet.json"
    packet_id = f"P-{run.ordinal:04d}"
    _write_atomic(path, text)
    try:
        store.save_packet_row(run_id, packet_id, path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return PacketRef(packet_id=packet_id, run_id=run_id, path=str(path))


def load_packet(store: CaseStore, run_id: str) -> tuple[ResearchPacket, str]:
    row = store.packet_row(run_id)
    if row is None:
        raise PacketIncomplete("No packet saved for run.")
    artifact_path = Path(row["artifact_path"])
    try:
        text = artifact_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ArtifactUnavailable(str(artifact_path)) from error
    return _packet_from_text(text)


def save_packet(
    store: CaseStore, run_id: str, packet: ResearchPacket, decision_implication: str
) -> PacketRef:
    run = store.get_run(run_id)
    if run.state not in {"SYNTHESIS_PENDING", "PARTIAL", "REVIEW_PENDING"}:
        raise InvalidStateTransition(run.state, "COMPLETE")
    _validate_packet(store, run_id, packet)
    return _save_packet_text(store, run_id, _packet_text(packet, decision_implication))


def save_packet_draft(
    store: CaseStore, run_id: str, packet: ResearchPacket, decision_implication: str
) -> DraftRef:
    run = store.get_run(run_id)
    if run.state not in {"SYNTHESIS_PENDING", "PARTIAL", "REVIEW_PENDING"}:
        raise InvalidStateTransition(run.state, "REVIEW_PENDING")
    if store.packet_row(run_id) is not None:
        raise DraftNotApprovable("A canonical packet already exists for this run.")
    _validate_packet(store, run_id, packet)
    text = _packet_text(packet, decision_implication)
    digest = hashlib.sha256(text.encode()).hexdigest()
    draft_path = store.run_path(run_id) / "packet-draft.json"
    digest_path = store.run_path(run_id) / "packet-draft.sha256"
    _write_atomic(draft_path, text)
    try:
        _write_atomic(digest_path, digest + "\n")
        if run.state != "REVIEW_PENDING":
            store.transition(run_id, "REVIEW_PENDING")
    except Exception:
        draft_path.unlink(missing_ok=True)
        digest_path.unlink(missing_ok=True)
        raise
    return DraftRef(run_id=run_id, path=str(draft_path), draft_sha256=digest)


def load_packet_draft(store: CaseStore, run_id: str) -> PacketDraft:
    draft_path = store.run_path(run_id) / "packet-draft.json"
    digest_path = store.run_path(run_id) / "packet-draft.sha256"
    try:
        text = draft_path.read_text(encoding="utf-8")
        recorded_digest = digest_path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise DraftNotFound() from error
    actual_digest = hashlib.sha256(text.encode()).hexdigest()
    if not recorded_digest or actual_digest != recorded_digest:
        raise DraftNotApprovable("The saved draft no longer matches its recorded hash.")
    packet, decision_implication = _packet_from_text(text)
    _validate_packet(store, run_id, packet)
    return PacketDraft(
        run_id=run_id,
        packet=packet,
        decision_implication=decision_implication,
        path=str(draft_path),
        draft_sha256=actual_digest,
    )


def evidence_depth_gaps(store: CaseStore, run_id: str) -> list[str]:
    try:
        plan = store.load_research_plan(run_id)
    except ArtifactUnavailable:
        return ["research_plan:unavailable"]
    gaps = [
        f"{name}:{bucket.status}"
        for name, bucket in plan.coverage.items()
        if bucket.status not in {"satisfied", "not_applicable"}
    ]
    sources = store.list_sources(run_id)
    if len(sources) < 3:
        gaps.append("captured_sources:fewer_than_3")
    domains = {urlsplit(str(source.url)).hostname for source in sources}
    domains.discard(None)
    if len(domains) < 2:
        gaps.append("source_domains:fewer_than_2")
    primary_sources = {
        source_id
        for bucket in (plan.coverage["primary"], plan.coverage["public_authority"])
        for source_id in bucket.source_ids
    }
    if not primary_sources.intersection(source.source_id for source in sources):
        gaps.append("primary_or_public_authority:no_captured_source")
    if not any(query.bucket == "counter_evidence" for query in plan.queries):
        gaps.append("counter_evidence:no_search")
    if not plan.issues:
        gaps.append("issues:none")
    for issue in plan.issues:
        if issue.status not in {"satisfied", "not_applicable"}:
            gaps.append(f"issue:{issue.issue_id}:{issue.status}")
        if issue.historical_status not in {"satisfied", "not_applicable"}:
            gaps.append(f"issue:{issue.issue_id}:history_{issue.historical_status}")
        if issue.status == "satisfied" and not issue.counter_source_ids:
            gaps.append(f"issue:{issue.issue_id}:counter_evidence_missing")
    return gaps


def load_approval(store: CaseStore, run_id: str) -> ApprovalRecord | None:
    approval_path = store.run_path(run_id) / "approval.json"
    if not approval_path.exists():
        return None
    try:
        return ApprovalRecord.model_validate_json(approval_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ArtifactUnavailable(str(approval_path)) from error


def approve_packet(
    store: CaseStore,
    run_id: str,
    actor: str,
    note: str = "",
    *,
    accept_evidence_gaps: bool = False,
) -> ApprovalRecord:
    run = store.get_run(run_id)
    if run.state != "REVIEW_PENDING":
        raise DraftNotApprovable("The run is not awaiting review.")
    if not actor.strip():
        raise DraftNotApprovable("An approval actor is required.")
    if load_approval(store, run_id) is not None:
        raise DraftNotApprovable("The draft is already approved.")
    draft = load_packet_draft(store, run_id)
    gaps = evidence_depth_gaps(store, run_id)
    if gaps and not accept_evidence_gaps:
        raise DraftNotApprovable("Evidence coverage is incomplete.")
    if gaps and not note.strip():
        raise DraftNotApprovable("Evidence-gap acceptance requires a rationale.")
    if gaps and (
        draft.packet.assessment_status != "inconclusive" or not draft.packet.evidence_gaps
    ):
        raise DraftNotApprovable("Evidence-incomplete approval requires an inconclusive packet.")
    approval = ApprovalRecord(
        run_id=run_id,
        actor=actor.strip(),
        approved_at=datetime.now(UTC),
        draft_sha256=draft.draft_sha256,
        note=note.strip(),
        accepted_evidence_gaps=bool(gaps),
        evidence_gaps=gaps,
    )
    approval_path = store.run_path(run_id) / "approval.json"
    _write_atomic(approval_path, approval.model_dump_json(indent=2))
    try:
        text = Path(draft.path).read_text(encoding="utf-8")
        _save_packet_text(store, run_id, text)
    except Exception:
        approval_path.unlink(missing_ok=True)
        raise
    return approval


def render_brief(store: CaseStore, run_id: str) -> Path:
    run = store.get_run(run_id)
    draft_path = store.run_path(run_id) / "packet-draft.json"
    approval = load_approval(store, run_id)
    if draft_path.exists() and approval is None:
        raise PacketNotApproved()
    packet, decision_implication = load_packet(store, run_id)
    if approval is not None:
        row = store.packet_row(run_id)
        if row is None:
            raise PacketNotApproved()
        packet_text = Path(row["artifact_path"]).read_text(encoding="utf-8")
        if hashlib.sha256(packet_text.encode()).hexdigest() != approval.draft_sha256:
            raise DraftNotApprovable("The canonical packet does not match the approved draft.")
    case = store.get_case(run.case_key)
    lines = [
        f"# {case.issuer_name} — {case.theme.title()} Research Brief",
        "",
        "## Assessment status",
        (
            "INCONCLUSIVE — EVIDENCE INCOMPLETE"
            if packet.assessment_status == "inconclusive"
            else "PROVISIONAL"
        ),
        "",
        "## Analyst review required",
        "True",
    ]
    try:
        plan = store.load_research_plan(run_id)
    except ArtifactUnavailable:
        plan = None
    if plan is not None:
        lines += ["", "## Coverage summary"]
        lines.extend(
            f"- {name}: {bucket.status}"
            + (f" [{', '.join(bucket.source_ids)}]" if bucket.source_ids else "")
            + (f" — {bucket.explanation}" if bucket.explanation else "")
            for name, bucket in plan.coverage.items()
        )
        lines += ["", "## Research issues"]
        lines.extend(
            f"- {issue.issue_id} — {issue.topic}: {issue.status}; history {issue.historical_status}"
            + (f" ({', '.join(issue.periods)})" if issue.periods else "")
            + (f" [{', '.join(issue.source_ids)}]" if issue.source_ids else "")
            + (f" — {issue.explanation}" if issue.explanation else "")
            for issue in plan.issues
        )
    for heading, findings in (
        ("Current thesis", packet.thesis),
        ("Counter-view", packet.counter_view),
        ("Risks", packet.risks),
    ):
        lines += ["", f"## {heading}"]
        for finding in findings:
            labels = "; ".join(
                f"{citation.source_id}, {citation.locator}" for citation in finding.citations
            )
            lines.append(f"- **{finding.finding_id}** {finding.statement} [{labels}]")
            if len({citation.source_id for citation in finding.citations}) == 1:
                lines.append("  - single-source")
            if finding.contradicts:
                lines.append(f"  - Contradicts: {', '.join(finding.contradicts)}")
            if finding.challenges:
                lines.append(f"  - Challenges: {', '.join(finding.challenges)}")
            lines.extend(
                f"  > [{citation.source_id}, {citation.locator}] {citation.excerpt}"
                for citation in finding.citations
            )
    lines += [
        "",
        "## Evidence gaps",
        *[f"- {gap}" for gap in packet.evidence_gaps],
        "",
        "## Open questions",
        *[f"- {q}" for q in packet.open_questions],
        "",
        "## Decision implication",
        decision_implication,
        "",
        "## Approval metadata",
        f"Approved by: {approval.actor if approval else 'not approved'}",
        "",
        "## Evidence ledger",
    ]
    for s in store.list_sources(run_id):
        lines.append(
            f"- {s.source_id} — {s.title}, {s.url}, captured {s.captured_at.isoformat()}, "
            f"via {s.retrieval_method}, SHA-256 {s.content_sha256}"
        )
    path = store.run_path(run_id) / "brief.md"
    _write_atomic(path, "\n".join(lines) + "\n")
    try:
        store.set_brief_path(run_id, path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    if run.state in {"SYNTHESIS_PENDING", "REVIEW_PENDING"}:
        store.transition(run_id, "COMPLETE")
    return path
