# Integrated Research Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one host request discover institutional and recent leads, preserve evidence coverage, create a persistent cited draft, and require explicit analyst approval before canonical rendering.

**Architecture:** Extend the existing artifact-backed `CaseStore`, typed Pydantic models, packet validation seam, and FastMCP server. Vendor Last30Days 3.21.0 unchanged at an immutable commit, invoke only its keyless raw-JSON path through a constrained subprocess adapter, and keep discovery output untrusted until the existing source-capture pipeline records it as evidence.

**Tech Stack:** Python 3.12, Pydantic 2, SQLite plus JSON/text artifacts, FastMCP, stdlib `subprocess`/`tempfile`/`hashlib`, pytest, Ruff, mypy, uv.

## Global Constraints

- The repository remains a local single-user candidate prototype; add no server, cloud database, dashboard, queue, scheduler, LangGraph, A2A, or agent framework.
- The Python runtime never calls an LLM, starts a host worker, makes a decision, executes a trade, reads ambient credentials, extracts browser cookies, or bypasses access controls.
- Last30Days is pinned to tag `v3.21.0`, commit `c7460f6114449ddfe6ea3fc2f23c3d910c0e740c`, and MIT license; its imported tree is unchanged.
- Automatic recent discovery is fixed to `reddit,hackernews,github`, raw JSON, 30 days, the run reference date, no browser cookies, temporary storage, bounded output, and no shell.
- Leads are untrusted and non-citable. Findings may cite only exact excerpts captured in the same run through SRD acquisition paths.
- Canonical packets and rendered briefs require a persisted draft plus explicit approval; evidence-gap acceptance requires a non-empty rationale.
- Preserve existing 0.2 cases and internal fixture helpers. Remove `packet_save` only from the public MCP surface.
- Do not commit, push, publish, install plugin caches, or run live discovery as part of local implementation.

---

### Task 1: Vendor the immutable Last30Days snapshot

**Files:**
- Create: `third_party/last30days/**`
- Create: `third_party/last30days.manifest.json`
- Create: `THIRD_PARTY_NOTICES.md`
- Create: `tests/test_vendor_snapshot.py`

**Interfaces:**
- Consumes: upstream Git tag `v3.21.0` dereferenced to commit `c7460f6114449ddfe6ea3fc2f23c3d910c0e740c`.
- Produces: unchanged vendor tree; manifest object `{repository, version, commit, license, files: {relative_path: sha256}}`.

- [ ] **Step 1: Write the failing vendor-integrity test**

```python
def test_last30days_vendor_tree_matches_manifest() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["version"] == "3.21.0"
    assert manifest["commit"] == "c7460f6114449ddfe6ea3fc2f23c3d910c0e740c"
    actual = {
        str(path.relative_to(VENDOR)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in VENDOR.rglob("*")
        if path.is_file()
    }
    assert actual == manifest["files"]
    assert not any(part in {".git", "__pycache__", ".venv"} for path in VENDOR.rglob("*") for part in path.parts)
```

- [ ] **Step 2: Run the test and verify the vendor artifact is missing**

Run: `uv run pytest tests/test_vendor_snapshot.py -q`
Expected: FAIL because `third_party/last30days.manifest.json` does not exist.

- [ ] **Step 3: Import and record the clean upstream archive**

Clone the exact tag into a temporary directory, verify `HEAD`, `pyproject.toml`, and `LICENSE`, export `git archive` into `third_party/last30days/`, and generate the manifest from every imported regular file. Record repository, tag, commit, license, import date, imported destination, and unchanged-tree policy in `THIRD_PARTY_NOTICES.md`. Do not copy `.git`, virtual environments, caches, local configuration, credentials, or generated output.

- [ ] **Step 4: Run the vendor test**

Run: `uv run pytest tests/test_vendor_snapshot.py -q`
Expected: PASS.

---

### Task 2: Add typed research plans, coverage, and an append-only lead ledger

**Files:**
- Modify: `src/srd/models.py`
- Modify: `src/srd/store.py`
- Modify: `src/srd/errors.py`
- Create: `tests/test_research_plan.py`
- Modify: `tests/test_leads.py`

**Interfaces:**
- Consumes: `CaseStore.run_path(run_id)` and existing `LeadCandidate` inputs.
- Produces: `CoverageBucket`, `ResearchQuery`, `ResearchPlan`, `PersistedLead`, `CaseStore.save_research_plan`, `CaseStore.load_research_plan`, `CaseStore.import_leads`, and `CaseStore.list_leads`.

- [ ] **Step 1: Write failing plan and ledger tests**

```python
def test_plan_requires_all_coverage_buckets_and_round_trips(tmp_path: Path) -> None:
    store, run_id = opened_run(tmp_path)
    plan = ResearchPlan.model_validate(valid_plan_payload(run_id))
    assert store.save_research_plan(run_id, plan).name == "research-plan.json"
    assert store.load_research_plan(run_id) == plan

def test_lead_import_appends_deduplicates_and_retains_provenance(tmp_path: Path) -> None:
    store, run_id = opened_run(tmp_path)
    first = store.import_leads(run_id, [host_lead("https://example.test/a")])
    second = store.import_leads(run_id, [host_lead("https://example.test/a")])
    assert first[0].lead_id == "L-0001"
    assert second[0].lead_id == "L-0001"
    assert len(store.list_leads(run_id)) == 1
```

