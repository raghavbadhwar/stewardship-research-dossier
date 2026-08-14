import json
from datetime import date
from pathlib import Path

from srd.models import CaseOpenRequest, LeadCandidate
from srd.store import CaseStore


def test_last30days_leads_are_persisted_as_untrusted_not_sources(tmp_path: Path) -> None:
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
    path = store.import_leads(
        run.run_id,
        [
            LeadCandidate(
                url="https://example.test/lead",
                title="Lead",
                summary="Untrusted discovery output",
                origin="last30days",
            )
        ],
    )
    assert json.loads(path.read_text())["untrusted"] is True
    assert store.list_sources(run.run_id) == []
