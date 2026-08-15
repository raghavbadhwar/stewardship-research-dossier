# Integrated Research Discovery and Analyst Approval Design

**Status:** Approved design, awaiting written-spec review  
**Date:** 2026-08-14  
**Target release:** 0.3.0 candidate research pilot

## Objective

Turn the Stewardship Research Dossier from an evidence-analysis engine that expects supplied URLs into a complete research product. From one request containing a company and research question, the host must discover institutional and recent sources, capture and read the evidence, construct a challenged draft, and pause for analyst approval before creating the canonical dossier.

The product remains a local candidate prototype. It does not make investment, engagement, voting, risk, or trading decisions and does not claim NBIM requested, uses, or endorses it.

## Product promise

Given an issuer, research question, reference date, and optional constraints, one invocation will:

1. Open or resume a local research run.
2. Plan the evidence coverage required by the question.
3. Discover primary, public-authority, independent, recent, and counter-evidence leads.
4. Use a fully vendored Last30Days engine as an integrated recent-signals lane.
5. Deduplicate, classify, rank, and persist all leads with discovery provenance.
6. Capture selected public evidence through the dossier's existing secure acquisition paths.
7. Read every captured source completely through bounded calls.
8. Produce a cited thesis, linked counter-view, risks, open questions, and structural diagnostics.
9. Persist a validated draft that survives host restarts.
10. Show the draft to the analyst and require explicit approval before canonical save and final rendering.

The ordinary workflow must not require the user to provide URLs.

## Confirmed product choices

- The default experience is a complete research run, not an evidence-only utility.
- Every run attempts an institutional evidence set: issuer or primary sources, relevant regulator or public-authority sources where available, credible independent recent reporting, and an explicit counter-evidence search.
- The system prepares a complete draft; the analyst approves or edits it before it becomes canonical.
- The complete upstream Last30Days source is included in the product rather than required as a separately installed plugin.
- Keyless recent discovery runs automatically. Credentials, browser cookies, helper installation, paid providers, publishing, and other privileged capabilities require separate consent and are not part of the default path.

## Approaches considered

### Host-native discovery only

Use host web search and browser tools, retaining Last30Days as an optional external plugin. This preserves the smallest runtime but fails the requirement that recent discovery be part of the product and remains host-capability dependent.

### Runtime search-provider connectors

Build direct search/news provider integrations into the dossier MCP. This creates a self-contained runtime but introduces new credentials, provider configuration, spend control, and vendor dependence while duplicating mature recent-signal work.

### Full vendored Last30Days plus an SRD adapter — selected

Ship a clean upstream snapshot and invoke it through a narrow SRD-owned adapter. This satisfies the self-contained-product requirement and preserves upstream capability, license, and test provenance. The cost is a materially larger repository and a deliberate upstream-refresh responsibility. Isolation is therefore mandatory: upstream code stays unchanged, and the ordinary SRD tool surface cannot silently activate privileged upstream paths.

## Upstream provenance and ownership

Implementation will import a clean archive from:

- Repository: `https://github.com/mvanhorn/last30days-skill`
- Local inspected version: `3.20.0`
- Local inspected commit: `0b35e0c2c8a1dc42b6f80db7d79af888eb268ed6`
- License: MIT, copyright 2026 Matt Van Horn
- Intended destination: `third_party/last30days/`

Before import, implementation must verify the live repository, release/tag, commit, license, and clean archive. The archive must exclude `.git`, virtual environments, Python caches, local configuration, credentials, generated output, and other machine state. It must retain the upstream source, tests, fixtures, manifests, documentation, lockfile, and license.

`THIRD_PARTY_NOTICES.md` will record repository, version, full SHA, license, import date, imported paths, excluded generated paths, and every local adaptation. The vendored tree remains byte-identical to the verified archive. SRD-specific changes live in the adapter, never as silent edits inside the vendor snapshot.

## Architecture

### 1. Research conductor

`skills/living-research/SKILL.md` becomes the host-native conductor for the complete workflow. It converts the request into an evidence plan, calls institutional host discovery and embedded recent discovery, closes coverage gaps, drives capture and reading, optionally uses bounded specialists, prepares the draft, asks for approval, and then renders and exports the canonical dossier.

The conductor reasons through host capabilities. The Python runtime remains deterministic and never calls an LLM or starts a worker.

