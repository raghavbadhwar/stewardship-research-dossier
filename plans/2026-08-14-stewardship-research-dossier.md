# Stewardship Research Dossier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, host-native research-dossier prototype that captures public evidence, retains an explicit counter-view, renders a cited brief, and compares later research runs for Codex and Claude Code.

**Architecture:** A single Python 3.12 package runs as both CLI and local stdio MCP server. It stores a case in SQLite plus run-scoped artifacts, uses static public retrieval and PDF extraction, and returns deterministic delegation task cards for the host to execute. Thin Codex and Claude Code wrappers start that same runtime; the host lead owns all final synthesis.

**Tech Stack:** Python 3.12, `uv`, `mcp>=1.27,<2`, Pydantic v2, `httpx`, `trafilatura`, PyMuPDF, SQLite, pytest, Ruff and mypy.

## Global Constraints

- Build a new repository named `stewardship-research-dossier`; do not put product source in `career-ops`.
- Use Python 3.12 and a committed `uv.lock`; the bootstrap must be `uv run --locked`.
- Support local single-user cases only under `~/.stewardship-research-dossier/cases/`, with `--root` for test isolation.
- The host does reasoning, source discovery and native subagent spawning. The runtime does not call an LLM or start host agents.
- Static public retrieval is the default. Enforce 15 MB response cap, five redirects, 15-second connect timeout, 30-second total timeout, and four concurrent requests.
- Every final-packet finding must refer to a source captured in the same run.
- A valid packet requires thesis, counter-view, risk, open question and `analyst_review_required=true`.
- A normal delegation plan proposes at most three workers; `mixed` can reach four only with a lead-provided cap of four.
- No trades, brokers, credentials, paywall/access-control bypass, web app, cloud database, background service, LangGraph, A2A or agent team.
- Do not commit, push, publish, install globally, send messages or change host-wide configuration without explicit user approval.

---

## File structure

```text
stewardship-research-dossier/
  .agents/plugins/marketplace.json          # local Codex marketplace registration
  .codex-plugin/plugin.json                 # Codex plugin metadata
  .claude-plugin/plugin.json                # Claude Code plugin metadata
  .mcp.json                                 # host MCP process definitions
  bin/srd-mcp                               # locked runtime bootstrap
  pyproject.toml                            # dependency and CLI definition
  uv.lock                                   # locked dependency graph
  README.md                                 # truthful local-demo instructions
  skills/living-research/SKILL.md           # shared host workflow
  agents/
    filings-analyst.md                      # Claude bounded task card
    event-scout.md
    competitive-analyst.md
    governance-analyst.md
    thesis-skeptic.md
    delta-analyst.md
  src/srd/
    __init__.py
    cli.py                                  # doctor and offline fixture demo
    errors.py                               # named domain errors and envelope
    models.py                               # Pydantic request/artifact models
    store.py                                # SQLite schema and state transitions
    collection.py                           # safe static source capture
    pdfs.py                                 # PDF text extraction
    packets.py                              # packet validation and Markdown renderer
    delta.py                                # run-to-run evidence comparison
    delegation.py                           # deterministic task-card planner
    mcp_server.py                           # MCP adapters only
  tests/
    conftest.py
    test_models.py
    test_store.py
    test_collection.py
    test_pdfs.py
    test_packets.py
    test_delta.py
    test_delegation.py
    test_mcp_server.py
    test_cli.py
    fixtures/case_001/
    fixtures/case_002/
```

## Task 1: Create the isolated package and local commands

**Files:**

- Create: `pyproject.toml`
- Create: `src/srd/__init__.py`
- Create: `src/srd/cli.py`
- Create: `tests/test_cli.py`
- Create: `README.md`

**Interfaces:**

- Produces: `srd` CLI with `--version`, `doctor`, and `fixture-demo --offline` subcommands.
- Produces: `srd-mcp` entry point reserved for Task 9.

- [ ] **Step 1: Write the CLI version test.**

```python
from typer.testing import CliRunner
from srd.cli import app

def test_version_is_reported() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "srd 0.1.0"
```

- [ ] **Step 2: Run the test before implementation.**

