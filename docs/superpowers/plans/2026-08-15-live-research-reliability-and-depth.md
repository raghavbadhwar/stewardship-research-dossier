# Live Research Reliability and Depth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the live dossier workflow reliably collect multiple evidence batches, expose source failures, assess unapproved drafts, capture official documents without bypassing controls, and produce an institutionally useful evidence-depth assessment.

**Architecture:** Adapt the existing `CaseStore`, bounded collector, packet lifecycle, diagnostics, FastMCP tools, and living-research conductor. Keep network acquisition and host-assisted imports as explicit evidence boundaries; add no service, agent framework, database, scheduler, credential dependency, or autonomous decision layer.

**Tech Stack:** Python 3.12, asyncio, httpx, Pydantic 2, SQLite plus JSON/text artifacts, PyMuPDF, FastMCP, pytest, Ruff, mypy, uv.

## Global Constraints

- Preserve the local, single-user candidate-prototype scope and the existing same-run citation rule.
- Never bypass authentication, robots restrictions, HTTP denials, rate limits, private-network checks, redirect limits, MIME checks, or the 15 MiB capture ceiling.
- Leads remain untrusted and non-citable; `satisfied` coverage requires captured same-run evidence, not a discovered lead.
- The runtime never calls an LLM, starts host workers, makes a voting/investment/engagement decision, executes a trade, or reads ambient credentials.
- The host lead remains the only canonical packet writer; an analyst remains the only approval authority.
- Preserve existing cases and packet JSON compatibility by giving new packet fields safe defaults.
- Use existing dependencies and stdlib facilities. Do not add a framework or package.
- Run focused tests before full gates. Do not commit, push, publish, install/refresh plugin caches, or modify the saved NVIDIA run without separate explicit authorization.

---

## File Map

- `src/srd/mcp_server.py`: async MCP boundary, structured tool envelopes, explicit collection finish.
- `src/srd/collection.py`: bounded capture only; no lifecycle completion side effect; compliant request headers and bounded retry semantics.
- `src/srd/store.py`: state transitions and captured-source validation used by coverage/depth gates.
- `src/srd/models.py`: structured capture error, issue-depth schema, packet evidence gaps, assessment status, challenge links, diagnostic stage.
- `src/srd/diagnostics.py`: canonical-or-draft diagnostics and coverage/depth observations.
- `src/srd/packets.py`: packet validation, evidence-depth approval gate, and complete cited rendering.
- `src/srd/pdfs.py`: approved local PDF import with original public-source provenance.
- `src/srd/recent.py`: keep partial discovery explicit; preserve successful lanes when Reddit is rate-limited.
- `skills/living-research/SKILL.md`: issue matrix, longitudinal/peer research, evidence-quality rules, displayed draft format, and stop conditions.
- `tests/`: focused regression coverage plus real stdio MCP verification.
- `docs/pilot/`: updated reviewer rubric and a fresh live-pilot script.

---

### Task 1: Repair the real MCP collection boundary and expose per-URL failures

**Files:**
- Modify: `src/srd/mcp_server.py:1-105`
- Modify: `src/srd/models.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_mcp_stdio.py`

**Interfaces:**
- Consumes: existing synchronous `collect_sources(store, run_id, urls)`.
- Produces: async MCP tool `source_collect`; result items shaped as `{url, source, error}` where `error` is `null` or `{code, message, url}`.

- [ ] **Step 1: Add a real stdio regression that reproduces the event-loop failure without network egress**

Extend the existing `exercise()` in `tests/test_mcp_stdio.py` after `case_open`:

```python
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
```

- [ ] **Step 2: Run the stdio regression and confirm the reproduced failure**

Run: `uv run pytest tests/test_mcp_stdio.py -q`

Expected before implementation: FAIL because the MCP result is `INTERNAL_ERROR` and stderr contains `asyncio.run() cannot be called from a running event loop`.

- [ ] **Step 3: Make only the MCP adapter asynchronous**

Import `asyncio`, define `source_collect` as `async def`, and call the existing synchronous collector in a worker thread:

```python
@mcp.tool()
async def source_collect(run_id: str, urls: list[str]) -> dict[str, object]:
    try:
        run_id = validate_run_id(run_id)
        store = CaseStore(root)
        results = await asyncio.to_thread(collect_sources, store, run_id, urls)
        return _ok(
            [
                {
                    "url": result.url,
                    "source": result.source.model_dump(mode="json") if result.source else None,
                    "error": (
                        {
                            "code": result.error.code,
                            "message": result.error.message,
                            "url": result.error.url or result.url,
                        }
                        if result.error
                        else None
                    ),
                }
                for result in results
            ]
        )
    except Exception as error:
        return _error(error)
```

