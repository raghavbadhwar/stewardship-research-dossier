from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from srd.cli import app
from srd.models import CaseOpenRequest
from srd.store import CaseStore


def test_version_is_reported() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "srd 0.3.3"


def test_doctor_reports_python_312() -> None:
    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert result.stdout == "srd doctor: ok (Python 3.12)\n"


def test_export_rejects_case_descendant_and_allows_sibling(tmp_path: Path) -> None:
    case_key = "export-case-2026"
    store = CaseStore(tmp_path)
    store.open_case(
        CaseOpenRequest(
            case_key=case_key,
            issuer_name="Acme",
            question="Q?",
            theme="governance",
            reference_date=date(2026, 8, 14),
        )
    )
    runner = CliRunner()
    nested = store.case_path(case_key) / "nested"
    rejected = runner.invoke(app, ["export", case_key, str(nested), "--root", str(tmp_path)])
    assert rejected.exit_code != 0
    assert not nested.exists()

    sibling = tmp_path / "exported-case"
    exported = runner.invoke(app, ["export", case_key, str(sibling), "--root", str(tmp_path)])
    assert exported.exit_code == 0
    assert (sibling / "dossier.sqlite").exists()