Run: `uv run pytest tests/test_cli.py::test_version_is_reported -v`
Expected: collection fails because `srd.cli` does not exist.

- [ ] **Step 3: Add the minimal package definition and CLI.**

```toml
[project]
name = "stewardship-research-dossier"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "httpx>=0.27,<1",
  "mcp>=1.27,<2",
  "pydantic>=2.8,<3",
  "pymupdf>=1.24,<2",
  "trafilatura>=1.12,<3",
  "typer>=0.12,<1",
]

[project.scripts]
srd = "srd.cli:main"
srd-mcp = "srd.mcp_server:main"

[dependency-groups]
dev = ["mypy>=1.11,<2", "pytest>=8.3,<9", "ruff>=0.6,<1"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["srd"]
```

```python
# src/srd/cli.py
import typer

app = typer.Typer(no_args_is_help=True)

@app.callback()
def main(version: bool = typer.Option(False, "--version", is_eager=True)) -> None:
    if version:
        typer.echo("srd 0.1.0")
        raise typer.Exit()
```

- [ ] **Step 4: Generate the lockfile and pass the first test.**

Run: `uv lock && uv run pytest tests/test_cli.py::test_version_is_reported -v`
Expected: PASS.

- [ ] **Step 5: Add truthful README boundaries.**

Document local-only storage, public-source scope, host-owned reasoning/subagents, no investment decision/trading capability, the `uv` prerequisite, and the planned offline fixture demo. Do not mention NBIM as a customer or user.

- [ ] **Step 6: Review checkpoint.**

Run: `uv run ruff check . && uv run mypy src && git diff --check`
Expected: all pass. Present the diff for review; do not commit without explicit authorisation.

## Task 2: Define validated domain models and named failures

**Files:**

- Create: `src/srd/errors.py`
- Create: `src/srd/models.py`
- Create: `tests/test_models.py`

**Interfaces:**

- Produces: `CaseOpenRequest`, `SourceCapture`, `Finding`, `WorkerHandoff`, `ResearchPacket`, `Envelope`.
- Produces: `SrdError(code: str, message: str, url: str | None = None)` and its named subclasses.
- Consumed by: every later task.

- [ ] **Step 1: Write failing model tests.**

```python
from datetime import date
from pydantic import ValidationError
from srd.models import CaseOpenRequest, ResearchPacket

def test_case_key_rejects_path_traversal() -> None:
    with pytest.raises(ValidationError):
        CaseOpenRequest(
            case_key="../bad", issuer_name="Acme", question="Q?",
            theme="governance", reference_date=date(2026, 8, 14),
        )

def test_packet_requires_counter_view() -> None:
    with pytest.raises(ValidationError):
        ResearchPacket(thesis=[], counter_view=[], risks=[], open_questions=[])
```

- [ ] **Step 2: Run the test before implementation.**

Run: `uv run pytest tests/test_models.py -v`
Expected: collection fails because the models do not exist.

- [ ] **Step 3: Implement compact model constraints.**

Use a case-key regex of `^[a-z0-9][a-z0-9-]{2,63}$`. Restrict themes to `governance`, `risk`, `event`, `competitive`, `mixed`. Make `Finding.source_ids` non-empty. Use `Field(min_length=1)` for all four required research-packet sections, and default `analyst_review_required` to literal `True`.

```python
class PacketSourceMismatch(SrdError):
    def __init__(self, source_id: str) -> None:
        super().__init__("PACKET_SOURCE_MISMATCH", f"Source {source_id} is not captured in this run.")
```

- [ ] **Step 4: Run model and static checks.**

Run: `uv run pytest tests/test_models.py -v && uv run mypy src/srd/models.py src/srd/errors.py`
Expected: PASS.

- [ ] **Step 5: Review checkpoint.**

Run: `git diff --check`
Expected: no whitespace errors. Present the diff for review; do not commit without explicit authorisation.

## Task 3: Build the case store and enforce run lifecycle

**Files:**

- Create: `src/srd/store.py`
- Create: `tests/test_store.py`
- Modify: `src/srd/models.py`

**Interfaces:**

