from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from .collection import collect_rendered_source, collect_sources
from .delegation import plan_delegation
from .delta import compare_runs
from .errors import InvalidRequest, PacketIncomplete, SrdError
from .models import (
    CaseOpenRequest,
    DelegationRequest,
    LeadCandidate,
    ResearchPacket,
    WorkerHandoff,
    validate_case_key,
    validate_run_id,
)
from .packets import render_brief, save_packet
from .pdfs import ingest_pdf_path
from .store import CaseStore

ROOT = Path.home() / ".stewardship-research-dossier" / "cases"


def _ok(data: object) -> dict[str, object]:
    return {"ok": True, "data": data}


def _error(exc: Exception) -> dict[str, object]:
    if isinstance(exc, ValidationError):
        exc = InvalidRequest("Invalid tool input.")
    if isinstance(exc, SrdError):
        e = {"code": exc.code, "message": exc.message}
        if exc.url:
            e["url"] = exc.url
        return {"ok": False, "error": e}
    return {
        "ok": False,
        "error": {"code": "INTERNAL_ERROR", "message": "Unexpected internal error."},
    }


def create_server(root: Path = ROOT) -> FastMCP:
    mcp = FastMCP("stewardship-research-dossier")

    @mcp.tool()
    def case_open(payload: dict[str, object]) -> dict[str, object]:
        try:
            req = CaseOpenRequest.model_validate(payload)
            store = CaseStore(root)
            case = store.open_case(req)
            run = store.start_run(case.case_key, req.reference_date)
            return _ok({"case_key": case.case_key, "run_id": run.run_id})
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def source_collect(
        run_id: str, urls: list[str], rendered_fallback: bool = False
    ) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            store = CaseStore(root)
            results = collect_sources(store, run_id, urls)
            if rendered_fallback:
                results = [
                    collect_rendered_source(store, run_id, result.url)
                    if result.source is None
                    else result
                    for result in results
                ]
            return _ok(
                [
                    {
                        "url": r.url,
                        "source": r.source.model_dump(mode="json") if r.source else None,
                        "error": r.error.code if r.error else None,
                    }
                    for r in results
                ]
            )
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def filing_ingest(run_id: str, path: str) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            return _ok(ingest_pdf_path(CaseStore(root), run_id, Path(path)).model_dump(mode="json"))
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def lead_import(run_id: str, leads: list[dict[str, object]]) -> dict[str, object]:
        """Store Last30Days/host-discovery output as untrusted capture leads."""
        try:
            run_id = validate_run_id(run_id)
            parsed = [LeadCandidate.model_validate(lead) for lead in leads]
            path = CaseStore(root).import_leads(run_id, parsed)
            return _ok({"path": str(path), "count": len(parsed), "untrusted": True})
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def delegation_plan(
        run_id: str, case_type: str, available_worker_cap: int, sources: list[str]
    ) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            return _ok(
                plan_delegation(
                    DelegationRequest.model_validate(
                        {"case_type": case_type, "available_worker_cap": available_worker_cap}
                    ),
                    sources,
                    run_id,
                ).model_dump()
            )
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def handoff_save(payload: dict[str, object]) -> dict[str, object]:
        try:
            return _ok(
                {"handoff_id": CaseStore(root).save_handoff(WorkerHandoff.model_validate(payload))}
            )
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def packet_save(
        run_id: str, payload: dict[str, object], decision_implication: str
    ) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            return _ok(
                save_packet(
                    CaseStore(root),
                    run_id,
                    ResearchPacket.model_validate(payload),
                    decision_implication,
                ).model_dump()
            )
        except ValidationError:
            return _error(PacketIncomplete())
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def brief_render(run_id: str) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            path = render_brief(CaseStore(root), run_id)
            return _ok({"path": str(path), "content": path.read_text()})
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def case_compare(
        case_key: str, base_run_id: str, later_run_id: str, lead_implication: str
    ) -> dict[str, object]:
        try:
            case_key = validate_case_key(case_key)
            base_run_id = validate_run_id(base_run_id)
            later_run_id = validate_run_id(later_run_id)
            return _ok(
                compare_runs(
                    CaseStore(root), case_key, base_run_id, later_run_id, lead_implication
                ).model_dump()
            )
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def case_export(case_key: str, destination: str) -> dict[str, object]:
        try:
            import shutil

            case_key = validate_case_key(case_key)
            store = CaseStore(root)
            src = store.case_path(case_key)
            dst = Path(destination).expanduser().resolve()
            if dst.exists():
                raise ValueError("destination already exists")
            shutil.copytree(src, dst)
            return _ok({"path": str(dst)})
        except Exception as e:
            return _error(e)

    return mcp


def main() -> None:
    root = Path(os.environ["SRD_ROOT"]) if "SRD_ROOT" in os.environ else ROOT
    create_server(root).run(transport="stdio")
