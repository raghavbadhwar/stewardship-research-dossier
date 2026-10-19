from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

import srd.models as domain_models
from srd.errors import InvalidRequest
from srd.models import CaseOpenRequest
from srd.store import CaseStore


def opened_run(tmp_path: Path) -> tuple[CaseStore, str]:
    store = CaseStore(tmp_path)
    request = CaseOpenRequest(
        case_key="plan-case-2026",
        issuer_name="Acme",
        question="How effective is Acme's governance?",
        theme="governance",
        reference_date=date(2026, 8, 14),
    )
    store.open_case(request)
    return store, store.start_run(request.case_key, request.reference_date).run_id


def valid_plan_payload(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "issuer": "Acme",
        "question": "How effective is Acme's governance?",
        "theme": "governance",
        "reference_date": "2026-08-14",
        "queries": [
            {
                "query_id": "Q-001",
                "query": "Acme governance annual report",
                "bucket": "primary",
            }
        ],
        "coverage": {
            "primary": {"status": "planned"},
            "public_authority": {"status": "planned"},
            "independent_recent": {"status": "planned"},
            "counter_evidence": {"status": "planned"},
        },
        "query_budget": 12,
        "lead_budget": 50,
        "capture_budget": 10,
        "issues": [
            {
                "issue_id": "I-001",
                "topic": "Board oversight",
                "research_question": "Is oversight adequate?",
                "materiality": "Oversight informs accountability.",
                "status": "planned",
                "historical_status": "planned",
            }
        ],
    }


def test_plan_requires_all_coverage_buckets_and_round_trips(tmp_path: Path) -> None:
    store, run_id = opened_run(tmp_path)
    plan_type = getattr(domain_models, "ResearchPlan", None)
    assert plan_type is not None
    plan = plan_type.model_validate(valid_plan_payload(run_id))

    assert store.save_research_plan(run_id, plan).name == "research-plan.json"
    assert CaseStore(tmp_path).load_research_plan(run_id) == plan


def test_plan_rejects_missing_bucket_and_unexplained_unavailability(tmp_path: Path) -> None:
    _, run_id = opened_run(tmp_path)
    plan_type = getattr(domain_models, "ResearchPlan", None)
    assert plan_type is not None
    missing = valid_plan_payload(run_id)
    del missing["coverage"]["counter_evidence"]  # type: ignore[index]
    with pytest.raises(ValidationError):
        plan_type.model_validate(missing)

    unavailable = valid_plan_payload(run_id)
    unavailable["coverage"]["public_authority"] = {  # type: ignore[index]
        "status": "unavailable"
    }
    with pytest.raises(ValidationError):
        plan_type.model_validate(unavailable)


def test_satisfied_issue_requires_counter_evidence_or_an_explained_exception(
    tmp_path: Path,
) -> None:
    _, run_id = opened_run(tmp_path)
    payload = valid_plan_payload(run_id)
    issue = payload["issues"][0]  # type: ignore[index]
    issue.update(  # type: ignore[union-attr]
        {
            "status": "satisfied",
            "source_ids": ["S-0001"],
            "historical_status": "satisfied",
            "periods": ["2024", "2025", "2026"],
        }
    )

    with pytest.raises(ValidationError, match="counter-evidence"):
        domain_models.ResearchPlan.model_validate(payload)

    issue["explanation"] = "No eligible counter-evidence was captured in this bounded run."  # type: ignore[index]
    assert domain_models.ResearchPlan.model_validate(payload).issues[0].status == "satisfied"


def test_satisfied_issue_rejects_unresolved_historical_coverage(tmp_path: Path) -> None:
    _, run_id = opened_run(tmp_path)
    payload = valid_plan_payload(run_id)
    issue = payload["issues"][0]  # type: ignore[index]
    issue.update(  # type: ignore[union-attr]
        {
            "status": "satisfied",
            "source_ids": ["S-0001"],
            "counter_source_ids": ["S-0002"],
            "historical_status": "planned",
        }
    )

    with pytest.raises(ValidationError, match="historical coverage"):
        domain_models.ResearchPlan.model_validate(payload)


def test_plan_rejects_wrong_run_binding(tmp_path: Path) -> None:
    store, run_id = opened_run(tmp_path)
    plan_type = getattr(domain_models, "ResearchPlan", None)
    assert plan_type is not None
    plan = plan_type.model_validate(valid_plan_payload("other-case-2026:0001"))

    with pytest.raises(InvalidRequest, match="run_id"):
        store.save_research_plan(run_id, plan)


def test_plan_rejects_case_metadata_mismatch(tmp_path: Path) -> None:
    store, run_id = opened_run(tmp_path)
    payload = valid_plan_payload(run_id)
    payload["issuer"] = "Different Issuer"
    plan = domain_models.ResearchPlan.model_validate(payload)

    with pytest.raises(InvalidRequest, match="issuer, question, theme, and reference date"):
        store.save_research_plan(run_id, plan)
