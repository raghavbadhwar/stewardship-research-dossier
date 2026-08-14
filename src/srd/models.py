from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from .errors import InvalidRequest

CASE_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
RUN_ID = re.compile(r"^(?P<case_key>[a-z0-9][a-z0-9-]{2,63}):(?P<ordinal>[0-9]{4,})$")


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
    url: AnyHttpUrl
    title: str = Field(min_length=1)
    publisher: str | None = None
    captured_at: datetime
    retrieval_method: Literal["static", "pdf", "rendered"]
    content_sha256: str
    text_path: str


class Finding(BaseModel):
    statement: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]
    contradicts: list[str] = Field(default_factory=list)


class ResearchPacket(BaseModel):
    thesis: list[Finding] = Field(min_length=1)
    counter_view: list[Finding] = Field(min_length=1)
    risks: list[Finding] = Field(min_length=1)
    open_questions: list[str] = Field(min_length=1)
    analyst_review_required: Literal[True] = True


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


class EvidenceDelta(BaseModel):
    added: list[str]
    superseded: list[tuple[str, str]]
    unchanged: list[str]
    lead_implication: str


class LeadCandidate(BaseModel):
    url: AnyHttpUrl
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    origin: Literal["last30days", "host_search"]