- [ ] **Step 2: Run the focused tests and verify missing types/methods fail**

Run: `uv run pytest tests/test_research_plan.py tests/test_leads.py -q`
Expected: FAIL because the plan models and store methods do not exist and `import_leads` returns a path.

- [ ] **Step 3: Implement the minimum typed artifact model**

Add four exact bucket keys (`primary`, `public_authority`, `independent_recent`, `counter_evidence`), statuses (`planned`, `satisfied`, `not_applicable`, `unavailable`), source/lead IDs, and a required explanation for non-satisfied terminal statuses. Validate run binding, positive budgets capped at 12 queries/50 leads/10 captures, and unique query IDs. Persist plans atomically as `research-plan.json`.

Extend lead inputs with optional query, lane, source type, publication/discovery timestamps, snippet/engagement, relevance rationale, and screening status. Normalize URLs by lowercasing scheme/host and removing fragments, assign stable `L-####` IDs, append without erasing prior leads, and deduplicate by canonical URL.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_research_plan.py tests/test_leads.py -q`
Expected: PASS.

---

### Task 3: Add the isolated recent-discovery adapter

**Files:**
- Create: `src/srd/recent.py`
- Modify: `src/srd/errors.py`
- Create: `tests/test_recent.py`

**Interfaces:**
- Consumes: `discover_recent(vendor_root: Path, topic: str, as_of: date, days: int = 30, *, runner: Callable[..., CompletedProcess[str]] = subprocess.run)`.
- Produces: `RecentDiscoveryResult(leads: list[LeadCandidate], failures: list[str])` and named discovery errors.

- [ ] **Step 1: Write failing isolation and parsing tests**

```python
def test_recent_discovery_uses_fixed_keyless_isolated_contract(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    result = discover_recent(VENDOR, "Acme governance", date(2026, 8, 14), runner=fake_runner(calls, RAW_JSON))
    call = calls[0]
    assert call["shell"] is False
    assert "--json-profile=raw" in call["args"]
    assert "--search=reddit,hackernews,github" in call["args"]
    assert "--no-browser-cookies" in call["args"]
    assert call["env"].keys() <= {"HOME", "XDG_CONFIG_HOME", "TMPDIR", "PATH", "PYTHONUTF8", "LC_ALL"}
    assert [str(lead.url) for lead in result.leads] == ["https://example.test/item"]

def test_recent_discovery_rejects_oversized_or_invalid_output() -> None:
    with pytest.raises(DiscoveryOutputInvalid):
        discover_recent(VENDOR, "Acme", date(2026, 8, 14), runner=invalid_json_runner)
```

- [ ] **Step 2: Run tests and verify the adapter is missing**

Run: `uv run pytest tests/test_recent.py -q`
Expected: FAIL because `srd.recent` does not exist.

- [ ] **Step 3: Implement the constrained subprocess boundary**

Use the current absolute Python executable and vendored `skills/last30days/scripts/last30days.py`; reject blank/oversized topics and days outside 1–30; build a fixed argument list; create temporary HOME/config/output/bin directories; pass only the six allowlisted environment keys; use `shell=False`, `check=False`, text capture, a 90-second timeout, and 5 MiB stdout/256 KiB stderr postconditions. Map timeout, nonzero exit, invalid JSON, and oversized output to named SRD errors. Parse only public HTTP(S) rows from the raw per-source lists and convert them to untrusted `LeadCandidate` values; ignore upstream prose and synthesis.

- [ ] **Step 4: Run focused adapter tests**

Run: `uv run pytest tests/test_recent.py -q`
Expected: PASS.

---

### Task 4: Implement persistent draft, coverage gate, and explicit approval

**Files:**
- Modify: `src/srd/models.py`
- Modify: `src/srd/store.py`
- Modify: `src/srd/packets.py`
- Modify: `src/srd/errors.py`
- Create: `tests/test_packet_approval.py`
- Modify: `tests/test_core.py`

**Interfaces:**
- Consumes: `ResearchPlan`, `ResearchPacket`, existing citation validation, and internal `save_packet`.
- Produces: `save_packet_draft`, `load_packet_draft`, `approve_packet`, `DraftRef`, `ApprovalRecord`, state `REVIEW_PENDING`, and approval-gated canonical rendering.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_draft_survives_reload_and_cannot_render_before_approval(tmp_path: Path) -> None:
    store, run_id, packet = synthesis_run_with_complete_plan(tmp_path)
    draft = save_packet_draft(store, run_id, packet, "Review it.")
    assert CaseStore(tmp_path).load_packet_draft(run_id).draft_sha256 == draft.draft_sha256
    with pytest.raises(PacketNotApproved):
        render_brief(store, run_id)

def test_approval_promotes_exact_draft_hash(tmp_path: Path) -> None:
    store, run_id, packet = synthesis_run_with_complete_plan(tmp_path)
    draft = save_packet_draft(store, run_id, packet, "Review it.")
    approval = approve_packet(store, run_id, "analyst", "Approved")
    assert approval.draft_sha256 == draft.draft_sha256
    assert load_packet(store, run_id)[0] == packet

def test_incomplete_coverage_requires_explicit_rationale(tmp_path: Path) -> None:
    store, run_id, packet = synthesis_run_with_incomplete_plan(tmp_path)
    save_packet_draft(store, run_id, packet, "Review it.")
    with pytest.raises(DraftNotApprovable):
        approve_packet(store, run_id, "analyst", "", accept_evidence_gaps=True)
```

- [ ] **Step 2: Run focused tests and verify draft behavior is absent**

Run: `uv run pytest tests/test_packet_approval.py -q`
Expected: FAIL because the draft and approval interfaces do not exist.

- [ ] **Step 3: Implement two-stage packet persistence**

Factor existing packet validation into one shared helper. Save canonical JSON bytes plus decision implication to `packet-draft.json`, compute SHA-256 over those exact bytes, and transition `SYNTHESIS_PENDING` or `PARTIAL` to `REVIEW_PENDING`. Reload and revalidate the draft from disk. Approval requires actor and note, verifies the current bytes still match the draft hash, enforces coverage or a non-empty evidence-gap rationale, writes `approval.json`, and promotes the exact validated draft through the internal canonical save seam. Rendering raises `PACKET_NOT_APPROVED` unless an approval artifact and canonical packet exist. Preserve internal fixture saves for legacy 0.2 tests.

- [ ] **Step 4: Run packet and core tests**

Run: `uv run pytest tests/test_packet_approval.py tests/test_core.py -q`
Expected: PASS.

---

### Task 5: Expose the integrated MCP workflow and update the host conductor

**Files:**
- Modify: `src/srd/mcp_server.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_mcp_stdio.py`
- Modify: `skills/living-research/SKILL.md`

**Interfaces:**
- Consumes: store plan/lead methods, `discover_recent`, and packet draft/approval functions.
- Produces: public tools `research_plan_save`, `recent_discover`, `packet_draft_save`, `packet_draft_read`, and `packet_approve`; removes public `packet_save`; extends `run_inspect`.

- [ ] **Step 1: Change MCP tests first**

Update the expected tool set to include the five new tools and exclude `packet_save`. Add one real MCP flow that saves a plan, imports fake recent results through an injected adapter boundary, saves/reads a draft, proves `brief_render` fails before approval, approves it, and renders it. Assert `run_inspect` includes bounded plan, lead, draft, and approval status without source text.

- [ ] **Step 2: Run MCP tests and verify the public contract fails**

Run: `uv run pytest tests/test_mcp_server.py tests/test_mcp_stdio.py -q`
Expected: FAIL because the new tools are missing and `packet_save` is still public.

- [ ] **Step 3: Implement the public tool surface**

Validate every tool input with Pydantic/domain validators, return existing envelopes, persist recent results through the lead ledger, and expose only bounded status metadata from `run_inspect`. Use an optional `recent_runner` dependency on `create_server` for deterministic tests while defaulting to the real adapter. Replace the 15-line conductor with the approved one-request coverage/discovery/capture/read/draft/review/approval sequence and explicit stop budgets. Keep host search as the institutional lane and Last30Days as recent-signal discovery only.

- [ ] **Step 4: Run MCP tests**

Run: `uv run pytest tests/test_mcp_server.py tests/test_mcp_stdio.py -q`
Expected: PASS.

---

### Task 6: Version, document, and verify the complete local product

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `.codex-plugin/plugin.json`
- Modify: `.claude-plugin/plugin.json`
- Modify: `README.md`
- Modify: `docs/demo-review.md`
- Modify: `docs/pilot/reviewer-rubric.md`
- Modify: `tests/test_plugin_files.py`
- Create: `docs/pilot/integrated-discovery-demo.md`

**Interfaces:**
- Consumes: completed 0.3.0 tool surface and verification evidence.
- Produces: aligned 0.3.0 metadata, accurate product documentation, and a reproducible offline demo record.

- [ ] **Step 1: Update metadata tests first**

Require the project and both host manifests to report `0.3.0`, and require the README to describe discovery as untrusted lead generation plus analyst approval rather than autonomous evidence synthesis.

- [ ] **Step 2: Run plugin-file tests and verify version mismatch**

Run: `uv run pytest tests/test_plugin_files.py -q`
Expected: FAIL while metadata remains 0.2.0.

- [ ] **Step 3: Align version and documentation**

Set all declared versions to 0.3.0, refresh `uv.lock`, document the one-request host workflow, exact default sources, evidence/approval boundaries, vendor provenance, offline versus live verification, and the fact that host plugin caches were not refreshed. Add a local offline demo transcript using fake discovery output; do not claim live-source or NBIM validation.

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
uv lock --check
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Expected: lock check passes; all tests pass; Ruff reports no lint or format failures; mypy reports no issues.

- [ ] **Step 5: Record intentionally separate checks**

Do not run live keyless discovery, host-cache installation, or independent analyst pilots without their separate authorization. Report them as unverified product-level gates, not as local failures and not as completed work.
