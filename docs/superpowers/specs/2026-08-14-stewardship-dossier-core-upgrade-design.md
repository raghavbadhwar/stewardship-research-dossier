# Stewardship Dossier Core Upgrade Design

**Status:** approved design for implementation planning
**Date:** 2026-08-14
**Product boundary:** local candidate prototype for Codex and Claude Code; not an NBIM product, production service, investment recommendation, or engagement decision engine

## Goal

Turn the existing technically credible prototype into a decision-useful research demo by making every material finding directly traceable to captured evidence, repairing the confirmed trust-boundary and persistence defects, replacing the toy fixture with one substantive stewardship case, and proving the workflow through a real host.

## Decision

Use a core-first upgrade. Preserve the local Python, SQLite, files, CLI, stdio MCP, and host-owned reasoning architecture. Adapt the existing models and modules; add no dependency or framework.

Keep the role-specific worker personalities because they add no runtime machinery. Remove the uncommitted agent-memory models, JSON store, MCP tools, task-card guidance, candidate-lesson fields, tests, and documentation. Reconsider procedural memory only after an independent reviewer finds the upgraded dossier useful.

## Alternatives considered

### Reliability-first

Resolve every automated-review item before improving the research artifact. This lowers technical debt first but delays the only output an analyst or portfolio reviewer can judge. Reject because several reported items conflict with the approved local-prototype contract and the current bottleneck is decision usefulness.

### Institutionalisation

Add authentication, access control, encryption, retention policy, immutable audit infrastructure, and hosted integrations. Reject because the repository is a single-user local candidate prototype and has no institutional sponsor, internal data, or deployment mandate.

## Scope

### Included

1. Remove the speculative runtime learning loop while retaining specialist personalities.
2. Add claim-level evidence citations with a source ID, locator, and bounded verbatim excerpt.
3. Validate citation excerpts against captured text before a packet can be saved.
4. Render findings with evidence excerpts and useful source metadata.
5. Add withdrawn evidence and chronological ordering to run comparison.
6. Pin validated public addresses during HTTP connections and preserve TLS verification.
7. Extract real HTML titles with the installed `trafilatura` dependency.
8. Remove optional rendered retrieval until its browser transport can enforce the same pinned-address invariant.
9. Prevent recursive case export and preflight local-PDF size before reading.
10. Move packet persistence and case lookup behind `CaseStore`; close connections on failures and expose named artifact errors.
11. Replace the tiny Microsoft fixture with a substantive, frozen AI-governance stewardship case.
12. Run repository, live-collection, Claude, and separately authorised Codex verification gates.

### Excluded

- Runtime or host-wide long-term memory.
- Semantic truth scoring, automated materiality decisions, investment recommendations, engagement recommendations, or voting decisions.
- A dashboard, web service, cloud database, scheduler, vector store, model call, or agent-orchestration framework.
- Credentialed sources, paywall bypass, private data, automatic outreach, deployment, or an NBIM adoption claim.
- Confining approved local PDF input to one directory. Local PDF access remains an explicit caller-authority boundary.
- Rejecting a delegation cap of zero. A host may choose a lead-only run.
- Treating a mixed-case cap above four as an implicit request for four workers. Four remains allowed only when explicitly requested.

## Architecture and file responsibilities

The existing module boundaries remain. No new production module is required.

| File | Responsibility after the upgrade |
| --- | --- |
| `src/srd/models.py` | `EvidenceCitation`, `Finding`, `ResearchPacket`, and `EvidenceDelta` schemas |
| `src/srd/store.py` | case/run/source/packet persistence, source text lookup, case metadata lookup, connection lifetime |
| `src/srd/collection.py` | public URL validation, pinned HTTP transport, redirect handling, extraction, source metadata |
| `src/srd/pdfs.py` | bounded local/public PDF extraction |
| `src/srd/packets.py` | packet validation orchestration and deterministic Markdown rendering using public `CaseStore` methods |
| `src/srd/delta.py` | ordered, offline comparison of packet-backed runs |
| `src/srd/mcp_server.py` | typed tool adapters, safe envelopes, unexpected-error logging |
| `src/srd/cli.py` | offline demonstration, doctor, and safe case export |
| `tests/` | one focused behavioural check for each changed invariant plus end-to-end proof |

`CaseStore` remains the only canonical writer. Packet rendering may read only through public store methods and may not execute SQLite statements directly.

