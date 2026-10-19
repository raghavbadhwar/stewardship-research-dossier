# Stewardship Research Dossier — Technical Specification

**Status:** implementation baseline; local verification is recorded in `docs/demo-review.md`.
**Companion documents:** [PRD](2026-08-14-stewardship-research-dossier-prd.md) · [implementation plan](../plans/2026-08-14-stewardship-research-dossier.md)

## 1. Technical decision

Use one Python 3.12 codebase and a locked `uv` environment. Ship thin Codex and Claude Code plugin wrappers around the same local stdio MCP process. The host supplies reasoning, web discovery, permissions and optional native subagents. The runtime supplies durable storage, static collection, PDF extraction, validation, packet rendering, and run comparison.

This is deliberately a **local-first CLI/MCP application**, not a service. SQLite plus run-scoped files is enough for a single-user candidate prototype.

## 2. System context

```text
                    ┌────────────────────────────────────┐
                    │  Codex or Claude Code (lead)        │
                    │  plans, searches, reviews, writes   │
                    └─────────────┬────────────────────────┘
                                  │ MCP calls / task cards
          ┌───────────────────────▼────────────────────────┐
          │ Stewardship Research Dossier local runtime      │
          │  stdio MCP + CLI                                │
          │                                                 │
          │ case store ─ source capture ─ packet ─ renderer │
          │        └──── delegation planner ─────┘          │
          └──────────────┬─────────────────────┬────────────┘
                         │                     │
                 static public web         local/public PDFs
                         │                     │
                         └──────────┬──────────┘
                                    ▼
               ~/.stewardship-research-dossier/cases/
```

The `delegation_plan` tool only returns structured task cards. It does not call a model, start a process, select a model or bypass host approval. The lead may decline the plan and perform the work itself.

## 3. Repository layout

```text
stewardship-research-dossier/
  .agents/plugins/marketplace.json
  .codex-plugin/plugin.json
  .claude-plugin/plugin.json
  .mcp.json
  bin/srd-mcp
  pyproject.toml
  uv.lock
  README.md
  skills/living-research/SKILL.md
  agents/
    filings-analyst.md
    event-scout.md
    competitive-analyst.md
    governance-analyst.md
    thesis-skeptic.md
    delta-analyst.md
  src/srd/
    __init__.py
    cli.py
    errors.py
    models.py
    store.py
    collection.py
    pdfs.py
    packets.py
    delta.py
    delegation.py
    mcp_server.py
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
    fixtures/
      case_001/
      case_002/
```

## 4. Runtime and dependencies

| Concern | Choice | Reason |
| --- | --- | --- |
| Language/runtime | Python 3.12 + `uv` | isolated, locked, easy local CLI/MCP launch |
| MCP | `mcp>=1.27,<2` | compatible with the installed Scrapling MCP generation; verify at lock time |
| Data validation | Pydantic v2 | small typed boundary for tool input and stored packets |
| HTTP | `httpx` | async static retrieval with timeouts |
| HTML extraction | `trafilatura` | local extraction of public HTML into readable text |
| PDF extraction | PyMuPDF | deterministic text extraction for public/local PDFs |
| Storage | Python `sqlite3` + files | no service or database dependency |
| Testing | pytest | focused behavioural checks |
| Lint/type | Ruff + mypy | simple static gates |

`Scrapling` is not a base dependency. If installed as an optional extra, it is used only after static fetch fails and the user explicitly requests rendered retrieval. Last30Days remains a host-side lead source; its output is never evidence until a primary URL is captured.

The bootstrap script runs `uv run --locked` from the plugin root. It can install the project’s locked dependencies in its isolated environment; it cannot install `uv`, access credentials, or alter Codex/Claude binaries. `srd doctor` must make a missing `uv` prerequisite explicit.

## 5. Case data model

### Local filesystem layout

```text
~/.stewardship-research-dossier/cases/<case-key>/
  dossier.sqlite
  runs/0001/
    request.json
    sources/S-0001.txt
    sources/S-0001.json
    handoffs/H-0001.json
    packet.json
    brief.md
  runs/0002/
    ...
    delta-from-0001.json
```

### SQLite tables