Do not refactor the collector into a second async API; the thread adapter is the smallest correct boundary for FastMCP 1.29.

- [ ] **Step 4: Update direct MCP tests for the structured error contract**

Add assertions for `code`, `message`, and `url`; keep unexpected exceptions redacted and logged by `_error`.

- [ ] **Step 5: Verify both MCP paths**

Run: `uv run pytest tests/test_mcp_server.py tests/test_mcp_stdio.py -q`

Expected: PASS; actual stdio invocation returns a named per-URL failure and no coroutine warning.

---

### Task 2: Keep collection open across batches and finish it explicitly

**Files:**
- Modify: `src/srd/collection.py:168-201`
- Modify: `src/srd/mcp_server.py:107-117`
- Modify: `tests/test_failure_paths.py`
- Modify: `tests/test_collection_security.py`
- Modify: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `CaseStore.begin_collection`, `CaseStore.list_sources`, and `CaseStore.transition`.
- Produces: repeatable `source_collect` calls while state is `COLLECTING`; `collection_finish(run_id)` moves to `SYNTHESIS_PENDING` with evidence or `BLOCKED` without evidence.

- [ ] **Step 1: Write a failing two-batch lifecycle test**

```python
def test_collection_stays_open_for_multiple_batches_until_finished(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body><p>Board oversight evidence.</p></body></html>",
        )

    transport = httpx.MockTransport(handler)
    first = collect_sources(
        store,
        run_id,
        ["https://example.test/one"],
        transport=transport,
        resolver=public_dns,
    )
    second = collect_sources(
        store,
        run_id,
        ["https://example.test/two"],
        transport=transport,
        resolver=public_dns,
    )
    assert first[0].source is not None and second[0].source is not None
    assert store.get_run(run_id).state == "COLLECTING"
    assert len(store.list_sources(run_id)) == 2
```

Add MCP assertions that `collection_finish` produces `SYNTHESIS_PENDING` when sources exist and `BLOCKED` when none exist.

- [ ] **Step 2: Run focused tests and confirm premature synthesis**

Run: `uv run pytest tests/test_failure_paths.py tests/test_collection_security.py tests/test_mcp_server.py -q`

Expected before implementation: FAIL on the second batch with `Cannot transition from SYNTHESIS_PENDING to COLLECTING`.

- [ ] **Step 3: Remove lifecycle completion from `collect_sources`**

Delete the post-collection transition at `src/srd/collection.py:196-200`. Return results while leaving the run in `COLLECTING`, including when every URL fails.

- [ ] **Step 4: Put completion policy in `collection_finish`**

After validating the state, choose the terminal research state from captured evidence:

```python
target = "SYNTHESIS_PENDING" if store.list_sources(run_id) else "BLOCKED"
return _ok(store.transition(run_id, target).model_dump(mode="json"))
```

Repeated `collection_finish` remains an invalid transition. Imports through `filing_ingest` and `source_import_rendered` remain open until the same explicit finish call.

- [ ] **Step 5: Verify collection and state-machine behavior**

Run: `uv run pytest tests/test_failure_paths.py tests/test_collection_security.py tests/test_mcp_server.py -q`

Expected: PASS; two batches plus an official-document import can precede one explicit finish.

---

### Task 3: Diagnose saved drafts and make evidence gaps first-class

**Files:**
- Modify: `src/srd/models.py:97-123,196-207,329-344`
- Modify: `src/srd/diagnostics.py`
- Modify: `src/srd/packets.py`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_packet_approval.py`

**Interfaces:**
- Produces: `ResearchPacket.evidence_gaps: list[str]`, `ResearchPacket.assessment_status: Literal["provisional", "inconclusive"]`, `DossierDiagnostics.packet_stage: Literal["draft", "canonical"]`, and canonical-or-draft `build_diagnostics`.

- [ ] **Step 1: Write failing draft-diagnostic and compatibility tests**

```python
def test_diagnostics_use_unapproved_draft_without_promoting_it(tmp_path: Path) -> None:
    store, run_id, packet = synthesis_run(tmp_path, complete=False)
    save_packet_draft(store, run_id, packet, "Review it.")
    result = build_diagnostics(store, run_id)
    assert result.packet_stage == "draft"
    assert store.packet_row(run_id) is None
    assert store.get_run(run_id).state == "REVIEW_PENDING"

