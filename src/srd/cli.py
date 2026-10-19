"""Local CLI for the Stewardship Research Dossier prototype."""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer

from srd import __version__
from srd.delta import compare_runs
from srd.diagnostics import build_diagnostics
from srd.models import (
    CaseOpenRequest,
    EvidenceCitation,
    Finding,
    ResearchPacket,
    SourceCapture,
    validate_case_key,
    validate_run_id,
)
from srd.packets import render_brief, save_packet
from srd.store import CaseStore

DEFAULT_ROOT = Path.home() / ".stewardship-research-dossier" / "cases"
FIXTURE_ROOT = Path(__file__).parents[2] / "tests" / "fixtures"

app = typer.Typer(no_args_is_help=True)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"srd {__version__}")
        raise typer.Exit()


@app.command("diagnostics")
def diagnostics(run_id: str, root: Path = DEFAULT_ROOT) -> None:
    try:
        run_id = validate_run_id(run_id)
        result = build_diagnostics(CaseStore(root), run_id)
    except Exception as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(result.model_dump_json(indent=2))


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True)] = False,
) -> None:
    pass


def _import_fixture_sources(
    store: CaseStore, run_id: str, fixture_name: str
) -> list[SourceCapture]:
    fixture_root = (FIXTURE_ROOT / fixture_name).resolve()
    sources: list[dict[str, str]] = json.loads(
        (fixture_root / "sources.json").read_text(encoding="utf-8")
    )
    captured: list[SourceCapture] = []
    for metadata in sources:
        text_path = (fixture_root / metadata["text_file"]).resolve()
        if not text_path.is_relative_to(fixture_root):
            raise ValueError("Fixture text path escapes its fixture directory.")
        captured.append(
            store.add_source(
                run_id,
                url=metadata["url"],
                title=metadata["title"],
                publisher=metadata["publisher"],
                retrieval_method=metadata["retrieval_method"],
                text=text_path.read_text(encoding="utf-8"),
                captured_at=datetime.fromisoformat(metadata["captured_at"]),
                content_sha256=metadata["content_sha256"],
            )
        )
    return captured


def _cite(source: SourceCapture, locator: str, excerpt: str) -> EvidenceCitation:
    return EvidenceCitation(source_id=source.source_id, locator=locator, excerpt=excerpt)