| Table | Primary key | Important fields |
| --- | --- | --- |
| `cases` | `case_key` | issuer name, question, theme, created timestamp |
| `runs` | `run_id` | case key, ordinal, state, reference date, created/completed timestamp |
| `sources` | `source_id` | run ID, URL, title, publisher, capture time, method, content hash, text path |
| `handoffs` | `handoff_id` | run ID, role, artifact path, status |
| `packets` | `packet_id` | run ID, artifact path, rendered brief path |

The source text and JSON sidecar are immutable after capture for a given run. A later capture produces a new source ID; it never changes the old file.

### Core Pydantic models

```python
class CaseOpenRequest(BaseModel):
    case_key: str
    issuer_name: str
    question: str
    theme: Literal["governance", "risk", "event", "competitive", "mixed"]
    reference_date: date

class SourceCapture(BaseModel):
    source_id: str
    url: AnyHttpUrl
    title: str
    publisher: str | None
    captured_at: datetime
    retrieval_method: Literal["static", "pdf", "rendered"]
    content_sha256: str
    text_path: str

class Finding(BaseModel):
    statement: str
    source_ids: list[str] = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]
    contradicts: list[str] = []

class ResearchPacket(BaseModel):
    thesis: list[Finding] = Field(min_length=1)
    counter_view: list[Finding] = Field(min_length=1)
    risks: list[Finding] = Field(min_length=1)
    open_questions: list[str] = Field(min_length=1)
    analyst_review_required: Literal[True] = True

class WorkerHandoff(BaseModel):
    run_id: str
    role: str
    sources: list[str]
    findings: list[Finding]
    open_questions: list[str]
    recommendations_for_lead: list[str]
```

`ResearchPacket` validation checks that every referenced source ID belongs to its run. It does not determine whether a statement is true; the lead remains accountable for synthesis.

## 6. State and failure semantics

```text
OPEN ──► COLLECTING ──► INVESTIGATING ──► SYNTHESIS_PENDING ──► COMPLETE
                  │              │                  │
                  └──────────────┴──────────────────┴────► PARTIAL
                                                     └────► BLOCKED
```

- `OPEN`: case/run exists but no source has been captured.
- `COLLECTING`: one or more sources are being retrieved.
- `INVESTIGATING`: optional worker handoffs are being recorded.
- `SYNTHESIS_PENDING`: captured sources exist but no valid packet is saved.
- `COMPLETE`: a valid packet and brief exist.
- `PARTIAL`: useful source/packet output exists with recorded failures or omissions.
- `BLOCKED`: no credible output can be made, for example the requested source is protected or all retrievals failed.

Every domain failure subclasses `SrdError` and contains a stable `code`, human message and optional source URL. Required errors: `CaseNotFound`, `CaseExists`, `InvalidStateTransition`, `SourceUnavailable`, `UnsupportedContentType`, `ExtractionFailed`, `PacketSourceMismatch`, `PacketIncomplete`, `RunNotComparable`, and `OptionalDependencyMissing`.

## 7. MCP contract

| Tool | Input | Success result | Failure behaviour |
| --- | --- | --- | --- |
| `case_open` | `CaseOpenRequest` | case and first run identifiers | invalid key/date returns `INVALID_REQUEST` |
| `source_collect` | case key, run ID, list of public URLs | captures plus per-URL result | each failed URL is explicit; remaining URLs continue |
| `filing_ingest` | case key, run ID, file path or public PDF URL | PDF source capture | bad path/PDF returns a named failure |
| `delegation_plan` | case key, run ID, case type, available worker cap | task cards and join rule | unsupported role/cap returns validation failure |
| `handoff_save` | `WorkerHandoff` | handoff ID/path | sources outside run are rejected |
| `packet_save` | `ResearchPacket` plus lead implication | packet ID/path | missing counter-view/risk/source binding is rejected |
| `brief_render` | case key, run ID | Markdown path and content | only valid packets render |
| `case_compare` | case key, base run, later run, lead implication | `EvidenceDelta` JSON and Markdown | incomplete/non-comparable runs are rejected |
| `case_export` | case key, destination | portable folder path | existing destination never overwrites silently |

The MCP response envelope is always:

```json
{"ok": true, "data": {}}
```

or:

```json
{"ok": false, "error": {"code": "SOURCE_UNAVAILABLE", "message": "…", "url": "…"}}
```

## 8. Collection and ingestion