- Consumes: `CaseOpenRequest`, `InvalidStateTransition`, `CaseExists`, `CaseNotFound`.
- Produces: `CaseStore(root: Path)`, `open_case(request) -> CaseRef`, `start_run(case_key, reference_date) -> RunRef`, `transition(run_id, to_state) -> RunRef`, `run_path(run_id) -> Path`, `list_sources(run_id) -> list[SourceCapture]`.
- Consumed by: collection, packet, delta and MCP tasks.

- [ ] **Step 1: Write lifecycle tests.**

```python
def test_completed_run_cannot_return_to_collecting(store: CaseStore, request: CaseOpenRequest) -> None:
    case = store.open_case(request)
    run = store.start_run(case.case_key, request.reference_date)
    store.transition(run.run_id, "COLLECTING")
    store.transition(run.run_id, "INVESTIGATING")
    store.transition(run.run_id, "SYNTHESIS_PENDING")
    store.transition(run.run_id, "COMPLETE")
    with pytest.raises(InvalidStateTransition):
        store.transition(run.run_id, "COLLECTING")
```

- [ ] **Step 2: Run the focused test before implementation.**

Run: `uv run pytest tests/test_store.py::test_completed_run_cannot_return_to_collecting -v`
Expected: FAIL because `CaseStore` does not exist.

- [ ] **Step 3: Create schema and file layout atomically.**

Create `dossier.sqlite` under `<root>/<case_key>/`, enable `PRAGMA foreign_keys=ON`, and create the five tables from the technical specification. Use an explicit transition map:

```python
ALLOWED_TRANSITIONS = {
    "OPEN": {"COLLECTING", "BLOCKED"},
    "COLLECTING": {"INVESTIGATING", "SYNTHESIS_PENDING", "PARTIAL", "BLOCKED"},
    "INVESTIGATING": {"SYNTHESIS_PENDING", "PARTIAL", "BLOCKED"},
    "SYNTHESIS_PENDING": {"COMPLETE", "PARTIAL", "BLOCKED"},
    "PARTIAL": {"COLLECTING", "INVESTIGATING", "SYNTHESIS_PENDING", "COMPLETE"},
    "COMPLETE": set(),
    "BLOCKED": {"COLLECTING"},
}
```

Use `Path.mkdir(parents=True, exist_ok=False)` only for a new case. Create every run directory in a SQLite transaction boundary followed by a compensating delete if artifact-directory creation fails.

- [ ] **Step 4: Add coverage for duplicate cases and run directories.**

Test `CaseExists` for reopening with changed issuer/question, test that the same case can start run `0002`, and assert `runs/0001/request.json` is not altered by `runs/0002`.

- [ ] **Step 5: Run the store test suite.**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS.

## Task 4: Collect and capture static public sources

**Files:**

- Create: `src/srd/collection.py`
- Create: `tests/test_collection.py`
- Modify: `src/srd/store.py`

**Interfaces:**

- Consumes: `CaseStore`, `SourceCapture`, `SourceUnavailable`, `UnsupportedContentType`, `ExtractionFailed`.
- Produces: `collect_sources(store, run_id, urls) -> list[CaptureResult]`.
- `CaptureResult` contains `url`, `source: SourceCapture | None`, `error: SrdError | None`.
- Consumed by: MCP collection and fixture import.

- [ ] **Step 1: Write source-capture tests with `httpx.MockTransport`.**

```python
def test_html_capture_stores_extracted_text(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, headers={"content-type": "text/html"},
        text="<html><title>Acme</title><body><p>Material evidence.</p></body></html>",
    ))
    result = collect_sources(store, run_id, ["https://example.test/a"], transport=transport)
    assert result[0].source is not None
    assert Path(result[0].source.text_path).read_text() == "Material evidence."

def test_one_failed_url_does_not_abort_other_urls(...) -> None:
    ...
```

- [ ] **Step 2: Run the tests before implementation.**

Run: `uv run pytest tests/test_collection.py -v`
Expected: FAIL because `collect_sources` does not exist.

- [ ] **Step 3: Implement explicit static-fetch limits.**

