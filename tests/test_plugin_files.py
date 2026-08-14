import json
from pathlib import Path


def test_plugin_manifests_are_consistent() -> None:
    codex = json.loads(Path(".codex-plugin/plugin.json").read_text())
    claude = json.loads(Path(".claude-plugin/plugin.json").read_text())
    market = json.loads(Path(".agents/plugins/marketplace.json").read_text())
    assert codex["name"] == claude["name"] == "stewardship-research-dossier"
    assert codex["mcpServers"] == "./.mcp.json"
    assert market["name"] == "stewardship-research-dossier-local"
    source = market["plugins"][0]["source"]
    assert source["source"] == "local"
    assert (Path(".agents/plugins") / source["path"]).resolve() == Path.cwd()


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
        assert "## Output contract" in text
        assert f'"role": "{role}"' in text
        assert "only the supplied source IDs" in text
        assert "JSON object and no prose" in text
