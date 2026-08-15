import json
from datetime import date
from pathlib import Path

import pytest

from srd.errors import InvalidRequest
from srd.models import CaseOpenRequest, LeadCandidate, ResearchPlan
from srd.store import CaseStore


def test_leads_append_deduplicate_and_remain_untrusted_not_sources(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    request = CaseOpenRequest(
        case_key="lead-case-2026",
        issuer_name="Acme",
        question="Q?",
        theme="event",
        reference_date=date(2026, 8, 14),
    )
    store.open_case(request)
    run = store.start_run(request.case_key, request.reference_date)
    first = store.import_leads(
        run.run_id,
        [
            LeadCandidate(
                url="https://example.test/lead",
                title="Lead",
                summary="Untrusted discovery output",
                origin="last30days",
                discovery_query="Acme governance",
                discovery_lane="recent",
                source_type="community",
            )
        ],
    )
    second = store.import_leads(
        run.run_id,
        [
            LeadCandidate(
                url="https://EXAMPLE.test/lead#discussion",
                title="Duplicate lead",
                summary="Same canonical URL",
                origin="host_search",
            )
        ],
    )

    payload = json.loads((store.run_path(run.run_id) / "leads.json").read_text())
    assert payload["untrusted"] is True
    assert first[0].lead_id == "L-0001"
    assert second[0].lead_id == "L-0001"
    assert len(store.list_leads(run.run_id)) == 1
    assert store.list_leads(run.run_id)[0].discovery_query == "Acme governance"
    assert store.list_sources(run.run_id) == []


def test_lead_import_enforces_the_saved_plan_budget(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    request = CaseOpenRequest(
        case_key="lead-budget-2026",
        issuer_name="Acme",
        question="Q?",
        theme="event",
        reference_date=date(2026, 8, 14),
    )
    store.open_case(request)
    run = store.start_run(request.case_key, request.reference_date)
    store.save_research_plan(
        run.run_id,
        ResearchPlan.model_validate(
            {
                "run_id": run.run_id,
                "issuer": "Acme",
                "question": "Q?",
                "theme": "event",
                "reference_date": "2026-08-14",
                "queries": [],
                "coverage": {
                    "primary": {"status": "planned"},
                    "public_authority": {"status": "planned"},
                    "independent_recent": {"status": "planned"},
                    "counter_evidence": {"status": "planned"},
                },
                "query_budget": 1,
                "lead_budget": 1,
                "capture_budget": 1,
                "issues": [
                    {
                        "issue_id": "I-001",
                        "topic": "Event oversight",
                        "research_question": "What requires review?",
                        "materiality": "The event may affect governance.",
                        "status": "planned",
                        "historical_status": "planned",
                    }
                ],
            }
        ),
    )
    store.import_leads(
        run.run_id,
        [
            LeadCandidate(
                url="https://example.test/one",
                title="One",
                summary="First lead",
                origin="host_search",
            )
        ],
    )

    with pytest.raises(InvalidRequest, match="lead budget"):
        store.import_leads(
            run.run_id,
            [
                LeadCandidate(
                    url="https://example.test/two",
                    title="Two",
                    summary="Second lead",
                    origin="host_search",
                )
            ],
        )
