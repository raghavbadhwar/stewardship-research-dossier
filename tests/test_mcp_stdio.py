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
            tools = await session.list_tools()
            assert {
                "case_open",
                "source_collect",
                "filing_ingest",
                "delegation_plan",
                "handoff_save",
                "packet_save",
                "brief_render",
                "case_compare",
                "case_export",
            } <= {tool.name for tool in tools.tools}
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
            rejected = await session.call_tool(
                "brief_render", {"run_id": "stdio-case-2026:../../escape"}
            )
            assert json.loads(rejected.content[0].text)["error"]["code"] == "INVALID_REQUEST"

    asyncio.run(exercise())