### 2. Coverage plan and lead ledger

Each run persists a `research-plan.json` containing:

- issuer, question, theme, reference date, and optional constraints;
- planned search queries and their evidence bucket;
- bounded query and capture budgets;
- coverage status for primary, public-authority, independent-recent, and counter-evidence buckets;
- source or lead IDs satisfying each bucket;
- `not_applicable` or `unavailable` explanations where a bucket cannot be satisfied;
- named failures and the next gap query, if any.

The lead ledger extends the existing lead record with discovery query, discovery lane, source type, canonical URL, publication date when known, discovered time, snippet, engagement metadata when present, relevance rationale, and screening status. Leads remain untrusted and non-citable.

### 3. Institutional discovery lane

The conductor uses approved host search/browser tools to find issuer filings and governance material, regulator and public-authority material, credible independent reporting, and sources likely to challenge the emerging thesis. Search output is passed to `lead_import` with query and coverage provenance.

Web pages and search results are untrusted data. Their content cannot alter the conductor's instructions, request credentials, expand permissions, or become a finding before secure capture.

### 4. Embedded Last30Days lane

A new `recent_discover` MCP tool invokes the vendored engine as an isolated subprocess. The ordinary profile uses:

- `--emit=json --json-profile=raw`, so the adapter receives source records rather than upstream synthesis;
- `--days 30` and `--as-of` equal to the run reference date;
- `--no-browser-cookies`;
- `--search=reddit,hackernews,github` as the explicit keyless source allowlist;
- fixed maximum results and source-fetch bounds;
- a temporary HOME, configuration directory, working directory, and output directory;
- a minimal environment containing no API keys, auth tokens, cookie settings, project configuration, credential aliases, or user research state;
- a PATH that does not expose Keychain, `pass`, installers, publishers, or unrelated helper programs;
- no shell, fixed argument construction, a timeout, and stdout/stderr size limits.

The initial automatic source allowlist is Reddit, Hacker News, and GitHub. General web and official-source discovery remain in the host institutional lane so the default vendored subprocess does not fetch arbitrary result pages or become the canonical evidence collector.

The full upstream code is present, but the ordinary SRD adapter does not expose cookie extraction, Keychain or `pass` reads, API-key providers, X/TikTok/Instagram/LinkedIn credentials, local corpus ingestion, setup installers, publishing, HTML hosting, watchlists, delivery hooks, deep research, arbitrary source selection, or upstream persistent stores. A later explicitly consented design may expose selected extras; their presence in the vendor snapshot is not authorization to run them.

The adapter validates upstream JSON into SRD-owned models, rejects malformed or non-public URLs and oversized output, and converts acceptable items into untrusted lead records. Upstream ranking, engagement, snippets, and synthesis never bypass dossier capture or citation validation.

### 5. Secure evidence engine

Selected leads flow through the existing `source_collect`, `filing_ingest`, or caller-authorized `source_import_rendered` paths. The existing public-address checks, MIME and size limits, redirect handling, extraction, capture timestamp, final URL, SHA-256, exact text preservation, same-run citation binding, and excerpt validation remain authoritative.

Recent social or community items are discovery signals by default. A material governance or risk claim requires captured attributable evidence. A social item may support a finding only when the research question explicitly concerns public sentiment or community reaction and the item itself is captured with provenance.

### 6. Persisted draft and analyst approval

The canonical-save path becomes two-stage:

1. `packet_draft_save` validates the full packet, citations, excerpts, finding IDs, counter-links, coverage record, and decision implication, then writes a draft artifact and moves the run to `REVIEW_PENDING`.
2. `packet_draft_read` returns the validated draft for review or session resumption.
3. `packet_approve` records the analyst's explicit approval time and optional note, promotes the unchanged validated draft to the canonical packet, and permits final brief rendering.

The existing direct MCP `packet_save` path must not remain as an approval bypass. Internal fixture/test helpers may retain a lower-level save function, but the public host workflow uses draft and approval tools only.

The runtime cannot prove a human identity cryptographically. Its guarantee is procedural and auditable: the conductor must present the draft and may call `packet_approve` only after an explicit user response. The approval artifact records the supplied actor label, timestamp, draft hash, and note.

