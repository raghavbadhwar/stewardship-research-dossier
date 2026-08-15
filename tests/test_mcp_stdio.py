import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).parents[1]


def test_mcp_stdio_initializes_lists_tools_and_rejects_path_traversal(tmp_path: Path) -> None:
    async def exercise() -> None:
        parameters = StdioServerParameters(
            command="uv",
            args=["run", "--locked", "srd-mcp"],
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "SRD_ROOT": str(tmp_path)},
        )
        async with stdio_client(parameters) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            by_name = {tool.name: tool for tool in listed.tools}
            assert {
                "case_open",
                "source_collect",
                "collection_finish",
                "run_inspect",
                "source_read",
                "packet_diagnostics",
                "source_import_rendered",
                "filing_ingest",
                "lead_import",
                "research_plan_save",
                "recent_discover",
                "delegation_plan",
                "handoff_save",
                "packet_draft_save",
                "packet_draft_read",
                "packet_approve",
                "brief_render",
                "case_compare",
                "case_export",
            } == set(by_name)
            assert "agent_memory_list" not in by_name
            assert "agent_memory_save" not in by_name
            assert "rendered_fallback" not in by_name["source_collect"].inputSchema["properties"]
            opened = await session.call_tool(
                "case_open",
                {
                    "payload": {
                        "case_key": "stdio-case-2026",
                        "issuer_name": "Example Public Issuer",
                        "question": "Does this evidence merit review?",
                        "theme": "governance",
                        "reference_date": "2026-08-14",
                    }
                },
            )
            assert json.loads(opened.content[0].text)["ok"] is True
            opened_data = json.loads(opened.content[0].text)["data"]
            captured = await session.call_tool(
                "source_collect",
                {"run_id": opened_data["run_id"], "urls": ["http://127.0.0.1/blocked"]},
            )
            capture_payload = json.loads(captured.content[0].text)
            assert capture_payload["ok"] is True
            assert capture_payload["data"][0]["error"] == {
                "code": "SOURCE_UNAVAILABLE",
                "message": "Private network targets are not allowed.",
                "url": "http://127.0.0.1/blocked",
            }
            inspected = await session.call_tool("run_inspect", {"run_id": opened_data["run_id"]})
            assert json.loads(inspected.content[0].text)["ok"] is True
            missing = await session.call_tool(
                "source_read",
                {"run_id": opened_data["run_id"], "source_id": "S-9999", "limit": 1},
            )
            assert json.loads(missing.content[0].text)["error"]["code"] == "PACKET_SOURCE_MISMATCH"
            rejected = await session.call_tool(
                "brief_render", {"run_id": "stdio-case-2026:../../escape"}
            )
            assert json.loads(rejected.content[0].text)["error"]["code"] == "INVALID_REQUEST"

    asyncio.run(exercise())
