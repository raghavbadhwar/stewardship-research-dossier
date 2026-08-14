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
from srd.models import CaseOpenRequest, Finding, ResearchPacket, SourceCapture, validate_case_key
from srd.packets import render_brief, save_packet
from srd.store import CaseStore

DEFAULT_ROOT = Path.home() / ".stewardship-research-dossier" / "cases"
FIXTURE_ROOT = Path(__file__).parents[2] / "tests" / "fixtures"

app = typer.Typer(no_args_is_help=True)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"srd {__version__}")
        raise typer.Exit()


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


def run_fixture_demo(root: Path) -> tuple[Path, Path]:
    store = CaseStore(root)
    req = CaseOpenRequest(
        case_key="fixture-governance-2026",
        issuer_name="Microsoft Corporation",
        question="Does the frozen public evidence merit deeper governance review?",
        theme="governance",
        reference_date=date(2026, 8, 14),
    )
    if store.case_path(req.case_key).exists():
        raise FileExistsError("Fixture demo case already exists; choose a new --root.")
    store.open_case(req)
    r1 = store.start_run(req.case_key, req.reference_date)
    store.transition(r1.run_id, "COLLECTING")
    a, b = _import_fixture_sources(store, r1.run_id, "case_001")
    store.transition(r1.run_id, "SYNTHESIS_PENDING")
    p = ResearchPacket(
        thesis=[
            Finding(
                statement="The frozen governance framework excerpt describes board oversight.",
                source_ids=[a.source_id],
                confidence="medium",
            )
        ],
        counter_view=[
            Finding(
                statement="The frozen annual-report excerpt identifies material uncertainty.",
                source_ids=[b.source_id],
                confidence="medium",
            )
        ],
        risks=[
            Finding(
                statement="The limited frozen excerpts may omit relevant context.",
                source_ids=[b.source_id],
                confidence="low",
            )
        ],
        open_questions=["Do later public disclosures alter the review scope?"],
    )
    save_packet(store, r1.run_id, p, "Review the source-linked public evidence with a human lead.")
    brief = render_brief(store, r1.run_id)
    r2 = store.start_run(req.case_key, date(2026, 8, 15))
    store.transition(r2.run_id, "COLLECTING")
    a2, c = _import_fixture_sources(store, r2.run_id, "case_002")
    store.transition(r2.run_id, "SYNTHESIS_PENDING")
    p2 = ResearchPacket(
        thesis=[
            Finding(
                statement="The later frozen governance excerpt contains changed wording.",
                source_ids=[a2.source_id],
                confidence="medium",
            )
        ],
        counter_view=[
            Finding(
                statement="The policy excerpt adds governance context not present in run 0001.",
                source_ids=[c.source_id],
                confidence="medium",
            )
        ],
        risks=[
            Finding(
                statement="The frozen excerpts remain incomplete evidence.",
                source_ids=[c.source_id],
                confidence="low",
            )
        ],
        open_questions=["Should the lead inspect the cited primary documents in full?"],
    )
    save_packet(store, r2.run_id, p2, "Revisit the source-linked evidence with a human lead.")
    render_brief(store, r2.run_id)
    compare_runs(
        store,
        req.case_key,
        r1.run_id,
        r2.run_id,
        "Revisit the frozen evidence; no conclusion is automated.",
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
    try:
        import scrapling  # noqa: F401

        rendered_status = "available"
    except ImportError:
        rendered_status = "not installed (optional: uv sync --extra rendered)"
    typer.echo(f"srd doctor: ok (Python 3.12; Scrapling {rendered_status})")


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
    except Exception as error:
        raise typer.BadParameter(str(error)) from error
    source = CaseStore(root).case_path(case_key).resolve()
    dest = destination.expanduser().resolve()
    if dest.exists():
        raise typer.BadParameter("destination already exists")
    shutil.copytree(source, dest)
    typer.echo(str(dest))


if __name__ == "__main__":
    app()
