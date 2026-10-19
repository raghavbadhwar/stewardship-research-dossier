"""Isolated adapter for the vendored Last30Days keyless discovery lane."""

from __future__ import annotations

import ipaddress
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .errors import (
    DiscoveryOutputInvalid,
    DiscoveryOutputTooLarge,
    DiscoveryTimeout,
    DiscoveryUnavailable,
    InvalidRequest,
)
from .models import LeadCandidate, RecentDiscoveryResult

ALLOWED_SOURCES = ("reddit", "hackernews", "github")
MAX_STDOUT_BYTES = 5 * 1024 * 1024
MAX_STDERR_BYTES = 256 * 1024
TIMEOUT_SECONDS = 90
Runner = Callable[..., subprocess.CompletedProcess[str]]


def _public_http_url(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    hostname = parsed.hostname.casefold()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        return None
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return raw
    return (
        raw if address.is_global and not address.is_multicast and not address.is_reserved else None
    )


def _published_at(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _engagement(item: dict[str, Any]) -> dict[str, int | float | str]:
    raw = item.get("engagement")
    values = raw if isinstance(raw, dict) else {}
    for key in ("score", "num_comments", "points", "comments", "stars", "forks"):
        value = item.get(key)
        if isinstance(value, (int, float, str)) and not isinstance(value, bool):
            values.setdefault(key, value)
    return {
        str(key)[:80]: value
        for key, value in list(values.items())[:20]
        if isinstance(value, (int, float, str)) and not isinstance(value, bool)
    }


def _parse_result(stdout: str) -> RecentDiscoveryResult:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise DiscoveryOutputInvalid() from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("items_by_source"), dict):
        raise DiscoveryOutputInvalid()

    leads: list[LeadCandidate] = []
    items_by_source = payload["items_by_source"]
    for source in ALLOWED_SOURCES:
        items = items_by_source.get(source, [])
        if not isinstance(items, list):
            raise DiscoveryOutputInvalid()
        for item in items[:50]:
            if not isinstance(item, dict):
                continue
            url = _public_http_url(item.get("url"))
            title = item.get("title")
            if url is None or not isinstance(title, str) or not title.strip():
                continue
            raw_summary = item.get("snippet") or item.get("body") or title
            summary = str(raw_summary).strip()[:2_000]
            if not summary:
                continue
            leads.append(
                LeadCandidate(
                    url=url,  # type: ignore[arg-type]
                    title=title.strip()[:500],
                    summary=summary,
                    origin="last30days",
                    discovery_lane="recent",
                    source_type="developer" if source == "github" else "community",
                    published_at=_published_at(item.get("published_at")),
                    snippet=str(item.get("snippet") or "").strip()[:2_000] or None,
                    engagement=_engagement(item),
                    relevance_rationale=str(item.get("why_relevant") or "").strip()[:1_000] or None,
                )
            )

    errors = payload.get("errors_by_source")
    failures = []
    if isinstance(errors, dict):
        failures = [
            f"{source}: {str(errors[source])[:500]}"
            for source in ALLOWED_SOURCES
            if errors.get(source)
        ]
    return RecentDiscoveryResult(leads=leads, failures=failures)


def discover_recent(
    vendor_root: Path,
    topic: str,
    as_of: date,
    days: int = 30,
    *,
    runner: Runner | None = None,
) -> RecentDiscoveryResult:
    """Run the fixed keyless Last30Days profile and return untrusted lead records."""
    topic = topic.strip()
    if not topic or len(topic) > 500:
        raise InvalidRequest("topic must contain between 1 and 500 characters.")
    if not 1 <= days <= 30:
        raise InvalidRequest("days must be between 1 and 30.")
    engine = (
        vendor_root.expanduser().resolve() / "skills" / "last30days" / "scripts" / "last30days.py"
    )
    if not engine.is_file():
        raise DiscoveryUnavailable("Vendored recent-discovery engine is unavailable.")

    execute = runner or subprocess.run
    with tempfile.TemporaryDirectory(prefix="srd-recent-") as temporary:
        root = Path(temporary)
        home = root / "home"
        config = root / "config"
        output = root / "output"
        binaries = root / "bin"
        for directory in (home, config, output, binaries):
            directory.mkdir()
        args = [
            sys.executable,
            str(engine),
            topic,
            "--emit=json",
            "--json-profile=raw",
            "--search=reddit,hackernews,github",
            "--no-browser-cookies",
            "--no-verify-freshness",
            "--web-backend=keyless",
            f"--days={days}",
            f"--as-of={as_of.isoformat()}",
            "--max-results=50",
            "--max-source-fetches=10",
            f"--save-dir={output}",
        ]
        environment = {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(config),
            "TMPDIR": str(root),
            "PATH": str(binaries),
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LC_ALL": "C.UTF-8",
        }
        try:
            completed = execute(
                args,
                cwd=str(root),
                env=environment,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DiscoveryTimeout() from exc
        if (
            len(completed.stdout.encode()) > MAX_STDOUT_BYTES
            or len(completed.stderr.encode()) > MAX_STDERR_BYTES
        ):
            raise DiscoveryOutputTooLarge()
        if completed.returncode != 0:
            raise DiscoveryUnavailable(
                f"Recent-discovery engine exited with status {completed.returncode}."
            )
        return _parse_result(completed.stdout)
