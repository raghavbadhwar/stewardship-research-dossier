# Stewardship Dossier Core Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local candidate prototype produce a decision-useful, claim-traceable stewardship dossier while repairing confirmed trust-boundary and persistence defects and proving a real host workflow.

**Architecture:** Keep the existing Python package, SQLite-plus-files case store, CLI, and stdio MCP server. Replace document-level finding references with validated citation excerpts, route persistence through `CaseStore`, pin approved public addresses in the existing HTTP stack, and keep the final synthesis human-owned. Remove speculative runtime memory and optional rendered retrieval rather than hardening features that have not proved useful.

**Tech Stack:** Python 3.12, uv, Pydantic 2, httpx/httpcore, trafilatura, PyMuPDF, sqlite3, Typer, MCP FastMCP, pytest, Ruff, mypy.

## Global Constraints

- Python must remain `>=3.12,<3.13`; use `uv` and `uv run --locked`.
- Add no production or development dependency; update `uv.lock` only for removal of the Scrapling optional group.
- The runtime never calls an LLM, spawns host agents, makes an investment/risk/engagement/voting decision, executes a trade, uses credentials, or bypasses access controls.
- The lead is the only canonical packet writer; every packet citation belongs to the same run and matches captured text.
- Keep storage single-user and local; do not add a service, cloud database, scheduler, dashboard, vector store, or migration framework.
- Preserve a delegation cap of zero and allow four mixed-case workers only when the caller explicitly supplies `4`.
- Keep approved local-PDF access as an explicit caller-authority boundary; do not add a path allowlist.
- Do not commit, push, publish, deploy, install a host plugin, or change external configuration without separate user approval.
- Preserve unrelated user changes; only the approved uncommitted memory surface may be removed.

## File map

- Modify `src/srd/models.py`: evidence citation and delta schemas; remove memory schemas.
- Modify `src/srd/errors.py`: evidence/artifact failures; remove memory-limit failure.
- Modify `src/srd/store.py`: context-managed connections, stable IDs, public packet/source/case methods; remove memory store.
- Modify `src/srd/packets.py`: citation validation, atomic artifact cleanup, evidence-rich rendering.
- Modify `src/srd/collection.py`: pinned transport, metadata extraction, static-only capture.
- Modify `src/srd/pdfs.py`: size preflight.
- Modify `src/srd/delta.py`: chronological comparison and withdrawn evidence.
- Modify `src/srd/mcp_server.py`: memory/rendered removal, narrow validation, unexpected-error logging.
- Modify `src/srd/cli.py`: evidence-rich fixtures and safe export.
- Modify `agents/*.md`, `skills/living-research/SKILL.md`, `README.md`, `docs/demo-review.md`, copied `specs/` and `plans/`: contracts and factual verification record.
- Modify focused tests in place; delete `tests/test_learning_loop.py`; update frozen fixture files and metadata.

---

### Task 1: Remove speculative memory and rendered-retrieval surfaces