## Evidence model

Add this required model:

```python
class EvidenceCitation(BaseModel):
    source_id: str
    locator: str = Field(min_length=1, max_length=160)
    excerpt: str = Field(min_length=1, max_length=800)
```

Change `Finding` to:

```python
class Finding(BaseModel):
    statement: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]
    contradicts: list[str] = Field(default_factory=list)
```

This is an intentional v0 schema break. There is no external compatibility promise, and retaining both `source_ids` and `citations` would create two conflicting sources of truth.

Before saving a packet, the runtime must:

1. Verify that every cited source belongs to the same run.
2. Read the captured source text through `CaseStore.read_source_text(run_id, source_id)`.
3. Collapse whitespace in the stored text and excerpt with `" ".join(value.split())`.
4. Reject the packet with `EvidenceExcerptMismatch(source_id)` unless the normalised excerpt is a substring of the normalised captured text.

The runtime validates provenance, not whether the finding follows logically from the excerpt. The host lead remains accountable for synthesis.

## Collection and network trust boundary

The existing resolve-then-connect flow leaves a second hostname resolution inside the HTTP client. Replace it with a small `httpx.AsyncBaseTransport` wrapper around the installed `httpx.AsyncHTTPTransport`:

1. Resolve the original hostname once with the injected resolver.
2. Reject an empty set, invalid address, or any non-global, multicast, reserved, loopback, link-local, or private address.
3. Select the first address after deterministic string sorting.
4. Send the transport-level request to the approved IP address.
5. Preserve the original authority in the `Host` header.
6. Set the request extension `sni_hostname` to the original hostname so TLS certificate verification remains bound to the public hostname.
7. Restore the original logical URL in the returned response.
8. Repeat the complete process for each redirect target, with a maximum of five redirects.

Tests inject both resolver answers and `httpx.MockTransport`; production never infers a safe resolver merely because a custom transport exists.

For HTML, call `trafilatura.extract_metadata(data)` and use its non-empty title and site name when available. Fall back to the final hostname only when metadata is absent. Keep the 15 MB streamed-response cap and existing MIME allowlist.

Remove `collect_rendered_source`, the `rendered_fallback` MCP parameter, and the optional Scrapling dependency group. Rendered retrieval is deferred because its browser-owned DNS connection cannot currently be pinned by this runtime. Static HTML and public/local PDF capture remain the complete v0 acquisition surface.

## Storage and failure semantics

Turn `CaseStore._db` into a context-managed internal helper so every successful and exceptional path closes its connection. Add public methods with typed return values:

```python
def get_case(self, case_key: str) -> CaseRef: ...
def read_source_text(self, run_id: str, source_id: str) -> str: ...
def save_packet_row(self, run_id: str, packet_id: str, artifact_path: Path) -> None: ...
def set_brief_path(self, run_id: str, brief_path: Path) -> None: ...
```

Use `MAX(CAST(SUBSTR(source_id, 3) AS INTEGER)) + 1` rather than `COUNT(*) + 1` for source IDs. Write source and packet content to sibling `.tmp` files, perform the database write inside a transaction, and atomically replace the final artifact before commit. On any exception, roll back and remove the temporary or newly created artifact without deleting a previously valid artifact.

Add named failures:

- `EvidenceExcerptMismatch(source_id)` for a citation excerpt absent from captured text.
- `ArtifactUnavailable(path)` for a missing or unreadable stored packet/source artifact.

The MCP envelope logs unexpected exceptions with traceback information to stderr and still returns only `INTERNAL_ERROR` plus the existing generic client message.

## Packet and brief output

The brief keeps its current fixed section order. Each finding renders as:

```markdown
- <statement> [S-0001, Board risk oversight]
  > <bounded verbatim excerpt>
```

Multiple citations render in their declared order. The evidence ledger shows the real page title, publisher when present, final URL, capture timestamp, retrieval method, and SHA-256. The brief continues to state `Analyst review required` and must not contain an automated recommendation.

## Evidence delta

`compare_runs` requires both runs to belong to the named case, be `COMPLETE` or `PARTIAL`, have packets, and satisfy `base.ordinal < later.ordinal`.

`EvidenceDelta` contains:

```python
class EvidenceDelta(BaseModel):
    added: list[str]
    withdrawn: list[str]
    superseded: list[tuple[str, str]]
    unchanged: list[str]
    lead_implication: str
```

Comparison remains offline and deterministic:

