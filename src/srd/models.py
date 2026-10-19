from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, FileUrl, field_validator, model_validator

from .errors import InvalidRequest

CASE_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
RUN_ID = re.compile(r"^(?P<case_key>[a-z0-9][a-z0-9-]{2,63}):(?P<ordinal>[0-9]{4,})$")
FINDING_ID = re.compile(r"^[TCR]-[0-9]{3}$")


def validate_case_key(value: str) -> str:
    if not CASE_KEY.fullmatch(value):
        raise InvalidRequest("case_key must be a safe lowercase slug.")
    return value


def parse_run_id(value: str) -> tuple[str, int]:
    match = RUN_ID.fullmatch(value)
    if match is None or int(match["ordinal"]) == 0:
        raise InvalidRequest("run_id must be a case key followed by a four-digit ordinal.")
    return match["case_key"], int(match["ordinal"])


def validate_run_id(value: str) -> str:
    parse_run_id(value)
    return value


class CaseOpenRequest(BaseModel):
    case_key: str
    issuer_name: str = Field(min_length=1)
    question: str = Field(min_length=1)
    theme: Literal["governance", "risk", "event", "competitive", "mixed"]
    reference_date: date

    @field_validator("case_key")
    @classmethod
    def valid_key(cls, value: str) -> str:
        try:
            return validate_case_key(value)
        except InvalidRequest as error:
            raise ValueError(error.message) from error


class CaseRef(BaseModel):
    case_key: str
    issuer_name: str
    question: str
    theme: str


class RunRef(BaseModel):
    run_id: str
    case_key: str
    ordinal: int
    state: str
    reference_date: date


class SourceCapture(BaseModel):
    source_id: str
    url: AnyHttpUrl | FileUrl
    title: str = Field(min_length=1)
    publisher: str | None = None
    captured_at: datetime
    retrieval_method: Literal["static", "pdf", "host_rendered"]
    content_sha256: str
    text_path: str


class HostRenderedImport(BaseModel):
    url: AnyHttpUrl
    title: str = Field(min_length=1)
    publisher: str | None = None
    captured_at: datetime


class PdfImportMetadata(HostRenderedImport):
    """Public origin retained when an approved local PDF is imported."""


class EvidenceCitation(BaseModel):
    source_id: str
    locator: str = Field(min_length=1, max_length=160)
    excerpt: str = Field(min_length=1, max_length=800)


class Finding(BaseModel):
    finding_id: str = Field(pattern=FINDING_ID.pattern)
    statement: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]
    contradicts: list[str] = Field(default_factory=list)
    challenges: list[str] = Field(default_factory=list)


class ResearchPacket(BaseModel):
    thesis: list[Finding] = Field(min_length=1)
    counter_view: list[Finding] = Field(min_length=1)
    risks: list[Finding] = Field(min_length=1)
    open_questions: list[str] = Field(min_length=1)
    analyst_review_required: Literal[True] = True
    evidence_gaps: list[str] = Field(default_factory=list)
    assessment_status: Literal["provisional", "inconclusive"] = "provisional"

    @model_validator(mode="after")
    def valid_finding_links(self) -> ResearchPacket:
        sections = (("T-", self.thesis), ("C-", self.counter_view), ("R-", self.risks))
        findings = [finding for _, values in sections for finding in values]
        ids = [finding.finding_id for finding in findings]
        if len(ids) != len(set(ids)):
            raise ValueError("finding IDs must be unique within a packet.")
        for prefix, values in sections:
            if any(not finding.finding_id.startswith(prefix) for finding in values):
                raise ValueError("finding ID prefix must match its packet section.")
        known = set(ids)
        thesis_ids = {finding.finding_id for finding in self.thesis}
        for finding in findings:
            targets = set(finding.contradicts) | set(finding.challenges)
            if finding.finding_id in targets or not targets.issubset(known):
                raise ValueError("finding links must reference another finding in this packet.")
            if finding.confidence == "high" and len({c.source_id for c in finding.citations}) < 2:
                raise ValueError("high confidence findings require two distinct sources.")
        for finding in self.counter_view:
            targets = set(finding.contradicts) | set(finding.challenges)
            if not targets or not targets.issubset(thesis_ids):
                raise ValueError("each counter-view must link to at least one thesis finding.")
        return self


