import json
import logging
import subprocess
from pathlib import Path

from srd.cli import run_fixture_demo
from srd.mcp_server import _error, create_server
from srd.store import CaseStore


def tool(server: object, name: str):
    return server._tool_manager.get_tool(name).fn  # type: ignore[attr-defined,no-any-return]


def plan_payload(run_id: str, source_id: str | None = None) -> dict[str, object]:
    primary = (
        {"status": "satisfied", "source_ids": [source_id]} if source_id else {"status": "planned"}
    )
    return {
        "run_id": run_id,
        "issuer": "Acme",
        "question": "Q?",
        "theme": "governance",
        "reference_date": "2026-08-14",
        "queries": [
            {"query_id": "Q-001", "query": "Acme evidence", "bucket": "primary"},
            {
                "query_id": "Q-002",
                "query": "Acme counter evidence",
                "bucket": "counter_evidence",
            },
        ],
        "coverage": {
            "primary": primary,
            "public_authority": {
                "status": "unavailable",
                "explanation": "No authority source found.",
            },
            "independent_recent": {
                "status": "unavailable",
                "explanation": "No independent source found.",
            },
            "counter_evidence": {
                "status": "unavailable",
                "explanation": "No contrary evidence found.",
            },
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


def test_mcp_case_open_packet_and_render(tmp_path: Path) -> None:
    server = create_server(tmp_path)
    opened = tool(server, "case_open")(
        {
            "case_key": "mcp-case-2026",
            "issuer_name": "Acme",
            "question": "Q?",
            "theme": "governance",
            "reference_date": "2026-08-14",
        }
    )
    assert opened["ok"] is True
    run_id = opened["data"]["run_id"]
    store = CaseStore(tmp_path)
    store.transition(run_id, "COLLECTING")
    source = store.add_source(
        run_id,
        url="https://example.test/a",
        title="A",
        publisher=None,
        retrieval_method="static",
        text="evidence",
    )
    planned = tool(server, "research_plan_save")(run_id, plan_payload(run_id, source.source_id))
    assert planned["ok"] is True
    store.transition(run_id, "SYNTHESIS_PENDING")
    payload = {
        "thesis": [
            {
                "finding_id": "T-001",
                "statement": "Claim",
                "citations": [
                    {"source_id": source.source_id, "locator": "Evidence", "excerpt": "evidence"}
                ],
                "confidence": "medium",
            }
        ],
        "counter_view": [
            {
                "finding_id": "C-001",
                "statement": "Counter",
                "citations": [
                    {"source_id": source.source_id, "locator": "Evidence", "excerpt": "evidence"}
                ],
                "confidence": "low",
                "contradicts": ["T-001"],
            }
        ],
        "risks": [
            {
                "finding_id": "R-001",
                "statement": "Risk",
                "citations": [
                    {"source_id": source.source_id, "locator": "Evidence", "excerpt": "evidence"}
                ],
                "confidence": "low",
            }
        ],
        "open_questions": ["Question?"],
        "assessment_status": "inconclusive",
        "evidence_gaps": ["primary:planned", "public_authority:planned"],
    }
    saved = tool(server, "packet_draft_save")(run_id, payload, "Review it.")
    assert saved["ok"] is True
    draft = tool(server, "packet_draft_read")(run_id)
    assert draft["data"]["packet"]["thesis"][0]["statement"] == "Claim"
    assert draft["data"]["packet"]["analyst_review_required"] is True
    blocked = tool(server, "brief_render")(run_id)
    assert blocked["error"]["code"] == "PACKET_NOT_APPROVED"
    approved = tool(server, "packet_approve")(
        run_id,
        "analyst",
        "Accepted named evidence gaps for this local test.",
        True,
    )
    assert approved["ok"] is True
    rendered = tool(server, "brief_render")(run_id)
    assert rendered["ok"] is True and Path(rendered["data"]["path"]).exists()


def test_mcp_invalid_packet_has_named_error(tmp_path: Path) -> None:
    server = create_server(tmp_path)
    result = tool(server, "packet_draft_save")("missing:0001", {}, "Review")
    assert result["ok"] is False and result["error"]["code"] == "PACKET_INCOMPLETE"

    invalid_run = tool(server, "packet_draft_save")("../bad", {}, "Review")
    assert invalid_run["ok"] is False
    assert invalid_run["error"]["code"] == "INVALID_REQUEST"


def test_unexpected_mcp_error_is_logged_and_redacted(caplog) -> None:
    with caplog.at_level(logging.ERROR, logger="srd.mcp_server"):
        result = _error(RuntimeError("boom"))

    assert result == {
        "ok": False,
        "error": {"code": "INTERNAL_ERROR", "message": "Unexpected internal error."},
    }
    assert "boom" in caplog.text


def test_leads_cannot_change_a_blocked_run(tmp_path: Path) -> None:
    server = create_server(tmp_path)
    opened = tool(server, "case_open")(
        {
            "case_key": "blocked-case-2026",
            "issuer_name": "Acme",
            "question": "Q?",
            "theme": "governance",
            "reference_date": "2026-08-14",
        }
    )
    run_id = opened["data"]["run_id"]
    CaseStore(tmp_path).transition(run_id, "BLOCKED")

    result = tool(server, "lead_import")(
        run_id,
        [
            {
                "url": "https://example.test/lead",
                "title": "Lead",
                "summary": "Untrusted lead",
                "origin": "host_search",
            }
        ],
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_collection_finish_rejects_invalid_state(tmp_path: Path) -> None:
    server = create_server(tmp_path)
    opened = tool(server, "case_open")(
        {
            "case_key": "finish-case-2026",
            "issuer_name": "Acme",
            "question": "Q?",
            "theme": "governance",
            "reference_date": "2026-08-14",
        }
    )
    run_id = opened["data"]["run_id"]

    first = tool(server, "collection_finish")(run_id)

    assert first["ok"] is False
    assert first["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_run_inspect_and_source_read_are_bounded(tmp_path: Path) -> None:
    server = create_server(tmp_path)
    opened = tool(server, "case_open")(
        {
            "case_key": "resume-case-2026",
            "issuer_name": "Acme",
            "question": "Q?",
            "theme": "governance",
            "reference_date": "2026-08-14",
        }
    )
    run_id = opened["data"]["run_id"]
    store = CaseStore(tmp_path)
    store.begin_collection(run_id)
    source = store.add_source(
        run_id,
        url="https://example.test/long-evidence",
        title="Long evidence",
        publisher="Example",
        retrieval_method="static",
        text="x" * 25_000,
    )

    inspected = tool(server, "run_inspect")(run_id)
    first = tool(server, "source_read")(run_id, source.source_id, 0, 20_000)

    assert inspected["ok"] is True
    assert "text" not in inspected["data"]["sources"][0]
    assert inspected["data"]["research"]["lead_count"] == 0
    assert inspected["data"]["research"]["draft"] is None
    assert first["ok"] is True
    assert len(first["data"]["text"]) == 20_000
    for offset, limit in [(-1, 1), (0, 0), (0, 20_001), (25_001, 1)]:
        rejected = tool(server, "source_read")(run_id, source.source_id, offset, limit)
        assert rejected["error"]["code"] == "INVALID_REQUEST"
    wrong_source = tool(server, "source_read")(run_id, "S-9999", 0, 1)
    assert wrong_source["error"]["code"] == "PACKET_SOURCE_MISMATCH"
    traversal = tool(server, "source_read")("../bad", source.source_id, 0, 1)
    assert traversal["error"]["code"] == "INVALID_REQUEST"


def test_packet_diagnostics_matches_saved_packet(tmp_path: Path) -> None:
    run_fixture_demo(tmp_path)

    result = tool(create_server(tmp_path), "packet_diagnostics")("fixture-governance-2026:0001")

    assert result["ok"] is True
    assert result["data"]["captured_source_count"] == 3
    assert "score" not in result["data"]
    assert "recommendation" not in result["data"]


def test_rendered_import_validates_metadata(tmp_path: Path) -> None:
    server = create_server(tmp_path / "cases")
    opened = tool(server, "case_open")(
        {
            "case_key": "rendered-case-2026",
            "issuer_name": "Acme",
            "question": "Q?",
            "theme": "governance",
            "reference_date": "2026-08-14",
        }
    )
    path = tmp_path / "rendered.txt"
    path.write_text("Evidence", encoding="utf-8")

    result = tool(server, "source_import_rendered")(
        opened["data"]["run_id"],
        str(path),
        {
            "url": "file:///tmp/not-public",
            "title": "Rendered evidence",
            "captured_at": "2026-08-14T09:00:00Z",
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_REQUEST"
    assert CaseStore(tmp_path / "cases").get_run(opened["data"]["run_id"]).state == "OPEN"


def test_recent_discover_persists_typed_leads_and_bounded_status(tmp_path: Path) -> None:
    raw = json.dumps(
        {
            "items_by_source": {
                "hackernews": [
                    {
                        "item_id": "HN1",
                        "source": "hackernews",
                        "title": "Acme discussion",
                        "body": "Recent discussion",
                        "url": "https://news.example/item",
                    }
                ]
            },
            "errors_by_source": {},
        }
    )

    def runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout=raw, stderr="")

    server = create_server(tmp_path, recent_runner=runner)
    opened = tool(server, "case_open")(
        {
            "case_key": "recent-case-2026",
            "issuer_name": "Acme",
            "question": "Q?",
            "theme": "governance",
            "reference_date": "2026-08-14",
        }
    )
    run_id = opened["data"]["run_id"]
    assert tool(server, "research_plan_save")(run_id, plan_payload(run_id))["ok"] is True

    discovered = tool(server, "recent_discover")(run_id, "Acme governance", "2026-08-14", 30)
    inspected = tool(server, "run_inspect")(run_id)

    assert discovered["ok"] is True
    assert discovered["data"]["lead_ids"] == ["L-0001"]
    assert inspected["data"]["research"]["lead_count"] == 1
    assert inspected["data"]["research"]["recent_discovery"]["lead_ids"] == ["L-0001"]