**Files:**
- Modify: `src/srd/models.py`
- Modify: `src/srd/errors.py`
- Modify: `src/srd/store.py`
- Modify: `src/srd/delegation.py`
- Modify: `src/srd/mcp_server.py`
- Modify: `src/srd/collection.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `agents/*.md`
- Modify: `skills/living-research/SKILL.md`
- Modify: `README.md`
- Modify: `tests/test_mcp_stdio.py`
- Modify: `tests/test_plugin_files.py`
- Delete: `tests/test_learning_loop.py`

**Interfaces:**
- Consumes: current MCP tool list and `plan_delegation(request, sources, run_id="")`.
- Produces: the original core MCP surface without `agent_memory_list`, `agent_memory_save`, or `rendered_fallback`; role personalities remain in worker cards.

- [x] **Step 1: Change MCP and plugin tests to the intended reduced surface**

In `tests/test_mcp_stdio.py`, assert the tool set contains the ten core tools and excludes memory tools. In `tests/test_plugin_files.py`, retain the `## Working personality` assertion and remove procedural-memory/candidate-lesson assertions:

```python
listed = await session.list_tools()
by_name = {tool.name: tool for tool in listed.tools}
assert {"case_open", "source_collect", "filing_ingest", "lead_import", "delegation_plan", "handoff_save", "packet_save", "brief_render", "case_compare", "case_export"} == set(by_name)
assert "agent_memory_list" not in by_name
assert "agent_memory_save" not in by_name
assert "rendered_fallback" not in by_name["source_collect"].inputSchema["properties"]

assert "## Working personality" in text
assert "## Procedural memory" not in text
assert "candidate_lessons" not in text
```

- [x] **Step 2: Run the focused tests and verify they fail**

Run: `uv run --locked pytest -q tests/test_mcp_stdio.py tests/test_plugin_files.py`

Expected: FAIL because memory tools, rendered input, and worker memory fields still exist.

- [x] **Step 3: Remove only the approved speculative surfaces**

Delete `LessonCandidate`, `AgentMemoryDraft`, `AgentMemory`, `AgentRole`, `TaskCard.memory_guidance`, `AgentMemoryLimit`, `CaseStore` memory methods, MCP memory tools, delegation memory parameters, `collect_rendered_source`, and `rendered_fallback`. Remove the `[project.optional-dependencies].rendered` group and run `uv lock`.

In each `agents/*.md`, keep `## Working personality` and remove `## Procedural memory` plus `candidate_lessons`. Restore the handoff JSON to:

```json
{
  "run_id": "acme-governance-2026:0001",
  "role": "governance-analyst",
  "sources": ["S-0001"],
  "findings": [],
  "open_questions": [],
  "recommendations_for_lead": []
}
```

Delete `tests/test_learning_loop.py` and remove the uncommitted Task 13 and README learning section.

- [x] **Step 4: Run focused checks**

Run: `uv lock --check && uv run --locked pytest -q tests/test_mcp_stdio.py tests/test_plugin_files.py tests/test_core.py`

Expected: PASS; lock contains no Scrapling requirement; specialist personalities remain.

- [x] **Step 5: Review checkpoint**

Run: `git diff --check && git status --short`

Expected: only approved memory/rendered removals plus the new Superpowers documents; do not commit.

---

### Task 2: Add claim-level evidence and storage-owned packet persistence

**Files:**
- Modify: `src/srd/models.py`
- Modify: `src/srd/errors.py`
- Modify: `src/srd/store.py`
- Modify: `src/srd/packets.py`
- Modify: `src/srd/cli.py`
- Modify: `agents/*.md`
- Modify: `tests/test_core.py`
- Modify: `tests/test_failure_paths.py`
- Modify: `tests/test_mcp_server.py`

**Interfaces:**
- Produces: `EvidenceCitation(source_id: str, locator: str, excerpt: str)`, `CaseStore.get_case`, `CaseStore.read_source_text`, `CaseStore.save_packet_row`, `CaseStore.set_brief_path`.
- Consumes: existing `SourceCapture`, run lifecycle, and `ResearchPacket` structure.

- [x] **Step 1: Write failing evidence and artifact tests**

Add helpers and checks equivalent to:

```python
def citation(source_id: str, excerpt: str = "Captured evidence.") -> EvidenceCitation:
    return EvidenceCitation(source_id=source_id, locator="Risk oversight", excerpt=excerpt)

def finding(source_id: str, excerpt: str = "Captured evidence.") -> Finding:
    return Finding(statement="Board oversight is disclosed.", citations=[citation(source_id, excerpt)], confidence="medium")

def packet_with(item: Finding) -> ResearchPacket:
    return ResearchPacket(thesis=[item], counter_view=[item], risks=[item], open_questions=["What remains unresolved?"])

def synthesis_run_with_source(tmp_path: Path, text: str) -> tuple[CaseStore, str, str]:
    store = CaseStore(tmp_path)
    store.open_case(request())
    run = store.start_run(request().case_key, date(2026, 8, 14))
    store.transition(run.run_id, "COLLECTING")
    source = store.add_source(run.run_id, url="https://example.test/evidence", title="Evidence", publisher="Example", retrieval_method="static", text=text)
    store.transition(run.run_id, "SYNTHESIS_PENDING")
    return store, run.run_id, source.source_id

def test_packet_rejects_excerpt_absent_from_captured_source(store: CaseStore, run_id: str) -> None:
    with pytest.raises(EvidenceExcerptMismatch):
        save_packet(store, run_id, packet_with(finding("S-0001", "Invented excerpt.")), "Review oversight effectiveness.")

def test_rendered_brief_contains_locator_excerpt_and_hash(tmp_path: Path) -> None:
    store, run_id, source_id = synthesis_run_with_source(tmp_path, "Captured evidence.")
    save_packet(store, run_id, packet_with(finding(source_id)), "Review oversight effectiveness.")
    text = render_brief(store, run_id).read_text()
    assert "[S-0001, Risk oversight]" in text
    assert "> Captured evidence." in text
    assert "sha256" in text.lower()
```

Add a missing-packet-artifact test that deletes `packet.json` after `save_packet` and expects `ArtifactUnavailable` from `render_brief`.

- [x] **Step 2: Run tests and verify the schema fails**

Run: `uv run --locked pytest -q tests/test_core.py tests/test_failure_paths.py tests/test_mcp_server.py`

Expected: FAIL because `EvidenceCitation`, excerpt validation, and named artifact handling do not exist.

- [x] **Step 3: Implement the minimal evidence schema**

In `models.py` add:

```python
class EvidenceCitation(BaseModel):
    source_id: str
    locator: str = Field(min_length=1, max_length=160)
    excerpt: str = Field(min_length=1, max_length=800)

class Finding(BaseModel):
    statement: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]
    contradicts: list[str] = Field(default_factory=list)
```

Remove `Finding.source_ids`; update fixture code, tests, and agent output examples to use `citations`.

In `errors.py` add stable codes `EVIDENCE_EXCERPT_MISMATCH` and `ARTIFACT_UNAVAILABLE` without exposing file content.

- [x] **Step 4: Put SQLite lifetime and packet data behind CaseStore**

Use a standard-library context manager:

```python
@contextmanager
def _db(self, case_key: str) -> Iterator[sqlite3.Connection]:
    path = self.case_path(case_key) / "dossier.sqlite"
    if not path.exists():
        raise CaseNotFound(case_key)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()
```

Convert every caller to `with self._db(case_key) as conn:`. Implement the four public methods from the design. `read_source_text` verifies run membership and converts `FileNotFoundError`/`OSError` into `ArtifactUnavailable`.

Allocate source IDs with:

```sql
SELECT COALESCE(MAX(CAST(SUBSTR(source_id, 3) AS INTEGER)), 0) + 1 FROM sources
```

Use sibling `.tmp` files and `Path.replace`; remove temporary/new artifacts on failed database writes.

- [x] **Step 5: Validate citations and render evidence**

In `save_packet`, reject an existing packet row, iterate all citations, verify source membership, and compare `" ".join(excerpt.split())` with normalised stored text. Write `packet.json.tmp`, replace it, call `save_packet_row`, and unlink the new artifact if persistence fails.

Render each finding with:

```python
lines.append(f"- {finding['statement']} [{labels}]")
for cite in finding["citations"]:
    lines.append(f"  > [{cite['source_id']}, {cite['locator']}] {cite['excerpt']}")
```

Render retrieval method and SHA-256 in the evidence ledger. Use `get_case` and `set_brief_path`; do not access `store._db` in `packets.py`.

- [x] **Step 6: Run focused checks**

Run: `uv run --locked pytest -q tests/test_core.py tests/test_failure_paths.py tests/test_mcp_server.py`

Expected: PASS, including excerpt mismatch and missing-artifact errors.

- [x] **Step 7: Review checkpoint**

Run: `uv run --locked ruff check src/srd/models.py src/srd/store.py src/srd/packets.py tests/test_core.py tests/test_failure_paths.py && uv run --locked mypy src`

Expected: PASS; do not commit.

---

### Task 3: Pin public HTTP connections and capture real metadata

**Files:**
- Modify: `src/srd/collection.py`
- Modify: `tests/test_collection_security.py`
- Modify: `tests/test_failure_paths.py`
- Modify: `tests/test_core.py`

**Interfaces:**
- Consumes: `Resolver = Callable[[str], Awaitable[set[str]]]` and an optional inner `httpx.AsyncBaseTransport` for tests.
- Produces: `PinnedPublicTransport(resolver, inner=None)` and static-only `collect_sources` with original logical URLs preserved.

- [x] **Step 1: Write failing connection-pinning and metadata tests**

Use a mock resolver returning `93.184.216.34` and a mock inner transport that records the transport-level request. Assert:

```python
assert request.url.host == "93.184.216.34"
assert request.headers["host"] == "public.example"
assert request.extensions["sni_hostname"] == "public.example"
assert result.source and str(result.source.url) == "https://public.example/report"
```

Add a resolver sequence that would return a public address first and a private address second; assert it is called once per request. Add HTML with `<title>Board Oversight Report</title>` and assert the captured title is not the hostname.

- [x] **Step 2: Run security tests and verify failure**

Run: `uv run --locked pytest -q tests/test_collection_security.py tests/test_failure_paths.py::test_hostname_resolution_rejects_private_answers tests/test_core.py::test_collection_packet_and_delta`

Expected: FAIL because the inner transport still receives the hostname and metadata falls back to the host.

- [x] **Step 3: Implement the pinned transport using installed httpx/httpcore behavior**

Create a small `httpx.AsyncBaseTransport` that validates one deterministic resolved address, copies the request URL with the approved IP, sets `Host` and `sni_hostname`, delegates to `httpx.AsyncHTTPTransport` or the injected inner transport, then reassigns `response.request` to the logical request before returning it.

Do not call `_validate_public_url` separately before `client.stream`; the transport is the single shared enforcement point. Redirects remain explicit and each redirected request passes through the same transport.

Tests that inject `httpx.MockTransport` must also inject an explicit resolver; remove `_test_transport_resolver` and the current inference from `transport is not None`.

- [x] **Step 4: Extract metadata with trafilatura**

Use:

```python
metadata = trafilatura.extract_metadata(data)
title = (metadata.title if metadata else None) or host or "Captured source"
publisher = (metadata.sitename if metadata else None) or host
```

Keep MIME, timeout, concurrency, redirect, and 15 MB limits unchanged.

- [x] **Step 5: Run collection checks**

Run: `uv run --locked pytest -q tests/test_collection_security.py tests/test_failure_paths.py tests/test_core.py`

Expected: PASS; resolver count and transport-level pinning are asserted.

- [x] **Step 6: Review checkpoint**

Run: `uv run --locked ruff check src/srd/collection.py tests/test_collection_security.py && uv run --locked mypy src`

Expected: PASS; do not commit.

---

### Task 4: Correct delta, export, PDF, and MCP failure semantics

**Files:**
- Modify: `src/srd/models.py`
- Modify: `src/srd/delta.py`
- Modify: `src/srd/cli.py`
- Modify: `src/srd/pdfs.py`
- Modify: `src/srd/mcp_server.py`
- Modify: `src/srd/store.py`
- Modify: `tests/test_core.py`
- Modify: `tests/test_failure_paths.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_mcp_server.py`

**Interfaces:**
- Produces: `EvidenceDelta.withdrawn`, chronological comparison, safe export, pre-read PDF rejection, logged unexpected errors.
- Consumes: packet-backed runs and the public `CaseStore` methods from Task 2.

- [x] **Step 1: Write failing behavior tests**

Add tests that:

```python
with pytest.raises(RunNotComparable):
    compare_runs(store, case_key, later_run, earlier_run, "Review.")
with pytest.raises(RunNotComparable):
    compare_runs(store, case_key, earlier_run, earlier_run, "Review.")
assert delta.withdrawn == [base_only_source_id]
```

Use Typer’s `CliRunner` to assert exporting to `store.case_path(case_key) / "nested"` fails without creating the destination, while a sibling destination succeeds.

Monkeypatch `Path.read_bytes` to fail if called for an oversized PDF and assert `SourceUnavailable` is raised first. Use `caplog` to assert `_error(RuntimeError("boom"))` logs `boom` while returning only `INTERNAL_ERROR` to the caller.

- [x] **Step 2: Run focused tests and verify failure**

Run: `uv run --locked pytest -q tests/test_cli.py tests/test_failure_paths.py tests/test_mcp_server.py`

Expected: FAIL for missing withdrawn/order/export/preflight/log behavior.

- [x] **Step 3: Implement minimal corrections**

Add `withdrawn: list[str]` to `EvidenceDelta`. Load both runs once and reject unless `base.ordinal < later.ordinal`. Compute withdrawn URLs as `base_urls.keys() - later_urls.keys()` and sort their base source IDs.

In both CLI and MCP export flows:

```python
if dest == source or dest.is_relative_to(source):
    raise InvalidRequest("Destination must be outside the case directory.")
```

In `ingest_pdf_path`, call `resolved.stat().st_size` before `read_bytes()`.

Add a module logger in `mcp_server.py`; use `logger.exception("Unhandled tool error", exc_info=exc)` for unexpected exceptions. Narrow `packet_save` so only `ResearchPacket.model_validate(payload)` converts `ValidationError` to `PacketIncomplete`; malformed `run_id` remains `INVALID_REQUEST`.

Reject lead imports when the run is `COMPLETE` or `BLOCKED` so completed evidence records do not change.

- [x] **Step 4: Run focused checks**

Run: `uv run --locked pytest -q tests/test_cli.py tests/test_failure_paths.py tests/test_mcp_server.py tests/test_core.py`

Expected: PASS.

- [x] **Step 5: Review checkpoint**

Run: `uv run --locked ruff check src/srd/delta.py src/srd/cli.py src/srd/pdfs.py src/srd/mcp_server.py && uv run --locked mypy src`

Expected: PASS; do not commit.

---

### Task 5: Replace the toy fixture with a substantive stewardship dossier

**Files:**
- Modify: `tests/fixtures/case_001/S-0001.txt`
- Modify: `tests/fixtures/case_001/S-0002.txt`
- Create: `tests/fixtures/case_001/S-0003.txt`
- Modify: `tests/fixtures/case_001/sources.json`
- Delete: `tests/fixtures/case_002/S-0003.txt`
- Modify: `tests/fixtures/case_002/S-0004.txt`
- Create: `tests/fixtures/case_002/S-0005.txt`
- Create: `tests/fixtures/case_002/S-0006.txt`
- Modify: `tests/fixtures/case_002/sources.json`
- Modify: `src/srd/cli.py`
- Modify: `tests/test_fixture_demo.py`
- Modify: `docs/demo-review.md`

**Interfaces:**
- Consumes: `EvidenceCitation`, evidence-rich brief rendering, and four-way delta.
- Produces: two offline Microsoft AI-governance runs with one unchanged, superseded, added, and withdrawn source.

- [x] **Step 1: Write the dossier acceptance test before changing fixtures**

Assert the generated artifacts include all of:

```python
assert "Environmental, Social, and Public Policy Committee" in first_brief
assert "public disclosure does not establish operating effectiveness" in first_brief.lower()
assert "> [S-" in first_brief
assert "## Withdrawn" in delta_markdown
assert all(delta.model_dump()[key] for key in ("added", "withdrawn", "superseded", "unchanged"))
assert "investment recommendation" not in combined.lower()
assert "engagement recommendation" not in combined.lower()
assert "voting recommendation" not in combined.lower()
```

- [x] **Step 2: Run the fixture test and verify failure**

Run: `uv run --locked pytest -q tests/test_fixture_demo.py`

Expected: FAIL because the current excerpts and delta are too shallow.

- [x] **Step 3: Freeze bounded official-source excerpts**

Use only these official URLs in fixture metadata:

```text
https://www.microsoft.com/en-us/Investor/corporate-governance/framework
https://www.microsoft.com/en-us/corporate-responsibility/reporting-governance
https://www.microsoft.com/investor/reports/ar24/
https://www.microsoft.com/en-us/corporate-responsibility/responsible-ai-transparency-report/
```

Run 1 contains framework, reporting-governance, and annual-report excerpts. Run 2 contains the unchanged reporting-governance excerpt, a changed capture of the framework URL, and the added Responsible AI report; the annual-report URL is withdrawn. Record exact capture timestamps and recompute SHA-256 values from each UTF-8 fixture file.

- [x] **Step 4: Write a decision-useful deterministic packet**

Update `run_fixture_demo` to use the approved question and citation excerpts copied exactly from fixture text. The thesis is limited to disclosed board-level mechanisms. The counter-view states that the public materials describe structures and processes but do not establish operating effectiveness or outcomes. The lead implication names the unresolved question: whether the board receives evidence sufficient to test the effectiveness of AI-risk controls.

- [x] **Step 5: Run and inspect the fixture**

Run:

```bash
demo_root=$(mktemp -d /tmp/srd-demo.XXXXXX)
uv run --locked pytest -q tests/test_fixture_demo.py
uv run --locked srd fixture-demo --offline --root "$demo_root"
sed -n '1,240p' "$demo_root/fixture-governance-2026/runs/0001/brief.md"
sed -n '1,240p' "$demo_root/fixture-governance-2026/runs/0002/brief.md"
sed -n '1,240p' "$demo_root/fixture-governance-2026/runs/0002/delta-from-0001.md"
```

Expected: PASS; excerpts and locators make every finding directly traceable; the counter-view challenges operating-effectiveness inference; all four delta classes appear.

- [x] **Step 6: Apply the independent reviewer rubric**

Record each of the six rubric answers and elapsed time in `docs/demo-review.md`. If no independent reviewer is available during implementation, mark this gate `UNVERIFIED` and do not claim candidate-demo readiness.

- [x] **Step 7: Review checkpoint**

Run: `git diff --check && uv run --locked pytest -q tests/test_fixture_demo.py tests/test_plugin_files.py`

Expected: PASS; do not commit.

---

### Task 6: Run integration, live-source, and host gates

**Files:**
- Modify: `README.md`
- Modify: `docs/demo-review.md`
- Modify: `specs/2026-08-14-stewardship-research-dossier-prd.md`
- Modify: `specs/2026-08-14-stewardship-research-dossier-spec.md`
- Modify: `plans/2026-08-14-stewardship-research-dossier.md`

**Interfaces:**
- Consumes: all upgraded runtime behavior.
- Produces: a factual verification record separating automated, live-network, host, and independent-review evidence.

- [x] **Step 1: Run the complete automated gate**

Run:

```bash
uv lock --check
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src
doctor_root=$(mktemp -d /tmp/srd-doctor.XXXXXX)
uv run --locked srd doctor --root "$doctor_root"
uv run --locked pytest -q tests/test_mcp_stdio.py
sh -n bin/srd-mcp
git diff --check
```

Expected: every command exits zero. Record exact test counts and warnings without calling local checks production proof.

- [x] **Step 2: Run one pinned live-source capture**

Capture `https://www.nbim.no/en/news-and-insights/strategy-for-the-fund-management/strategy-28/` into a fresh `/tmp` case root through `collect_sources`. Assert and record: state `SYNTHESIS_PENDING`, non-empty source ID, real title containing `Strategy 28`, final HTTPS URL on `www.nbim.no`, positive character count, and no error.

- [x] **Step 3: Run the non-persistent Claude host gate**

Run `claude --plugin-dir .` with a temporary `SRD_ROOT`. The gate passes only if the host loads the plugin, lists the MCP tools, and completes one `case_open` call. If the configured model fails before MCP startup, record the exact failure and leave Claude `UNVERIFIED`.

- [x] **Step 4: Stop at the Codex configuration gate unless separately authorised**

Do not execute these commands without a new explicit user approval:

```bash
codex plugin marketplace add "$REPO_ROOT" --json
codex plugin add stewardship-research-dossier@stewardship-research-dossier-local --json
codex plugin list
```

Record Codex as `UNVERIFIED` when approval is absent.

- [x] **Step 5: Update public wording and copied design records**

Document the evidence-citation contract, static-only retrieval, four-way delta, exact checks, and remaining unverified gates. Remove rendered-retrieval and memory claims. Preserve “candidate prototype” wording and state that NBIM neither requested, uses, nor endorses it.

- [x] **Step 6: Final review checkpoint**

Run:

```bash
uv lock --check
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src
git diff --check
git status --short
```

Expected: all automated checks pass; modified/untracked files are limited to this upgrade; no commit, push, installation, or external write occurred.

## Definition of done

1. Every material packet finding has a same-run source, locator, and verbatim excerpt validated against captured text.
2. The generated Microsoft case contains a substantive counter-view and all four evidence-delta classes.
3. Public static collection pins the validated address and preserves Host/TLS identity; optional rendered retrieval is absent.
4. Export, PDF size, artifact, chronological comparison, connection lifetime, and unexpected-error paths have focused passing tests.
5. Full lock/test/lint/format/type/MCP/fixture checks pass.
6. Live NBIM capture is observed and recorded.
7. Host and independent-review claims are marked passed only when actually observed; otherwise they remain `UNVERIFIED`.
8. No deployment, adoption, production, investment-performance, or NBIM-endorsement claim is made.