Validate URL scheme before fetching. Use a single `httpx.AsyncClient` with `Timeout(connect=15.0, read=30.0, write=30.0, pool=30.0)`, `follow_redirects=True`, `max_redirects=5` and a semaphore of four. Stream the body to enforce 15 MB before extraction. Reject final URLs resolving to loopback, link-local, private or unspecified IP addresses. Accept only `text/html`, `application/xhtml+xml`, and `application/pdf`.

For HTML, extract text with `trafilatura.extract(..., include_links=False)`. Store source metadata in `sources/S-XXXX.json` and text in `sources/S-XXXX.txt`; calculate SHA-256 from UTF-8 text. Record a named error for each failure and leave the run usable.

- [ ] **Step 4: Add the shadow-path tests.**

Cover an empty extracted body (`EXTRACTION_FAILED`), 404 (`SOURCE_UNAVAILABLE`), unsupported MIME type (`UNSUPPORTED_CONTENT_TYPE`), 16 MB stream rejection, and a redirect to `127.0.0.1` rejection.

- [ ] **Step 5: Run the collection tests.**

Run: `uv run pytest tests/test_collection.py -v`
Expected: PASS.

## Task 5: Add public and local PDF ingestion

**Files:**

- Create: `src/srd/pdfs.py`
- Create: `tests/test_pdfs.py`
- Modify: `src/srd/collection.py`

**Interfaces:**

- Produces: `extract_pdf_bytes(data: bytes) -> str` and `ingest_pdf_path(store, run_id, path) -> SourceCapture`.
- Consumes: `ExtractionFailed`, `SourceCapture`, shared capture finaliser from `collection.py`.
- Consumed by: `filing_ingest` MCP tool.

- [ ] **Step 1: Write PDF tests using a generated single-page fixture.**

```python
def test_pdf_extraction_returns_visible_text(pdf_bytes: bytes) -> None:
    assert "Board composition" in extract_pdf_bytes(pdf_bytes)

def test_empty_pdf_text_is_rejected(blank_pdf_bytes: bytes) -> None:
    with pytest.raises(ExtractionFailed) as error:
        extract_pdf_bytes(blank_pdf_bytes)
    assert error.value.code == "EXTRACTION_FAILED"
```

- [ ] **Step 2: Run the focused test before implementation.**

Run: `uv run pytest tests/test_pdfs.py -v`
Expected: FAIL because `srd.pdfs` does not exist.

- [ ] **Step 3: Implement extraction and reuse source finalisation.**

Use `fitz.open(stream=data, filetype="pdf")`, concatenate non-empty page text in page order, strip only leading/trailing whitespace, and reject an empty result. `ingest_pdf_path` must resolve its path, reject missing/non-file paths, read at most 15 MB, assign `retrieval_method="pdf"`, and use the same artifact naming/hash path as HTML capture.

- [ ] **Step 4: Route public PDF responses from collection.**

When `source_collect` receives `application/pdf`, call `extract_pdf_bytes`; do not send it through the HTML extractor. Add a test asserting the resulting source method is `pdf`.

- [ ] **Step 5: Run PDF and collection regression tests.**

Run: `uv run pytest tests/test_pdfs.py tests/test_collection.py -v`
Expected: PASS.

## Task 6: Validate packets and render the deterministic research brief

**Files:**

- Create: `src/srd/packets.py`
- Create: `tests/test_packets.py`
- Modify: `src/srd/store.py`

**Interfaces:**

- Consumes: `ResearchPacket`, `Finding`, `CaseStore`, `PacketSourceMismatch`, `PacketIncomplete`.
- Produces: `save_packet(store, run_id, packet, decision_implication) -> PacketRef` and `render_brief(store, run_id) -> Path`.
- Consumed by: MCP packet/brief tools and offline fixture demo.

- [ ] **Step 1: Write packet validation tests.**

```python
def test_packet_rejects_source_from_another_run(store: CaseStore, valid_packet: ResearchPacket) -> None:
    other_run_source = capture_source_in_other_run(store)
    packet = valid_packet.model_copy(update={
        "thesis": [Finding(statement="Claim", source_ids=[other_run_source], confidence="medium")]
    })
    with pytest.raises(PacketSourceMismatch):
        save_packet(store, run_id, packet, "Review governance controls.")

def test_rendered_brief_has_required_sections(...) -> None:
    path = render_brief(store, run_id)
    assert path.read_text().index("## Current thesis") < path.read_text().index("## Counter-view")
```