A partial draft can be reviewed but cannot be approved as complete unless the analyst explicitly accepts the named evidence gaps with a non-empty rationale. This override records the unresolved coverage and does not convert missing evidence into support.

## End-to-end data flow

```text
Company + question
  -> case/run + persisted research plan
  -> institutional host discovery
  -> isolated embedded Last30Days discovery
  -> unified lead ledger
  -> deduplication, classification and coverage screening
  -> targeted gap searches
  -> secure source capture
  -> full bounded source reads
  -> source-bound analysis and counter-view
  -> validated persisted draft
  -> analyst review/edit/approval
  -> canonical packet
  -> brief + diagnostics + export + later comparison
```

## Coverage and stopping rules

The conductor must attempt four evidence buckets:

1. **Primary:** issuer filing, governance document, policy, report, or other first-party disclosure relevant to the question.
2. **Public authority:** regulator, court, legislature, exchange, public standard-setter, or comparable authority when relevant and available.
3. **Independent recent:** credible attributable reporting or analysis dated within the research window when recent context is material.
4. **Counter-evidence:** a targeted search for facts, scope limits, contrary evidence, or missing operating-effectiveness evidence that could weaken the thesis.

A normal complete run requires at least three captured sources across at least two domains, at least one primary or public-authority source, and an explicit counter-evidence search. The coverage matrix, not a raw source quota, determines adequacy. A bucket may be `not_applicable` only with a question-specific explanation.

Discovery stops when all applicable buckets are satisfied and two consecutive targeted gap queries add no eligible source. It also stops at the bounded default ceiling of twelve search queries, fifty retained leads, and ten capture attempts. Reaching a ceiling with an unresolved required bucket produces a partial draft and named gap.

Every captured source must be read to completion. Every captured but uncited source remains visible in diagnostics. The system never hides retrieval failures or fills a missing bucket with model knowledge.

## MCP and model changes

The design adds or changes these public interfaces:

- `research_plan_save(run_id, payload)` — validate and persist the plan and coverage matrix.
- `recent_discover(run_id, topic, as_of, days=30)` — run isolated embedded recent discovery and persist typed leads.
- `packet_draft_save(run_id, payload, decision_implication)` — validate and persist a reviewable draft.
- `packet_draft_read(run_id)` — resume and inspect the persisted draft.
- `packet_approve(run_id, actor, note, accept_evidence_gaps=False)` — promote the exact draft hash after explicit approval.
- `run_inspect(run_id)` — additionally expose research-plan, coverage, recent-discovery, draft, and approval status without returning unbounded source text.
- `packet_save` — removed from or disabled on the public MCP surface to prevent approval bypass.

New typed records cover the research plan, coverage bucket, enriched discovery lead, recent-discovery result, draft status, and approval record. SQLite/file storage remains single-user and local; no server, cloud database, queue, scheduler, or agent framework is added.

## Failure semantics

The following failures are named and visible:

- `UPSTREAM_SNAPSHOT_MISMATCH` — vendored files do not match the recorded manifest.
- `DISCOVERY_UNAVAILABLE` — the embedded engine or required host discovery capability cannot run.
- `DISCOVERY_TIMEOUT` — the bounded subprocess exceeds its deadline.
- `DISCOVERY_OUTPUT_TOO_LARGE` — stdout or stderr exceeds its limit.
- `DISCOVERY_OUTPUT_INVALID` — upstream output fails JSON or typed validation.
- `COVERAGE_INCOMPLETE` — an applicable evidence bucket remains unresolved at the stop condition.
- `DRAFT_NOT_FOUND` — review or approval is requested without a saved draft.
- `DRAFT_NOT_APPROVABLE` — validation, coverage, hash, state, or approval requirements fail.

One discovery lane failing does not erase successful leads from the other lane. The conductor continues only when it can still satisfy coverage and otherwise creates a partial draft with the failure. Paywalls, robots restrictions, authentication requirements, and access controls are not bypassed.

## Security and privacy boundaries

- Treat upstream code as third-party executable code and review it at every refresh.
- Treat all retrieved content and upstream output as untrusted data.
- Never forward ambient credentials or browser state to the default subprocess.
- Never interpolate user text into a shell command.
- Never allow upstream output to choose local paths, commands, tools, permissions, or environment variables.
- Restrict default discovery to audited keyless adapters and bounded network behavior.
- Capture evidence through SRD before citation; Last30Days output is not an evidence store.
- Keep source text, leads, plans, drafts, approvals, packets, and exports local.
- Preserve analyst authority over canonical output and all consequential interpretation.

