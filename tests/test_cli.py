from typer.testing import CliRunner

from srd.cli import app


def test_version_is_reported() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "srd 0.1.0"


def test_doctor_reports_python_312() -> None:
    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert result.stdout.startswith("srd doctor: ok (Python 3.12; Scrapling")