- [ ] **Step 2: Run tests before implementation.**

Run: `uv run pytest tests/test_packets.py -v`
Expected: FAIL because packet functions do not exist.

- [ ] **Step 3: Implement source-binding and packet persistence.**

Read the source IDs in every `Finding`; compare against `store.list_sources(run_id)`. Reject the first missing source ID with `PacketSourceMismatch`. Write canonical JSON using `json.dumps(..., sort_keys=True, indent=2)` to `runs/<ordinal>/packet.json`, then insert packet metadata and transition `SYNTHESIS_PENDING` to `COMPLETE`.

- [ ] **Step 4: Implement a fixed-order Markdown renderer.**

Render exactly: title; `Analyst review required`; current thesis; counter-view; risks; open questions; decision implication; evidence ledger. For each finding, append citation labels in source-ID order. Do not use an LLM in this module.

- [ ] **Step 5: Add failure-path coverage.**

Test no packet for a run, invalid state, a source ID without a capture, and a packet that omits a required section. Confirm no `brief.md` is written in each failure path.

- [ ] **Step 6: Run the packet suite.**

Run: `uv run pytest tests/test_packets.py -v`
Expected: PASS.

## Task 7: Compare evidence across completed runs

**Files:**

- Create: `src/srd/delta.py`
- Create: `tests/test_delta.py`
- Modify: `src/srd/store.py`

**Interfaces:**

- Consumes: `CaseStore`, `RunNotComparable`.
- Produces: `EvidenceDelta(added, superseded, unchanged, lead_implication)` and `compare_runs(store, case_key, base_run_id, later_run_id, lead_implication) -> EvidenceDelta`.
- Consumed by: `case_compare` MCP tool and fixture demo.

- [ ] **Step 1: Write delta tests.**

```python
def test_compare_marks_same_url_changed_hash_as_superseded(store: CaseStore) -> None:
    base, later = two_completed_runs_with_changed_source(store)
    delta = compare_runs(store, case_key, base, later, "Revisit the prior conclusion.")
    assert delta.superseded == [("S-0001", "S-0003")]
    assert delta.added == ["S-0004"]

def test_compare_rejects_incomplete_run(store: CaseStore) -> None:
    with pytest.raises(RunNotComparable):
        compare_runs(store, case_key, complete_run_id, open_run_id, "")
```

- [ ] **Step 2: Run before implementation.**

Run: `uv run pytest tests/test_delta.py -v`
Expected: FAIL because `compare_runs` does not exist.

- [ ] **Step 3: Implement stable comparison.**

Compare sources by canonical final URL plus content hash. Same URL/hash is unchanged. Same URL/different hash forms one superseded pair. URLs only in later run are added. Sort every result by source ID. Require both runs to be `COMPLETE` or `PARTIAL` with a saved packet. Save sorted JSON to `runs/<later>/delta-from-<base>.json` and a Markdown counterpart.

- [ ] **Step 4: Add offline invariant.**

Test comparison after monkeypatching all HTTP entry points to raise; assert the delta still completes from stored source metadata and text only.

- [ ] **Step 5: Run the suite.**

Run: `uv run pytest tests/test_delta.py -v`
Expected: PASS.

## Task 8: Create deterministic delegation task cards

**Files:**

- Create: `src/srd/delegation.py`
- Create: `tests/test_delegation.py`
- Modify: `src/srd/models.py`

**Interfaces:**

- Produces: `DelegationRequest`, `TaskCard`, `DelegationPlan`, and `plan_delegation(request, sources) -> DelegationPlan`.
- Consumes: captured source IDs and a caller-supplied `available_worker_cap`.
- Consumed by: `delegation_plan` MCP tool and shared host skill.

- [ ] **Step 1: Write planner tests.**

```python
def test_governance_plan_is_bounded_to_three() -> None:
    plan = plan_delegation(DelegationRequest(case_type="governance", available_worker_cap=8), ["S-0001"])
    assert [task.role for task in plan.tasks] == [
        "governance-analyst", "filings-analyst", "thesis-skeptic"
    ]
    assert plan.max_workers == 3

def test_mixed_case_requires_explicit_cap_of_four() -> None:
    plan = plan_delegation(DelegationRequest(case_type="mixed", available_worker_cap=3), ["S-0001"])
    assert plan.max_workers == 3
```