- added: a final URL exists only in the later run;
- withdrawn: a final URL exists only in the base run;
- superseded: the same final URL has a different content hash;
- unchanged: the same final URL has the same content hash.

The lead implication must be non-empty. The runtime does not infer what the change means.

## Safe export and local PDF ingestion

Resolve the source case and destination before copying. Reject a destination equal to or nested inside the source case with `Path.is_relative_to`. Preserve the existing destination-must-not-exist rule.

For local PDFs, check `resolved.stat().st_size` against 15 MB before `read_bytes()`. Do not add a path allowlist: the documented host workflow must obtain explicit approval for the named local file, and the runtime remains local and credential-free.

## Substantive demonstration case

Keep Microsoft to reuse the existing case shape and official public sources. The case question is:

> Do Microsoft’s public disclosures identify board-level oversight mechanisms for material AI-related risks, and what remains unresolved for stewardship review?

Freeze bounded excerpts with capture timestamps and hashes from exactly these official source families:

1. Microsoft Investor Relations corporate-governance framework.
2. Microsoft Corporate Responsibility reporting-governance page, which identifies the Environmental, Social, and Public Policy Committee's responsible-AI oversight remit.
3. Microsoft annual report risk disclosures.
4. Microsoft Responsible AI Transparency Report.

Run 1 must support a narrow thesis about disclosed oversight mechanisms and a substantive counter-view about the limits of public evidence on operating effectiveness. Run 2 must include one unchanged source, one superseded source, one added source, and one withdrawn source. Its lead implication must name the specific unresolved oversight question that should be investigated next without making an investment, engagement, or voting decision.

The frozen corpus stores only the excerpts necessary for the demo. It does not claim complete coverage of the issuer or independent verification of Microsoft’s practices.

## Verification design

Every non-trivial change follows one focused red/green test cycle. Tests must cover:

1. Citation source binding and verbatim-excerpt validation.
2. Brief rendering with locators, excerpts, and real metadata.
3. DNS rebinding prevention, private redirect rejection, explicit test resolver use, response-size limits, and peer URL preservation.
4. Descendant-export rejection and valid sibling export.
5. PDF size rejection before file reading.
6. Connection closure and cleanup after simulated SQLite/filesystem failures.
7. Source-ID stability after row deletion.
8. Self/reversed delta rejection and added/withdrawn/superseded/unchanged classification.
9. Safe MCP envelopes and stderr logging for unexpected exceptions.
10. Removal of agent-memory MCP tools and retention of worker personalities.
11. Offline fixture output and reviewer rubric.

The final automated gate is:

```bash
uv lock --check
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src
uv run --locked srd doctor
uv run --locked pytest -q tests/test_mcp_stdio.py
demo_root=$(mktemp -d /tmp/srd-demo.XXXXXX)
uv run --locked srd fixture-demo --offline --root "$demo_root"
sh -n bin/srd-mcp
git diff --check
```

Live verification captures the official NBIM Strategy 28 page through `collect_sources` into a fresh temporary root and records the title, final URL, state, source ID, character count, and absence of an error.

Claude verification uses `claude --plugin-dir .` without persistent installation and must reach MCP tool listing or a real MCP call. Codex marketplace addition and plugin installation remain a separate explicit approval gate because they change host configuration. A failed or unapproved host test is recorded as unverified, never inferred from manifest tests.

## Independent reviewer acceptance

Give the generated run-1 brief, run-2 brief, delta, and captured source files to a reviewer who did not implement the change. Without repository guidance, the reviewer must be able to complete all of these in under five minutes:

1. Trace every material finding to its exact source excerpt and locator.
2. State the thesis in one sentence.
3. Identify the counter-view and explain which thesis assumption it challenges.
4. Identify one added, withdrawn, superseded, and unchanged source.
5. State the unresolved oversight question named by the lead.
6. Confirm that the artifact makes no investment, engagement, or voting recommendation.

Failure of any item blocks the candidate-demo-ready claim even when automated tests pass.

## Delivery boundaries

The implementation may update the repository’s copied PRD/spec/plan and `docs/demo-review.md` to reflect observed behavior. The approved documents under `/Users/raghav/career-ops/docs/superpowers/` remain unchanged unless the user separately requests synchronisation.

No implementation step may commit, push, publish, deploy, install the Codex plugin, alter external records, or claim NBIM use or endorsement without explicit user approval.