def test_existing_packet_defaults_new_fields() -> None:
    legacy = packet("S-0001", "Material evidence.").model_dump(
        exclude={"evidence_gaps", "assessment_status"}
    )
    loaded = ResearchPacket.model_validate(legacy)
    assert loaded.evidence_gaps == []
    assert loaded.assessment_status == "provisional"
```

- [ ] **Step 2: Run focused tests and confirm `PACKET_INCOMPLETE`**

Run: `uv run pytest tests/test_diagnostics.py tests/test_packet_approval.py -q`

Expected before implementation: FAIL because diagnostics call only `load_packet`.

- [ ] **Step 3: Add backward-compatible packet and diagnostic fields**

Add the two packet fields with defaults. Add `packet_stage` to diagnostics. In `build_diagnostics`, load the canonical packet when `packet_row(run_id)` exists; otherwise load `load_packet_draft(store, run_id).packet`. Do not write, approve, promote, or render anything during diagnostics.

- [ ] **Step 4: Enforce truthful gap labelling at draft save**

In shared packet validation, load the research plan. If either `primary` or `public_authority` is not `satisfied`, require `assessment_status == "inconclusive"` and at least one non-empty evidence-gap entry naming the missing coverage. For complete official coverage, allow `provisional` or `inconclusive`.

- [ ] **Step 5: Render evidence gaps separately from open questions**

Update brief rendering so `## Evidence gaps` contains `packet.evidence_gaps`, followed by `## Open questions`. Preserve citations and approval metadata.

- [ ] **Step 6: Verify draft behavior and packet compatibility**

Run: `uv run pytest tests/test_diagnostics.py tests/test_packet_approval.py tests/test_core.py -q`

Expected: PASS; draft diagnostics work without weakening the approval gate.

---

### Task 4: Improve official-source capture without bypassing access controls

**Files:**
- Modify: `src/srd/collection.py:27-125`
- Modify: `src/srd/models.py:76-87`
- Modify: `src/srd/pdfs.py:27-42`
- Modify: `src/srd/recent.py:76-124`
- Modify: `src/srd/mcp_server.py:179-185`
- Modify: `tests/test_collection_security.py`
- Modify: `tests/test_failure_paths.py`
- Modify: `tests/test_recent.py`
- Modify: `tests/test_mcp_server.py`

**Interfaces:**
- Produces: stable public request headers; `PdfImportMetadata(url, title, publisher, captured_at)`; `ingest_pdf_path(store, run_id, path, metadata=None)`; optional `filing_ingest` metadata payload.

- [ ] **Step 1: Write failing request-header and PDF-provenance tests**

```python
def test_public_capture_sends_named_research_headers(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body><p>Official governance evidence.</p></body></html>",
        )

    collect_sources(
        store,
        run_id,
        ["https://issuer.example/report"],
        transport=httpx.MockTransport(handler),
        resolver=public_dns,
    )
    assert seen[0].headers["user-agent"].startswith("StewardshipResearchDossier/")
    assert "text/html" in seen[0].headers["accept"]

def test_pdf_import_retains_original_public_provenance(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    pdf_path = tmp_path / "proxy.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Official proxy evidence")
    document.save(pdf_path)
    document.close()
    source = ingest_pdf_path(store, run_id, pdf_path, PdfImportMetadata(
        url="https://issuer.example/proxy.pdf",
        title="2026 Proxy Statement",
        publisher="Example Issuer",
        captured_at=datetime(2026, 8, 15, tzinfo=UTC),
    ))
    assert str(source.url) == "https://issuer.example/proxy.pdf"
    assert source.title == "2026 Proxy Statement"
```

- [ ] **Step 2: Run focused tests and confirm missing behavior**

Run: `uv run pytest tests/test_collection_security.py tests/test_failure_paths.py tests/test_mcp_server.py -q`

Expected before implementation: FAIL because request headers are implicit and PDF imports use `file:` provenance.

- [ ] **Step 3: Add fixed, non-secret public request headers**

Set `User-Agent: StewardshipResearchDossier/<package-version> (local research prototype)` and an `Accept` header for HTML/PDF. Do not spoof a browser, fabricate contact details, forward cookies, or use ambient proxy credentials.

- [ ] **Step 4: Add provenance-preserving approved PDF import**

Validate optional metadata with Pydantic. When metadata exists, require its URL to pass the existing public-address check before `begin_collection`; save the extracted text under that public URL, title, publisher, capture time, and hash. Without metadata, retain the existing local `file:` behavior for fixtures and explicit local documents.