- [ ] **Step 2: Run before implementation.**

Run: `uv run pytest tests/test_delegation.py -v`
Expected: FAIL because planner models/functions do not exist.

- [ ] **Step 3: Implement literal rule map and task-card schema.**

Use the four normal rules from the technical specification. Each task card must contain role, objective, `allowed_source_ids`, `stop_condition`, and `handoff_schema="WorkerHandoff"`. The join rule must state that only the lead saves a packet. Do not import an LLM SDK or an orchestration framework.

- [ ] **Step 4: Add caps and no-source tests.**

Test worker caps of zero through five, an empty source list, invalid role names, and that every card references only supplied source IDs. A zero cap returns an empty plan with a lead-only join rule.

- [ ] **Step 5: Run the planner suite.**

Run: `uv run pytest tests/test_delegation.py -v`
Expected: PASS.

## Task 9: Expose the workflow through MCP and the CLI

**Files:**

- Create: `src/srd/mcp_server.py`
- Modify: `src/srd/cli.py`
- Create: `tests/test_mcp_server.py`
- Modify: `tests/test_cli.py`

**Interfaces:**

- Produces MCP tools: `case_open`, `source_collect`, `filing_ingest`, `delegation_plan`, `handoff_save`, `packet_save`, `brief_render`, `case_compare`, `case_export`.
- Uses response envelope `{"ok": bool, "data"?: object, "error"?: {"code": str, "message": str, "url"?: str}}`.
- Produces CLI: `srd doctor`, `srd fixture-demo --offline`, `srd export CASE_KEY DESTINATION`.

- [ ] **Step 1: Write MCP envelope tests.**

```python
def test_case_open_returns_data_envelope(mcp_client: ClientSession) -> None:
    result = call_tool(mcp_client, "case_open", valid_case_open_payload())
    assert result["ok"] is True
    assert result["data"]["case_key"] == "acme-governance-2026"

def test_invalid_packet_returns_named_error(mcp_client: ClientSession) -> None:
    result = call_tool(mcp_client, "packet_save", invalid_packet_payload())
    assert result["ok"] is False
    assert result["error"]["code"] == "PACKET_INCOMPLETE"
    assert isinstance(result["error"]["message"], str)
```

- [ ] **Step 2: Run before implementation.**

Run: `uv run pytest tests/test_mcp_server.py -v`
Expected: FAIL because MCP server does not exist.

- [ ] **Step 3: Implement thin MCP adapters.**

Each MCP tool validates input with Pydantic, calls exactly one domain operation, converts `SrdError` into the error envelope, and lets only unexpected errors become a logged `INTERNAL_ERROR`. Do not duplicate domain logic in MCP functions. Default root is `Path.home() / ".stewardship-research-dossier"`; pass an injected root in tests.

- [ ] **Step 4: Implement CLI doctor and export.**

`doctor` checks Python version, `uv` invocation context, writable root, SQLite open/close, and optional Scrapling availability; it returns a non-zero exit if a required condition fails and reports optional Scrapling as informational. `export` rejects an existing destination and uses `shutil.copytree` only after all source and destination paths are resolved.

- [ ] **Step 5: Add end-to-end MCP call coverage.**

Using an in-process test server and mocked HTTP, open a case, collect one page, save a valid packet, render its brief, and assert the returned brief path exists.

- [ ] **Step 6: Run MCP/CLI tests.**

Run: `uv run pytest tests/test_mcp_server.py tests/test_cli.py -v`
Expected: PASS.

## Task 10: Package host-native skills, task cards and locked bootstrap

**Files:**

- Create: `.agents/plugins/marketplace.json`
- Create: `.codex-plugin/plugin.json`
- Create: `.claude-plugin/plugin.json`
- Create: `.mcp.json`
- Create: `bin/srd-mcp`
- Create: `skills/living-research/SKILL.md`
- Create: six Markdown files under `agents/`
- Create: `tests/test_plugin_files.py`