## Verification strategy

### Vendor and provenance checks

- Verify upstream repository, version, full commit SHA, MIT license, and clean archive before import.
- Generate a file manifest with SHA-256 hashes and test it on every repository gate.
- Confirm the vendored tree contains no `.git`, environment, credential, cache, or generated-output files.
- Run the upstream locked test suite in its own project environment without changing SRD dependencies.
- Record any failing or skipped upstream tests instead of silently weakening them.

### Adapter checks

- Use a fake upstream engine to prove fixed arguments, no shell, timeout, output limits, temporary directories, and environment allowlisting.
- Seed fake process secrets, project configuration, Keychain/`pass` executables, helper installers, and publisher commands; assert none are read or executed.
- Test valid, malformed, oversized, duplicate, private-URL, missing-date, partial-source, and no-result JSON outputs.
- Test deterministic lead normalization, classification, deduplication, ranking metadata, and persistence.
- Run one separately authorized live keyless discovery smoke test and record contacted sources and named failures.

### Workflow checks

- Exercise the complete MCP stdio protocol from `case_open` through discovery, capture, full reads, draft save/read, approval, rendering, diagnostics, comparison, and export.
- Prove an unapproved draft cannot render as canonical.
- Prove approval promotes the exact draft hash and that edits require a new draft and approval.
- Prove incomplete coverage cannot appear complete without an explicit analyst gap-acceptance rationale.
- Preserve all existing collection, provenance, citation, counter-view, diagnostics, and no-egress fixture tests.

### Product pilots

Run three fresh no-URL-input pilots:

1. **Stable governance:** primary governance and filing evidence with an operating-effectiveness counter-view.
2. **Recent event:** institutional sources plus embedded recent signals, with dates and independent corroboration.
3. **Difficult acquisition:** an online/local PDF and a static-extraction failure requiring an approved rendered artifact.

For each pilot require:

- the user supplies no URLs;
- applicable coverage buckets are satisfied or visibly unresolved;
- every source is captured, hashed, and read completely;
- every material finding has an exact captured excerpt;
- at least one counter-view links to a thesis;
- the draft survives a fresh host session;
- canonical output is impossible before analyst approval;
- diagnostics identify all uncited sources and open questions;
- no investment, engagement, voting, or trading recommendation appears.

An independent analyst who did not implement the system then measures time to draft, traceability, coverage, clarity, decision usefulness, one useful feature, and one material weakness. Product-level completion requires the analyst to complete the existing six review checks within five minutes after opening the exported dossier, with no unsupported material finding and ratings of at least 4/5 for clarity and usefulness.

## Migration and compatibility

- Bump the candidate capability version to `0.3.0` only after the new tool surface and vendor snapshot pass all gates.
- Refresh plugin manifests and lockfiles consistently.
- Update the conductor skill, README, tool diagrams, reviewer rubric, and demo record.
- Preserve existing cases and source/packet artifacts. Schema migration must be explicit and idempotent.
- Existing 0.2.0 runs without a research plan remain inspectable and comparable; they are labelled legacy rather than retroactively claiming coverage or approval.
- The installed Codex/Claude plugin caches require separate refresh authorization and real host verification.

## Non-goals

- Production deployment, multi-user collaboration, RBAC, cloud storage, dashboards, alerts, schedulers, or automatic outreach.
- Autonomous memory writes, prompt mutation, self-training, or evidence replacement.
- Automated materiality, truth, quality, investment, voting, engagement, or trading scores.
- Credential harvesting, access-control bypass, paywall bypass, or silent use of ambient machine secrets.
- Treating social engagement as proof of issuer conduct or operating effectiveness.

## Definition of done

The upgrade is done only when the vendored upstream snapshot is attributable and reproducible; the default adapter is proven keyless and isolated; a single request can complete discovery through draft without user-supplied URLs; evidence coverage and failures are visible; the draft persists; analyst approval gates canonical output; all local and host verification passes; and three independent product pilots meet the stated thresholds.

Until those checks pass, public wording remains “local candidate prototype” or “research-pilot candidate.”