- [ ] **Step 5: Define bounded rate-limit behavior**

For static collection, retry once only for `429` or `503` when `Retry-After` is an integer from 1 through 30 seconds; otherwise return the named failure immediately. Never retry `403`, bypass the origin, or exceed existing timeout/size/redirect/concurrency limits. Inject the wait callable in focused tests so no test sleeps.

- [ ] **Step 6: Preserve partial recent discovery when Reddit returns 429**

Add a parser regression in `tests/test_recent.py` whose raw payload contains Hacker News and GitHub items plus `errors_by_source.reddit = "HTTP 429: Too Many Requests"`. Assert the successful leads remain present and the Reddit failure is preserved. Do not add blind sleep/retry behavior because the current raw contract does not expose a machine-readable `Retry-After`; add one bounded retry only if that contract is later supplied and tested.

- [ ] **Step 7: Verify security invariants**

Run: `uv run pytest tests/test_collection_security.py tests/test_failure_paths.py tests/test_recent.py tests/test_mcp_server.py -q`

Expected: PASS, including private redirect rejection, no-cookie/no-proxy behavior, 15 MiB rejection, public provenance, and bounded retry tests.

---

### Task 5: Add an enforceable research-depth and evidence-quality gate

**Files:**
- Modify: `src/srd/models.py:236-328`
- Modify: `src/srd/store.py:407-425`
- Modify: `src/srd/packets.py`
- Modify: `src/srd/diagnostics.py`
- Modify: `tests/test_research_plan.py`
- Modify: `tests/test_packet_approval.py`
- Modify: `tests/test_diagnostics.py`

**Interfaces:**
- Produces: `CoverageStatus` including `discovered`; `ResearchIssue`; `ResearchPlan.issues`; source-bound coverage validation; single-source/high-confidence validation; challenge links distinct from contradictions.

- [ ] **Step 1: Write failing coverage and depth tests**

```python
def test_leads_do_not_satisfy_evidence_coverage() -> None:
    bucket = CoverageBucket(status="discovered", lead_ids=["L-0001"])
    assert bucket.status == "discovered"
    with pytest.raises(ValidationError):
        CoverageBucket(status="satisfied", lead_ids=["L-0001"])

def test_satisfied_issue_requires_captured_evidence_and_history_status() -> None:
    issue = ResearchIssue.model_validate({
        "issue_id": "I-001",
        "topic": "Board independence and refreshment",
        "research_question": "Is the board composition adequate for the identified risks?",
        "materiality": "Board composition affects oversight capacity and accountability.",
        "status": "satisfied",
        "source_ids": ["S-0001"],
        "counter_source_ids": ["S-0002"],
        "historical_status": "satisfied",
        "periods": ["2024", "2025", "2026"],
    })
    assert issue.periods == ["2024", "2025", "2026"]
```

- [ ] **Step 2: Run focused tests and confirm the schema is absent**

Run: `uv run pytest tests/test_research_plan.py tests/test_packet_approval.py tests/test_diagnostics.py -q`

Expected before implementation: FAIL because lead-only satisfaction is currently allowed and `ResearchIssue` does not exist.

- [ ] **Step 3: Add the minimum issue-depth schema**

Define:

```python
class ResearchIssue(BaseModel):
    issue_id: str = Field(pattern=r"^I-[0-9]{3}$")
    topic: str = Field(min_length=1, max_length=160)
    research_question: str = Field(min_length=1, max_length=500)
    materiality: str = Field(min_length=1, max_length=1_000)
    status: Literal["planned", "discovered", "satisfied", "not_applicable", "unavailable"]
    source_ids: list[str] = Field(default_factory=list)
    counter_source_ids: list[str] = Field(default_factory=list)
    historical_status: Literal["planned", "satisfied", "not_applicable", "unavailable"]
    periods: list[str] = Field(default_factory=list, max_length=5)
    explanation: str | None = None
```

Require sources for `satisfied`; require at least three distinct periods when history is `satisfied`; require an explanation for `not_applicable` or `unavailable`. Add `issues: list[ResearchIssue] = Field(default_factory=list, max_length=12)` with unique issue IDs to `ResearchPlan` so stored pre-upgrade plans still load. Treat an empty issue list as depth-incomplete in diagnostics and approval; every newly saved host plan must contain 1–12 issues.

- [ ] **Step 4: Make coverage and issues evidence-bound**