class WorkerHandoff(BaseModel):
    run_id: str
    role: str = Field(min_length=1)
    sources: list[str]
    findings: list[Finding]
    open_questions: list[str]
    recommendations_for_lead: list[str]

    @field_validator("run_id")
    @classmethod
    def valid_run_id(cls, value: str) -> str:
        try:
            return validate_run_id(value)
        except InvalidRequest as error:
            raise ValueError(error.message) from error


class Envelope(BaseModel):
    ok: bool
    data: object | None = None
    error: dict[str, object] | None = None


class DelegationRequest(BaseModel):
    case_type: Literal["new_issuer", "governance", "event", "refresh", "mixed", "exploration"]
    available_worker_cap: int = Field(ge=0)


class TaskCard(BaseModel):
    role: str
    objective: str
    allowed_source_ids: list[str]
    stop_condition: str
    handoff_schema: Literal["WorkerHandoff"] = "WorkerHandoff"


class DelegationPlan(BaseModel):
    run_id: str = ""
    max_workers: int
    join_rule: str
    tasks: list[TaskCard]


class PacketRef(BaseModel):
    packet_id: str
    run_id: str
    path: str


class PacketStatus(BaseModel):
    packet_id: str
    artifact_path: str
    brief_path: str | None


class RunSnapshot(BaseModel):
    case: CaseRef
    run: RunRef
    sources: list[SourceCapture]
    packet: PacketStatus | None


class SourceTextChunk(BaseModel):
    source_id: str
    offset: int
    next_offset: int | None
    complete: bool
    text: str


class DossierDiagnostics(BaseModel):
    run_id: str
    packet_stage: Literal["draft", "canonical"]
    captured_source_count: int
    cited_source_count: int
    uncited_source_ids: list[str]
    source_domains: list[str]
    retrieval_methods: list[str]
    finding_count: int
    single_source_finding_ids: list[str]
    cross_source_finding_ids: list[str]
    contradiction_pairs: list[tuple[str, str]]
    challenge_pairs: list[tuple[str, str]]
    incomplete_issue_ids: list[str]
    missing_historical_issue_ids: list[str]
    missing_counter_source_issue_ids: list[str]
    evidence_depth_status: Literal["ready", "blocked"]
    evidence_depth_gaps: list[str]
    open_question_count: int


class EvidenceDelta(BaseModel):
    added: list[str]
    withdrawn: list[str]
    superseded: list[tuple[str, str]]
    unchanged: list[str]
    lead_implication: str


class LeadCandidate(BaseModel):
    url: AnyHttpUrl
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    origin: Literal["last30days", "host_search"]
    discovery_query: str | None = None
    discovery_lane: Literal["institutional", "recent"] | None = None
    source_type: (
        Literal["primary", "public_authority", "independent", "community", "developer"] | None
    ) = None
    published_at: datetime | None = None
    discovered_at: datetime | None = None
    snippet: str | None = None
    engagement: dict[str, int | float | str] = Field(default_factory=dict)
    relevance_rationale: str | None = None
    screening_status: Literal["new", "eligible", "rejected", "captured"] = "new"


CoverageKind = Literal["primary", "public_authority", "independent_recent", "counter_evidence"]
CoverageStatus = Literal["planned", "discovered", "satisfied", "not_applicable", "unavailable"]


class CoverageBucket(BaseModel):
    status: CoverageStatus
    source_ids: list[str] = Field(default_factory=list)
    lead_ids: list[str] = Field(default_factory=list)
    explanation: str | None = None

    @model_validator(mode="after")
    def valid_terminal_status(self) -> CoverageBucket:
        if self.status == "satisfied" and not self.source_ids:
            raise ValueError("satisfied coverage requires a captured source ID.")
        if self.status == "satisfied" and self.lead_ids:
            raise ValueError("satisfied coverage cannot rely on lead IDs.")
        if self.status in {"not_applicable", "unavailable"} and not (
            self.explanation and self.explanation.strip()
        ):
            raise ValueError("terminal coverage status requires an explanation.")
        return self


class ResearchQuery(BaseModel):
    query_id: str = Field(pattern=r"^Q-[0-9]{3}$")
    query: str = Field(min_length=1, max_length=500)
    bucket: CoverageKind


