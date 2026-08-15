from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from .collection import collect_sources, ingest_host_rendered_text
from .delegation import plan_delegation
from .delta import compare_runs
from .diagnostics import build_diagnostics
from .errors import (
    DraftNotFound,
    InvalidRequest,
    InvalidStateTransition,
    PacketIncomplete,
    SrdError,
)
from .models import (
    CaseOpenRequest,
    DelegationRequest,
    HostRenderedImport,
    LeadCandidate,
    PdfImportMetadata,
    RecentDiscoveryRecord,
    ResearchPacket,
    ResearchPlan,
    WorkerHandoff,
    validate_case_key,
    validate_run_id,
)
from .packets import (
    approve_packet,
    load_approval,
    load_packet_draft,
    render_brief,
    save_packet_draft,
)
from .pdfs import ingest_pdf_path
from .recent import Runner, discover_recent
from .store import CaseStore

ROOT = Path.home() / ".stewardship-research-dossier" / "cases"
VENDOR_ROOT = Path(__file__).parents[2] / "third_party" / "last30days"
logger = logging.getLogger(__name__)


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
    logger.exception("Unhandled tool error", exc_info=exc)
    return {
        "ok": False,
        "error": {"code": "INTERNAL_ERROR", "message": "Unexpected internal error."},
    }


