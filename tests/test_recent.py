from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).parents[1]
VENDOR = PROJECT_ROOT / "third_party" / "last30days"
RAW_JSON = json.dumps(
    {
        "items_by_source": {
            "reddit": [
                {
                    "item_id": "R1",
                    "source": "reddit",
                    "title": "Governance discussion",
                    "body": "A public discussion",
                    "url": "https://example.test/item",
                    "published_at": "2026-08-13T12:00:00Z",
                    "engagement": {"score": 42, "comments": 3},
                    "snippet": "Discussion excerpt",
                    "why_relevant": "Mentions Acme governance",
                },
                {
                    "item_id": "R2",
                    "source": "reddit",
                    "title": "Local target",
                    "body": "Must be rejected",
                    "url": "http://127.0.0.1/private",
                },
            ]
        },
        "errors_by_source": {"github": "rate limited"},
    }
)


def recent_module() -> Any:
    spec = importlib.util.find_spec("srd.recent")
    assert spec is not None
    return importlib.import_module("srd.recent")


def test_recent_discovery_uses_fixed_keyless_isolated_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    calls: list[dict[str, object]] = []

    def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append({"args": args, **kwargs})
        return subprocess.CompletedProcess(args, 0, stdout=RAW_JSON, stderr="")

    module = recent_module()
    result = module.discover_recent(
        VENDOR,
        "Acme governance",
        date(2026, 8, 14),
        runner=runner,
    )

    call = calls[0]
    args = call["args"]
    assert isinstance(args, list)
    assert call["shell"] is False
    assert "--emit=json" in args
    assert "--json-profile=raw" in args
    assert "--search=reddit,hackernews,github" in args
    assert "--no-browser-cookies" in args
    assert "--days=30" in args
    assert "--as-of=2026-08-14" in args
    assert "--max-results=50" in args
    assert "--max-source-fetches=10" in args
    env = call["env"]
    assert isinstance(env, dict)
    assert set(env) == {
        "HOME",
        "XDG_CONFIG_HOME",
        "TMPDIR",
        "PATH",
        "PYTHONUTF8",
        "PYTHONDONTWRITEBYTECODE",
        "LC_ALL",
    }
    assert "OPENAI_API_KEY" not in env
    assert [str(lead.url) for lead in result.leads] == ["https://example.test/item"]
    assert result.failures == ["github: rate limited"]


@pytest.mark.parametrize(
    ("stdout", "error_name"),
    [
        pytest.param("not-json", "DiscoveryOutputInvalid", id="invalid-json"),
        pytest.param(
            "x" * (5 * 1024 * 1024 + 1),
            "DiscoveryOutputTooLarge",
            id="oversized",
        ),
    ],
)
def test_recent_discovery_rejects_invalid_or_oversized_output(stdout: str, error_name: str) -> None:
    def runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    module = recent_module()
    error_type = getattr(importlib.import_module("srd.errors"), error_name)
    with pytest.raises(error_type):
        module.discover_recent(VENDOR, "Acme", date(2026, 8, 14), runner=runner)


def test_recent_discovery_maps_timeout_to_named_error() -> None:
    def runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(args, 90)

    module = recent_module()
    error_type = importlib.import_module("srd.errors").DiscoveryTimeout
    with pytest.raises(error_type):
        module.discover_recent(VENDOR, "Acme", date(2026, 8, 14), runner=runner)