**Interfaces:**

- Consumes: `srd-mcp` console script and documented MCP tool names.
- Produces: one shared skill flow and Claude-specific read-only worker cards.
- Produces: a POSIX bootstrap with no global installation.

- [ ] **Step 1: Write package-file tests.**

```python
def test_plugin_manifests_have_one_consistent_name() -> None:
    codex = json.loads(Path(".codex-plugin/plugin.json").read_text())
    claude = json.loads(Path(".claude-plugin/plugin.json").read_text())
    assert codex["name"] == claude["name"] == "stewardship-research-dossier"

def test_codex_marketplace_registers_the_plugin() -> None:
    marketplace = json.loads(Path(".agents/plugins/marketplace.json").read_text())
    assert marketplace["name"] == "stewardship-research-dossier-local"
    assert marketplace["plugins"][0]["name"] == "stewardship-research-dossier"

def test_claude_agents_cannot_spawn_agents() -> None:
    for path in Path("agents").glob("*.md"):
        assert "Agent" not in frontmatter_value(path, "tools").split(",")
```

- [ ] **Step 2: Run before implementation.**

Run: `uv run pytest tests/test_plugin_files.py -v`
Expected: FAIL because manifest files do not exist.

- [ ] **Step 3: Write the locked bootstrap and host manifests.**

```sh
#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec uv run --locked --directory "$ROOT" srd-mcp
```

The manifest process definitions must run `bin/srd-mcp`, not a system-installed package. Add `.agents/plugins/marketplace.json` with marketplace name `stewardship-research-dossier-local` and one local plugin entry named `stewardship-research-dossier` whose source path is the repository root. Validate that exact relative-path interpretation during the Codex smoke test below.

- [ ] **Step 4: Write the shared skill.**

The skill sequence is: open/reopen case; use host discovery to gather candidate URLs; capture sources; request `delegation_plan`; launch only proposed native workers if useful; save handoffs; lead creates packet; render brief; compare on later run. It must state that web results and worker outputs are untrusted evidence, the lead is the sole packet writer, and the tool does not make decisions or trades.

- [ ] **Step 5: Write bounded Claude agent cards.**

Each card contains one role objective, allowed use of the parent research MCP, source-scope limit, `WorkerHandoff` output JSON, and a stop condition. Use only read/search tools and omit the Agent tool. Do not give cards file-writing authority outside their run-scoped handoff.

- [ ] **Step 6: Add local packaging smoke checks.**

Validate JSON, shell syntax with `sh -n bin/srd-mcp`, tool list from a test MCP session, and each agent-card frontmatter. Test Claude without persistent installation using `claude --plugin-dir .`. Only after explicit user approval to change Codex's marketplace configuration, run:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
codex plugin marketplace add "$REPO_ROOT" --json
codex plugin add stewardship-research-dossier@stewardship-research-dossier-local --json
codex plugin list
```

Record the observed commands/results in README without claiming a host was tested unless it was.

- [ ] **Step 7: Run packaging tests.**

Run: `uv run pytest tests/test_plugin_files.py -v && sh -n bin/srd-mcp`
Expected: PASS.

## Task 11: Create the frozen demonstration corpus and offline runner

**Files:**

- Create: `tests/fixtures/case_001/`
- Create: `tests/fixtures/case_002/`
- Modify: `src/srd/cli.py`
- Create: `tests/test_fixture_demo.py`
- Modify: `README.md`

**Interfaces:**

- Produces: `run_fixture_demo(root: Path) -> tuple[Path, Path]` and `srd fixture-demo --offline --root PATH`.
- Consumes: source artifact import, packet save, brief render, evidence delta.
- Produces: two runs of one anonymised/public-source issuer case with a later evidence change.

- [ ] **Step 1: Choose and freeze lawful public sources.**

Use an issuer whose reports and governance material are publicly accessible without authentication. Save only the permitted text/metadata necessary for the demo, source URLs, capture dates and hashes. Include at least one thesis source, one meaningful counter-view source and one changed/superseding source in the later run.

- [ ] **Step 2: Write the offline test.**

```python
def test_fixture_demo_never_uses_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("srd.collection.httpx.AsyncClient", network_forbidden)
    first_brief, second_delta = run_fixture_demo(tmp_path)
    assert "## Counter-view" in first_brief.read_text()
    assert "Superseded" in second_delta.read_text()
