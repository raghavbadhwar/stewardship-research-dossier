import json
import tomllib
from pathlib import Path

from srd import __version__


def test_plugin_manifests_are_consistent() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text())
    codex = json.loads(Path(".codex-plugin/plugin.json").read_text())
    claude = json.loads(Path(".claude-plugin/plugin.json").read_text())
    market = json.loads(Path(".agents/plugins/marketplace.json").read_text())
    assert codex["name"] == claude["name"] == "stewardship-research-dossier"
    assert {
        project["project"]["version"],
        codex["version"],
        claude["version"],
        __version__,
    } == {"0.3.3"}
    assert codex["mcpServers"] == "./.mcp.json"
    assert market["name"] == "stewardship-research-dossier-local"
    source = market["plugins"][0]["source"]
    assert source["source"] == "local"
    assert (Path.cwd() / source["path"]).resolve() == Path.cwd()
    skill = Path("skills/living-research/SKILL.md").read_text()
    assert "## Adaptive intake" in skill
    assert "Apply a sufficiency gate before `case_open`. Start immediately" in skill
    assert (
        "Do not open a case, search, call\n`recent_discover`, or collect sources while such a question is pending."
        in skill
    )


def test_living_research_uses_bounded_scrapling_fallback() -> None:
    skill = Path("skills/living-research/SKILL.md").read_text()
    normalized = " ".join(skill.split())
    assert "Scrapling" in skill
    assert "Call `source_collect` first" in skill
    assert "call `source_import_rendered`" in skill
    assert (
        "Do not exhaust the capture ceiling before trying eligible rendered fallbacks" in normalized
    )
    assert "Never use `stealthy_fetch`" in skill
    assert "authentication, paywalls, robots restrictions, or access controls" in normalized


def test_worker_cards_cannot_spawn_workers() -> None:
    for card in Path("agents").glob("*.md"):
        text = card.read_text()
        assert "Agent" not in text.split("---", 2)[1].split("tools:", 1)[1].splitlines()[0]
        assert "WorkerHandoff" in text


def test_worker_cards_are_role_specific_and_source_bound() -> None:
    expected_focus = {
        "competitive-analyst": "competitive context",
        "delta-analyst": "evidence changes",
        "event-scout": "dated events",
        "filings-analyst": "formal disclosures",
        "governance-analyst": "governance mechanisms",
        "outlier-mind": "falsifiable hypotheses",
        "polymath": "cross-domain connections",
        "thesis-skeptic": "disconfirming evidence",
    }
    for role, focus in expected_focus.items():
        text = (Path("agents") / f"{role}.md").read_text()
        frontmatter = text.split("---", 2)[1]
        assert "tools: Read" in frontmatter
        assert "Search" not in frontmatter
        assert focus in text
        assert "## Input contract" in text
        assert "## Working personality" in text
        assert "## Procedural memory" not in text
        assert "## Output contract" in text
        assert f'"role": "{role}"' in text
        assert '"finding_id"' in text
        assert '"contradicts"' in text
        assert "provisional" in text
        assert "only the supplied source IDs" in text
        assert "JSON object and no prose" in text
        assert "candidate_lessons" not in text