Add `discovered` to coverage status. Require `satisfied` coverage to contain `source_ids`; lead IDs alone may support only `planned` or `discovered`. In `CaseStore.save_research_plan`, verify every referenced source ID belongs to the same run.

- [ ] **Step 5: Separate contradiction from challenge**

Add `Finding.challenges: list[str] = []`. A counter-view must contain at least one valid thesis ID across `contradicts` or `challenges`. Use `contradicts` only when two statements cannot both be true; use `challenges` when evidence limits the inference or adequacy assessment. Preserve legacy packets.

- [ ] **Step 6: Add objective confidence and approval rules**

Reject `high` confidence when a finding cites fewer than two distinct source IDs. Diagnostics must expose single-source findings, incomplete issues, missing historical coverage, and missing counter-source IDs. Approval with complete coverage requires all non-exempt issues satisfied. Evidence-incomplete approval still requires `accept_evidence_gaps=True`, a non-empty rationale, `assessment_status="inconclusive"`, and matching first-class evidence gaps.

- [ ] **Step 7: Verify depth and approval behavior**

Run: `uv run pytest tests/test_research_plan.py tests/test_packet_approval.py tests/test_diagnostics.py -q`

Expected: PASS; discovered leads cannot masquerade as evidence and depth deficiencies remain visible through approval.

---

### Task 6: Upgrade the analyst-facing dossier and host research conduct

**Files:**
- Modify: `src/srd/packets.py:220-279`
- Modify: `skills/living-research/SKILL.md`
- Modify: `tests/test_plugin_files.py`
- Modify: `tests/test_core.py`
- Modify: `docs/pilot/reviewer-rubric.md`

**Interfaces:**
- Consumes: research-plan coverage/issues, packet assessment status/evidence gaps, exact same-run citations, and diagnostics.
- Produces: a complete cited draft presentation and an evidence-depth research workflow.

- [ ] **Step 1: Add failing renderer and skill-contract tests**

Assert the rendered brief includes, in order: assessment status, coverage summary, thesis, counter-view, principal risks with citations, evidence gaps, open questions, decision implication, approval metadata, and evidence ledger. Assert the skill requires an issue matrix, longitudinal review, justified peer context, full relevant-section reads, claim/evidence/counter-evidence separation, and the explicit depth gate.

- [ ] **Step 2: Run focused tests and confirm missing sections/instructions**

Run: `uv run pytest tests/test_core.py tests/test_plugin_files.py -q`

Expected before implementation: FAIL because the renderer and conductor do not expose the full depth contract.

- [ ] **Step 3: Render a coverage and issue summary before findings**

Display each coverage bucket and research issue with status, same-run source IDs, historical status, periods, and explanation. Use the literal label `INCONCLUSIVE — EVIDENCE INCOMPLETE` whenever `assessment_status` is `inconclusive`.

- [ ] **Step 4: Preserve citations in every displayed finding section**

Render exact source ID, locator, and excerpt under thesis, counter-view, and principal-risk findings. Label one-source findings `single-source`. Render `Challenges` separately from `Contradicts`.

- [ ] **Step 5: Replace summary-first host conduct with issue-first research**

Update `skills/living-research/SKILL.md` to require:

1. A 1–12 issue matrix derived from the exact question.
2. Primary, public-authority, independent, and counter-evidence acquisition per material issue.
3. Three-period comparison when applicable, with `not_applicable` or `unavailable` explained.
4. Peer comparison only when the peer and mechanism are explicitly comparable; no rankings without a defined method.
5. Full bounded reads of relevant document sections rather than search-snippet synthesis.
6. Separate fields for verified facts, interpretation, conflicting evidence, materiality, and unresolved questions.
7. A falsification prompt: name the evidence that would weaken each material assessment.
8. `inconclusive` output whenever primary and authority evidence are both missing.
9. No approval recommendation until diagnostics and the displayed coverage/depth summary are shown.

- [ ] **Step 6: Update the reviewer rubric**

Score source authority, issue coverage, longitudinal depth, peer comparability, counter-evidence quality, citation fidelity, fact/inference separation, materiality, gap honesty, and approval discipline. Make any missing official coverage or uncited material claim an automatic revision condition, not a compensable score.

- [ ] **Step 7: Verify renderer and conductor contracts**

Run: `uv run pytest tests/test_core.py tests/test_plugin_files.py -q`

Expected: PASS; a reviewer can see why the assessment is deep, limited, or inconclusive without inspecting JSON.