```

- [ ] **Step 3: Run before implementation.**

Run: `uv run pytest tests/test_fixture_demo.py -v`
Expected: FAIL because the fixture runner does not exist.

- [ ] **Step 4: Implement direct fixture import.**

The fixture runner must load local fixture files through the same capture finaliser used by live collection, never through the HTTP client. Create run 0001, save sources and packet, render a brief; create run 0002, save changed/new sources and packet, then write delta from run 0001.

- [ ] **Step 5: Write demo instructions that remain truthful.**

README must state this is a portfolio prototype, show `uv run srd fixture-demo --offline`, explain the reviewer can inspect source IDs and delta, and use the wording “informed by publicly described AI, risk and stewardship priorities” rather than any adoption claim.

- [ ] **Step 6: Run demo checks.**

Run: `uv run pytest tests/test_fixture_demo.py -v && uv run srd fixture-demo --offline`
Expected: PASS and prints paths to the brief and delta.

## Task 12: Perform the final local quality gate and candidate-demo review

**Files:**

- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md` only if the new repository is created inside a workspace that requires an architecture index
- Create: `docs/demo-review.md`

**Interfaces:**

- Consumes: all P0 behaviour and local plugin smoke-test evidence.
- Produces: a factual demo review record distinguishing passed local checks from unverified external claims.

- [ ] **Step 1: Add a candidate-demo checklist.**

`docs/demo-review.md` must include these exact checks: both fixture runs render; every brief finding has local source IDs; at least one counter-view is visible; delta identifies an added and superseded source; a lead-only run works; a three-worker plan is bounded; Claude plugin load was manually checked or explicitly marked not checked; Codex plugin load was manually checked or explicitly marked not checked.

- [ ] **Step 2: Run every automated gate.**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
uv run srd doctor
uv run srd fixture-demo --offline
git diff --check
```

Expected: every command exits zero. If a host smoke test was not performed, record it as unverified instead of inferring success from the manifest.

- [ ] **Step 3: Inspect the generated artifacts.**

Read both briefs and the delta. Confirm the final text does not contain “recommendation,” “alpha,” “production,” “NBIM uses,” “NBIM asked,” or any client/adoption claim. Confirm source URLs/IDs in Markdown exist in the case artifacts.

- [ ] **Step 4: Review checkpoint.**

Present the final diff and the command outputs. Do not commit, push, publish, email, submit, or install host-wide without explicit authorisation.

## Coverage map

| PRD/spec requirement | Plan task |
| --- | --- |
| local case history and lifecycle | 3 |
| HTML/static source capture | 4 |
| PDF ingestion | 5 |
| source-bound thesis/counter-view/risk packet | 6 |
| later-run evidence delta | 7 |
| adaptive host-owned subagents | 8 and 10 |
| CLI and MCP surface | 9 |
| Codex/Claude packaging | 10 |
| frozen two-run demo | 11 |
| local verification and truthful presentation | 12 |

## Implementation order and stop points

1. Tasks 1–3 establish the local data contract.
2. Tasks 4–7 make a single-lead dossier useful end-to-end.
3. Task 8 adds adaptive task planning without a swarm.
4. Tasks 9–10 expose the working runtime to both hosts.
5. Tasks 11–12 prove the candidate demo using frozen evidence.

Stop after Task 7 and run a single-lead case before adding any plugin wrappers. If the resulting brief is not decision-useful to a reviewer, improve the packet/brief experience before adding more acquisition or agent capabilities. Do not pursue optional Scrapling retrieval or external filing adapters until the frozen offline demo passes.

## Self-review results

- Every P0 requirement from the PRD maps to a numbered task above.
- Source capture, packet validation, delta comparison, delegation caps, MCP envelopes, plugin files and offline fixtures each have focused tests.
- The plan uses no hosted service, scheduler, agent framework or browser dependency.
- Commit and external-action steps require explicit user approval, consistent with the project operating rules.