class ResearchIssue(BaseModel):
    issue_id: str = Field(pattern=r"^I-[0-9]{3}$")
    topic: str = Field(min_length=1, max_length=160)
    research_question: str = Field(min_length=1, max_length=500)
    materiality: str = Field(min_length=1, max_length=1_000)
    status: Literal["planned", "discovered", "satisfied", "not_applicable", "unavailable"]
    source_ids: list[str] = Field(default_factory=list)
    counter_source_ids: list[str] = Field(default_factory=list)
    historical_status: Literal["planned", "satisfied", "not_applicable", "unavailable"]
    periods: list[str] = Field(default_factory=list, max_length=5)
    explanation: str | None = None

    @model_validator(mode="after")
    def evidence_bound_status(self) -> ResearchIssue:
        if self.status == "satisfied" and not self.source_ids:
            raise ValueError("satisfied issues require captured source IDs.")
        if (
            self.status == "satisfied"
            and not self.counter_source_ids
            and not (self.explanation and self.explanation.strip())
        ):
            raise ValueError("satisfied issues require counter-evidence or an explanation.")
        if self.status == "satisfied" and self.historical_status == "planned":
            raise ValueError(
                "satisfied issues require historical coverage or an explained exception."
            )
        if self.historical_status == "satisfied" and len(set(self.periods)) < 3:
            raise ValueError("satisfied historical coverage requires three distinct periods.")
        if (
            self.status in {"not_applicable", "unavailable"}
            or self.historical_status in {"not_applicable", "unavailable"}
        ) and not (self.explanation and self.explanation.strip()):
            raise ValueError("terminal issue status requires an explanation.")
        return self


class ResearchPlan(BaseModel):
    run_id: str
    issuer: str = Field(min_length=1)
    question: str = Field(min_length=1)
    theme: Literal["governance", "risk", "event", "competitive", "mixed"]
    reference_date: date
    queries: list[ResearchQuery]
    coverage: dict[CoverageKind, CoverageBucket]
    query_budget: int = Field(ge=1, le=12)
    lead_budget: int = Field(ge=1, le=50)
    capture_budget: int = Field(ge=1, le=10)
    issues: list[ResearchIssue] = Field(default_factory=list, max_length=12)
    next_gap_query: str | None = None
    failures: list[str] = Field(default_factory=list)

    @field_validator("run_id")
    @classmethod
    def valid_run_id(cls, value: str) -> str:
        try:
            return validate_run_id(value)
        except InvalidRequest as error:
            raise ValueError(error.message) from error

    @model_validator(mode="after")
    def complete_and_unique(self) -> ResearchPlan:
        expected = {
            "primary",
            "public_authority",
            "independent_recent",
            "counter_evidence",
        }
        if set(self.coverage) != expected:
            raise ValueError("coverage must contain all four evidence buckets.")
        query_ids = [query.query_id for query in self.queries]
        if len(query_ids) != len(set(query_ids)):
            raise ValueError("research query IDs must be unique.")
        if len(self.queries) > self.query_budget:
            raise ValueError("planned queries exceed the query budget.")
        issue_ids = [issue.issue_id for issue in self.issues]
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError("research issue IDs must be unique.")
        return self


class PersistedLead(LeadCandidate):
    lead_id: str = Field(pattern=r"^L-[0-9]{4}$")
    canonical_url: AnyHttpUrl


class RecentDiscoveryResult(BaseModel):
    leads: list[LeadCandidate]
    failures: list[str] = Field(default_factory=list)


class RecentDiscoveryRecord(BaseModel):
    run_id: str
    topic: str
    as_of: date
    days: int
    lead_ids: list[str]
    failures: list[str] = Field(default_factory=list)
    completed_at: datetime


class DraftRef(BaseModel):
    run_id: str
    path: str
    draft_sha256: str


class PacketDraft(BaseModel):
    run_id: str
    packet: ResearchPacket
    decision_implication: str
    path: str
    draft_sha256: str


class ApprovalRecord(BaseModel):
    run_id: str
    actor: str = Field(min_length=1)
    approved_at: datetime
    draft_sha256: str
    note: str = ""
    accepted_evidence_gaps: bool = False
    evidence_gaps: list[str] = Field(default_factory=list)