---

### Task 7: Verify locally, refresh the host, and run one fresh product pilot

**Files:**
- Modify: `README.md`
- Modify: `docs/demo-review.md`
- Modify: `docs/pilot/integrated-discovery-demo.md`
- Create: `docs/pilot/live-research-reliability-and-depth.md`
- Modify version files only if implementation changes the public contract: `pyproject.toml`, `uv.lock`, `.codex-plugin/plugin.json`, `.claude-plugin/plugin.json`, `src/srd/__init__.py`

**Interfaces:**
- Produces: local quality evidence, actual host proof, and a reviewer-ready pilot record. Host refresh and live network work require separate explicit authorization at execution time.

- [ ] **Step 1: Run focused regressions together**

Run:

```bash
uv run pytest -q \
  tests/test_mcp_stdio.py \
  tests/test_mcp_server.py \
  tests/test_collection_security.py \
  tests/test_failure_paths.py \
  tests/test_diagnostics.py \
  tests/test_research_plan.py \
  tests/test_packet_approval.py \
  tests/test_core.py \
  tests/test_plugin_files.py
```

Expected: PASS with no `RuntimeWarning` and no unexpected `INTERNAL_ERROR`.

- [ ] **Step 2: Run the complete local quality gate**

Run:

```bash
uv lock --check
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run srd --version
uv run srd doctor
bash -n bin/srd-mcp
git diff --check
```

Expected: all commands exit zero; dependency-level warnings are recorded separately from failures.

- [ ] **Step 3: Inspect generated artifacts from an offline deep fixture**

The fixture must exercise two collection batches, at least four issues, three historical periods for one issue, a challenge link, first-class evidence gaps, draft diagnostics, approval, rendering, and evidence ledger hashes. Inspect JSON and Markdown directly; do not rely only on test assertions.

- [ ] **Step 4: Refresh and verify the actual Codex plugin only after explicit authorization**

Verify the loaded version, MCP `initialize`, tool listing, and an actual `source_collect` call against a local/private URL that must return a named rejection. Confirm the host no longer returns `INTERNAL_ERROR`.

- [ ] **Step 5: Run a fresh live issuer pilot only after explicit authorization**

Use a new run ID, not `nvidia-governance-2026:0001`. Require multiple capture batches, official-document fallback with public provenance, issue/coverage updates, full reads, draft diagnostics, and no approval. Record 403/429/oversize outcomes without bypasses.

- [ ] **Step 6: Apply the product acceptance gate**

The upgrade is product-validated only if:

- Actual stdio and actual host collection return structured per-URL results.
- At least two collection batches and one explicit finish succeed.
- Draft diagnostics work while the approval gate remains intact.
- Official-source denials have a provenance-preserving approved fallback or remain explicitly unavailable.
- Every material issue is satisfied, not applicable, or unavailable with a reason.
- Historical and peer claims meet the declared depth rules.
- Every displayed material claim retains a same-run citation.
- Missing official evidence forces `INCONCLUSIVE — EVIDENCE INCOMPLETE`.
- An independent reviewer can identify facts, interpretations, challenges, gaps, and the next research action in five minutes.

- [ ] **Step 7: Report truthfully and stop before release actions**

Report local verification, host verification, live-pilot evidence, remaining external limitations, and the dirty-worktree state separately. Do not commit, push, publish, approve a packet, or call the product complete without the corresponding explicit authorization and evidence.

---

## Self-Review Checklist

- [ ] The plan covers the reproduced MCP event-loop defect.
- [ ] The plan covers multi-batch collection and explicit completion.
- [ ] The plan preserves per-URL error code, message, and URL.
- [ ] The plan covers draft diagnostics without approval or promotion.
- [ ] The plan keeps the 15 MiB, SSRF, redirect, timeout, MIME, and access-control safeguards.
- [ ] The plan treats HTTP 403 and 429 as bounded external conditions, not invitations to bypass controls.
- [ ] The plan adds original public provenance for approved local PDF imports.
- [ ] The plan prevents leads from satisfying evidence coverage.
- [ ] The plan adds issue, history, counter-evidence, confidence, and challenge gates.
- [ ] The plan preserves citations in the analyst-facing risk section.
- [ ] The plan separates evidence gaps from open questions and forces inconclusive labelling.
- [ ] The plan includes focused, full-suite, stdio, host, live-pilot, and independent-review acceptance checks.
- [ ] No new dependency, service, database, framework, scheduler, credential, or autonomous decision authority is introduced.