`source_collect` accepts only `http`/`https` URLs. It uses an `httpx.AsyncClient` with a 15-second connect timeout, 30-second total response timeout, redirect limit of five, explicit content-size limit of 15 MB and at most four concurrent requests. It rejects responses outside 200–299, non-HTML/non-PDF content, private-address redirects and payloads above the limit.

For HTML, save response metadata and the extracted readable text. For PDF, call the same capture finaliser after `pdfs.py` extracts text. Empty extracted text records `EXTRACTION_FAILED`; it does not create an evidence source. Existing source URLs are recaptured per run, because the product must make the later evidence state visible.

No background crawling, credentialed retrieval, paywall bypass or generic search-engine scraping is in the runtime. Host web search discovers source URLs; a host skill may offer optional Last30Days leads and then capture primary sources through this contract.

## 9. Deterministic delegation planning

The planner uses explicit case type and source state, not an embedded LLM:

```python
PLAN_RULES = {
    "new_issuer": ["filings-analyst", "competitive-analyst", "thesis-skeptic"],
    "governance": ["governance-analyst", "filings-analyst", "thesis-skeptic"],
    "event": ["event-scout", "filings-analyst", "thesis-skeptic"],
    "refresh": ["delta-analyst"],
}
```

The output contains a task card per allowed worker:

```json
{
  "run_id": "acme-governance-2026:0001",
  "max_workers": 3,
  "join_rule": "Lead reviews structured handoffs and alone saves the research packet.",
  "tasks": [{
    "role": "governance-analyst",
    "objective": "Assess governance evidence relevant to the stated question.",
    "allowed_source_ids": ["S-0001", "S-0002"],
    "stop_condition": "Return when all allowed sources are assessed or no supported finding remains.",
    "handoff_schema": "WorkerHandoff"
  }]
}
```

The host skill chooses whether to launch task cards. A normal plan is capped at three; `mixed` accepts a cap of four only when the lead explicitly requests it.

### Host packaging

- **Claude Code:** plugin root contains `.claude-plugin/plugin.json`, `.mcp.json`, shared `skills/` and six task-card files under `agents/`. Each agent has read-only tools plus the local research MCP and omits the `Agent` tool, so it cannot create nested workers.
- **Codex:** plugin root contains `.codex-plugin/plugin.json`, `.mcp.json` and the same shared skill. The skill asks the main Codex session to launch dynamic task-specific native subagents from a returned plan. No global custom-agent configuration is silently written.
- **Both:** `bin/srd-mcp` starts the exact same `uv run --locked` server. Host-specific smoke tests verify manifest loading and tool listing.

## 10. Packet, brief and delta rules

`packet_save` requires at least one thesis finding, counter-view finding, risk finding, open question and lead-written `decision_implication`. It validates all source references, then writes a deterministic JSON packet. `brief_render` creates Markdown in a fixed section order. It does not call an LLM.

`case_compare` treats source content hashes as the evidence identity. It reports:

- `added`: source IDs absent from the base run;
- `superseded`: same canonical URL with a different hash in the later run;
- `unchanged`: same canonical URL and content hash;
- `lead_implication`: text supplied by the lead after comparing the new evidence.

The delta never claims that a thesis was automatically proven, disproven or materially changed.

## 11. Test and release gates

Run these locally before declaring the candidate prototype ready:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
uv run srd doctor
uv run srd fixture-demo --offline
```

The fixture demo must create two frozen runs, render a source-linked brief, record one counter-view, and produce a delta without network access. Plugin smoke tests must verify both host manifests can start the MCP server and list the documented tools. For Codex, the repository provides its own local marketplace manifest so it can be added through the documented marketplace flow; that host-wide registration is an explicitly approved manual test. No claim of production readiness is permitted after these local checks.

## 12. Known ceilings and later upgrades

The initial design deliberately has these ceilings: local single-user storage, host-provided discovery, static public-source retrieval, and rule-based delegation. Upgrade only after the v0 demo proves useful:

1. Optional rendered retrieval through Scrapling.
2. Additional public-filing adapters, starting with an explicit SEC helper.
3. An exportable case bundle and independently reviewed demo corpus.
4. Stronger provenance/replay controls only if an actual user needs them.

Do not add a web app, agent-orchestration framework, hosted vector database, broker, or customer-facing service merely because the repository grows.
