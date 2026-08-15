import hashlib
import json
from pathlib import Path

import pytest

from srd.cli import run_fixture_demo

FIXTURES = Path(__file__).parent / "fixtures"


def test_fixture_demo_uses_frozen_metadata_and_never_uses_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def network_forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("fixture demo must not create an HTTP client")

    monkeypatch.setattr("srd.collection.httpx.AsyncClient", network_forbidden)
    for fixture in ("case_001", "case_002"):
        for source in json.loads((FIXTURES / fixture / "sources.json").read_text()):
            text = (FIXTURES / fixture / source["text_file"]).read_text()
            assert source["captured_at"]
            assert source["content_sha256"] == hashlib.sha256(text.encode()).hexdigest()

    first_brief, delta = run_fixture_demo(tmp_path)

    first_text = first_brief.read_text()
    later_text = (delta.parent / "brief.md").read_text()
    delta_text = delta.read_text()
    delta_data = json.loads(delta.with_suffix(".json").read_text())
    combined = f"{first_text}\n{later_text}\n{delta_text}"

    assert "Environmental, Social, and Public Policy Committee" in first_text
    assert "public disclosure does not establish operating effectiveness" in first_text.lower()
    assert "> [S-" in first_text
    assert "## Withdrawn" in delta_text
    assert all(delta_data[key] for key in ("added", "withdrawn", "superseded", "unchanged"))
    assert "investment recommendation" not in combined.lower()
    assert "engagement recommendation" not in combined.lower()
    assert "voting recommendation" not in combined.lower()
