from pathlib import Path

from srd.mcp_server import create_server
from srd.store import CaseStore


def tool(server: object, name: str):
    return server._tool_manager.get_tool(name).fn  # type: ignore[attr-defined,no-any-return]


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
    store.transition(run_id, "SYNTHESIS_PENDING")
    payload = {
        "thesis": [
            {"statement": "Claim", "source_ids": [source.source_id], "confidence": "medium"}
        ],
        "counter_view": [
            {"statement": "Counter", "source_ids": [source.source_id], "confidence": "low"}
        ],
        "risks": [{"statement": "Risk", "source_ids": [source.source_id], "confidence": "low"}],
        "open_questions": ["Question?"],
    }
    saved = tool(server, "packet_save")(run_id, payload, "Review it.")
    assert saved["ok"] is True
    rendered = tool(server, "brief_render")(run_id)
    assert rendered["ok"] is True and Path(rendered["data"]["path"]).exists()


def test_mcp_invalid_packet_has_named_error(tmp_path: Path) -> None:
    server = create_server(tmp_path)
    result = tool(server, "packet_save")("missing:0001", {}, "Review")
    assert result["ok"] is False and result["error"]["code"] == "PACKET_INCOMPLETE"