def run_fixture_demo(root: Path) -> tuple[Path, Path]:
    store = CaseStore(root)
    req = CaseOpenRequest(
        case_key="fixture-governance-2026",
        issuer_name="Microsoft Corporation",
        question=(
            "Do Microsoft’s public disclosures identify board-level oversight mechanisms "
            "for material AI-related risks, and what remains unresolved for stewardship review?"
        ),
        theme="governance",
        reference_date=date(2026, 8, 1),
    )
    if store.case_path(req.case_key).exists():
        raise FileExistsError("Fixture demo case already exists; choose a new --root.")
    store.open_case(req)
    r1 = store.start_run(req.case_key, req.reference_date)
    store.transition(r1.run_id, "COLLECTING")
    framework, reporting, annual = _import_fixture_sources(store, r1.run_id, "case_001")
    store.transition(r1.run_id, "SYNTHESIS_PENDING")
    p = ResearchPacket(
        thesis=[
            Finding(
                finding_id="T-001",
                statement=(
                    "Microsoft's public disclosures identify board-level oversight mechanisms "
                    "for responsible AI-related policy and risk."
                ),
                citations=[
                    _cite(
                        framework,
                        "Purpose",
                        "Through oversight, review, and counsel, Microsoft’s Board of Directors "
                        "works with management to establish and promote business goals, "
                        "organizational objectives, and a strategy that is mindful of how our "
                        "business affects and is affected by the broader environment.",
                    ),
                    _cite(
                        reporting,
                        "Environmental, Social, and Public Policy Committee",
                        "The charter for the Microsoft Environmental, Social, and Public Policy "
                        "Committee includes assisting the Board of Directors in overseeing the "
                        "company’s “policies and programs and related risks that concern "
                        "environmental sustainability, the social and public policy impacts of "
                        "technology including privacy, digital safety, and responsible artificial "
                        "intelligence, and legal, regulatory, and compliance matters relating to "
                        "competition / antitrust, trade, and national security.”",
                    ),
                ],
                confidence="medium",
            )
        ],
        counter_view=[
            Finding(
                finding_id="C-001",
                statement=(
                    "Public disclosure does not establish operating effectiveness or show what "
                    "evidence the Board receives about AI-risk controls."
                ),
                citations=[
                    _cite(
                        reporting,
                        "Reporting our progress",
                        "ESG materiality in our reporting does not directly correspond to the "
                        "concept of materiality used in securities law.",
                    )
                ],
                confidence="medium",
                contradicts=["T-001"],
            )
        ],
        risks=[
            Finding(
                finding_id="R-001",
                statement=(
                    "The annual report says regulatory applicability can be unclear, change over "
                    "time, and vary across jurisdictions."
                ),
                citations=[
                    _cite(
                        annual,
                        "Government regulation",
                        "How these laws and regulations apply to our business is often unclear, "
                        "subject to change over time, and sometimes may be inconsistent from "
                        "jurisdiction to jurisdiction.",
                    )
                ],
                confidence="low",
            )
        ],
        open_questions=[
            (
                "What evidence does the Board receive to test whether AI-risk controls operate "
                "effectively?"
            )
        ],
    )
    save_packet(
        store,
        r1.run_id,
        p,
        "Investigate what evidence the Board receives about AI-risk control effectiveness.",
    )
    brief = render_brief(store, r1.run_id)
    r2 = store.start_run(req.case_key, date(2026, 8, 14))
    store.transition(r2.run_id, "COLLECTING")
    reporting_2, framework_2, transparency = _import_fixture_sources(store, r2.run_id, "case_002")
    store.transition(r2.run_id, "SYNTHESIS_PENDING")
    p2 = ResearchPacket(
        thesis=[
            Finding(
                finding_id="T-001",
                statement=(
                    "The later capture continues to identify a Board committee remit covering "
                    "responsible artificial intelligence and adds explicit framework references "
                    "to risk oversight."
                ),
                citations=[
                    _cite(
                        reporting_2,
                        "Environmental, Social, and Public Policy Committee",
                        "responsible artificial intelligence",
                    ),
                    _cite(
                        framework_2,
                        "Framework practices",
                        "Risk oversight",
                    ),
                ],
                confidence="medium",
            )
        ],
        counter_view=[
            Finding(
                finding_id="C-001",
                statement=(
                    "The added transparency-report page describes responsible-AI work at a high "
                    "level but does not resolve the Board-evidence question."
                ),
                citations=[
                    _cite(
                        transparency,
                        "Responsible AI Transparency Report",
                        "Discover how we build AI systems and models responsibly, support our "
                        "customers, learn, evolve, and grow in our responsible AI work.",
                    )
                ],
                confidence="medium",
                contradicts=["T-001"],
            )
        ],
        risks=[
            Finding(
                finding_id="R-001",
                statement=(
                    "The reporting scope remains distinct from securities-law materiality and "
                    "should not be treated as outcome evidence."
                ),
                citations=[
                    _cite(
                        reporting_2,
                        "Reporting our progress",
                        "ESG materiality in our reporting does not directly correspond to the "
                        "concept of materiality used in securities law.",
                    )
                ],
                confidence="low",
            )
        ],
        open_questions=[
            (
                "Does the Board receive evidence sufficient to test the effectiveness of AI-risk "
                "controls?"
            )
        ],
    )
    save_packet(
        store,
        r2.run_id,
        p2,
        "Determine whether the Board receives evidence sufficient to test AI-risk controls.",
    )
    render_brief(store, r2.run_id)
    compare_runs(
        store,
        req.case_key,
        r1.run_id,
        r2.run_id,
        "Investigate whether the Board receives evidence sufficient to test the effectiveness "
        "of AI-risk controls; no decision is automated.",
    )
    return brief, store.run_path(r2.run_id) / "delta-from-0001.md"


@app.command()
def doctor(root: Path = DEFAULT_ROOT) -> None:
    if sys.version_info[:2] != (3, 12):
        typer.echo("srd doctor: Python 3.12 is required", err=True)
        raise typer.Exit(1)
    try:
        if shutil.which("uv") is None:
            raise OSError("uv is required but was not found on PATH")
        CaseStore(root)
        probe = root / ".srd-write-probe"
        probe.write_text("ok")
        probe.unlink()
        sqlite3.connect(":memory:").close()
    except OSError as e:
        typer.echo(f"srd doctor: {e}", err=True)
        raise typer.Exit(1)
    typer.echo("srd doctor: ok (Python 3.12)")


@app.command("fixture-demo")
def fixture_demo(
    offline: bool = typer.Option(False, "--offline"), root: Path = Path("demo-output")
) -> None:
    if not offline:
        raise typer.BadParameter("--offline is required for the frozen demo")
    brief, delta = run_fixture_demo(root)
    typer.echo(str(brief))
    typer.echo(str(delta))


@app.command()
def export(case_key: str, destination: Path, root: Path = DEFAULT_ROOT) -> None:
    try:
        case_key = validate_case_key(case_key)
        dest = CaseStore(root).export_case(case_key, destination)
    except Exception as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(str(dest))


if __name__ == "__main__":
    app()