def create_server(
    root: Path = ROOT,
    *,
    recent_runner: Runner | None = None,
    vendor_root: Path = VENDOR_ROOT,
) -> FastMCP:
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
    async def source_collect(run_id: str, urls: list[str]) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            store = CaseStore(root)
            results = await asyncio.to_thread(collect_sources, store, run_id, urls)
            return _ok(
                [
                    {
                        "url": r.url,
                        "source": r.source.model_dump(mode="json") if r.source else None,
                        "error": (
                            {
                                "code": r.error.code,
                                "message": r.error.message,
                                "url": r.error.url or r.url,
                            }
                            if r.error
                            else None
                        ),
                    }
                    for r in results
                ]
            )
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def collection_finish(run_id: str) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            store = CaseStore(root)
            run = store.get_run(run_id)
            if run.state not in {"COLLECTING", "INVESTIGATING"}:
                raise InvalidStateTransition(run.state, "SYNTHESIS_PENDING")
            target = "SYNTHESIS_PENDING" if store.list_sources(run_id) else "BLOCKED"
            return _ok(store.transition(run_id, target).model_dump(mode="json"))
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def run_inspect(run_id: str) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            store = CaseStore(root)
            data = store.inspect_run(run_id).model_dump(mode="json")
            try:
                draft = load_packet_draft(store, run_id)
            except DraftNotFound:
                draft = None
            plan_path = store.run_path(run_id) / "research-plan.json"
            plan = store.load_research_plan(run_id) if plan_path.exists() else None
            recent = store.load_recent_discovery(run_id)
            approval = load_approval(store, run_id)
            data["research"] = {
                "plan": plan.model_dump(mode="json") if plan else None,
                "coverage": plan.model_dump(mode="json")["coverage"] if plan else None,
                "lead_count": len(store.list_leads(run_id)),
                "recent_discovery": recent.model_dump(mode="json") if recent else None,
                "draft": (
                    {"path": draft.path, "draft_sha256": draft.draft_sha256} if draft else None
                ),
                "approval": approval.model_dump(mode="json") if approval else None,
            }
            return _ok(data)
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def source_read(
        run_id: str, source_id: str, offset: int = 0, limit: int = 12_000
    ) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            chunk = CaseStore(root).read_source_chunk(run_id, source_id, offset=offset, limit=limit)
            return _ok(chunk.model_dump(mode="json"))
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def source_import_rendered(
        run_id: str, path: str, payload: dict[str, object]
    ) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            metadata = HostRenderedImport.model_validate(payload)
            source = ingest_host_rendered_text(CaseStore(root), run_id, Path(path), metadata)
            return _ok(source.model_dump(mode="json"))
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def packet_diagnostics(run_id: str) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            result = build_diagnostics(CaseStore(root), run_id)
            return _ok(result.model_dump(mode="json"))
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def filing_ingest(
        run_id: str, path: str, metadata: dict[str, object] | None = None
    ) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            parsed = PdfImportMetadata.model_validate(metadata) if metadata is not None else None
            return _ok(
                ingest_pdf_path(CaseStore(root), run_id, Path(path), parsed).model_dump(mode="json")
            )
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def lead_import(run_id: str, leads: list[dict[str, object]]) -> dict[str, object]:
        """Store Last30Days/host-discovery output as untrusted capture leads."""
        try:
            run_id = validate_run_id(run_id)
            parsed = [LeadCandidate.model_validate(lead) for lead in leads]
            persisted = CaseStore(root).import_leads(run_id, parsed)
            return _ok(
                {
                    "lead_ids": [lead.lead_id for lead in persisted],
                    "count": len(persisted),
                    "untrusted": True,
                }
            )
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def research_plan_save(run_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            plan = ResearchPlan.model_validate(payload)
            path = CaseStore(root).save_research_plan(run_id, plan)
            return _ok({"path": str(path), "coverage": plan.model_dump(mode="json")["coverage"]})
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def recent_discover(run_id: str, topic: str, as_of: str, days: int = 30) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            try:
                reference_date = date.fromisoformat(as_of)
            except ValueError as error:
                raise InvalidRequest("as_of must be an ISO date.") from error
            store = CaseStore(root)
            run = store.get_run(run_id)
            if reference_date != run.reference_date:
                raise InvalidRequest("as_of must match the run reference date.")
            try:
                result = discover_recent(
                    vendor_root,
                    topic,
                    reference_date,
                    days,
                    runner=recent_runner,
                )
            except SrdError as error:
                store.save_recent_discovery(
                    RecentDiscoveryRecord(
                        run_id=run_id,
                        topic=topic,
                        as_of=reference_date,
                        days=days,
                        lead_ids=[],
                        failures=[error.code],
                        completed_at=datetime.now(UTC),
                    )
                )
                raise
            leads = store.import_leads(run_id, result.leads)
            record = RecentDiscoveryRecord(
                run_id=run_id,
                topic=topic,
                as_of=reference_date,
                days=days,
                lead_ids=[lead.lead_id for lead in leads],
                failures=result.failures,
                completed_at=datetime.now(UTC),
            )
            store.save_recent_discovery(record)
            return _ok({**record.model_dump(mode="json"), "untrusted": True})
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
    def packet_draft_save(
        run_id: str, payload: dict[str, object], decision_implication: str
    ) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            try:
                packet = ResearchPacket.model_validate(payload)
            except ValidationError as error:
                raise PacketIncomplete() from error
            return _ok(
                save_packet_draft(
                    CaseStore(root),
                    run_id,
                    packet,
                    decision_implication,
                ).model_dump()
            )
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def packet_draft_read(run_id: str) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            return _ok(load_packet_draft(CaseStore(root), run_id).model_dump(mode="json"))
        except Exception as e:
            return _error(e)

    @mcp.tool()
    def packet_approve(
        run_id: str,
        actor: str,
        note: str = "",
        accept_evidence_gaps: bool = False,
    ) -> dict[str, object]:
        try:
            run_id = validate_run_id(run_id)
            approval = approve_packet(
                CaseStore(root),
                run_id,
                actor,
                note,
                accept_evidence_gaps=accept_evidence_gaps,
            )
            return _ok(approval.model_dump(mode="json"))
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
            case_key = validate_case_key(case_key)
            dst = CaseStore(root).export_case(case_key, Path(destination))
            return _ok({"path": str(dst)})
        except Exception as e:
            return _error(e)

    return mcp


def main() -> None:
    root = Path(os.environ["SRD_ROOT"]) if "SRD_ROOT" in os.environ else ROOT
    create_server(root).run(transport="stdio")
