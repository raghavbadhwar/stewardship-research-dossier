# Living Research Dossier Runtime v0 — Superseded Design Note

> Superseded by [the NBIM-aligned product specification](2026-08-14-stewardship-research-dossier-spec.md) and [product requirements document](2026-08-14-stewardship-research-dossier-prd.md). This note records the earlier generic architecture decision only.

**Status:** superseded planning record; the local candidate prototype and verification record now live in this repository.
**Purpose:** Give Codex and Claude Code a shared, installed research capability that can turn an issuer or stewardship question into a source-backed dossier, then refresh it as evidence changes.

## Decision

Build one plugin codebase with thin Codex and Claude Code packages around a local, locked Python MCP runtime. The runtime owns durable research artifacts and bounded source tooling. The host owns model calls, permission prompts, and any native subagent creation.

This is not an investment-execution product, a generic CRM, or a free-running agent swarm. It is a research workspace for agents: collect evidence, form a thesis and counter-view, preserve the trail, and identify a material delta on a later run.

## Why the host must spawn subagents

An MCP server cannot safely or portably create a host's hidden agent processes. Instead, it emits a **delegation plan**. The shared skill gives that plan to the current host, which launches its own task-specific subagents using the host's supported mechanism and existing permissions.

That preserves each host's controls:

- **Codex:** a generic research-worker role receives a task card generated for this case. Codex configuration can provide the worker role and default limits; the main Codex session decides when to spawn it.
- **Claude Code:** the plugin ships a small set of read-only agent cards. The main session invokes the matching cards; agents use the parent research MCP and return a structured handoff. Claude subagents do not spawn further subagents.

The lead session is the only writer of the final case state. Workers may write only their own run-scoped handoff file, preventing concurrent edits to the current dossier.

## Adaptive delegation

The runtime selects only the work that the case needs, then returns a plan with a cap, source boundaries, and a join rule. It does not always launch every specialist.

| Case condition | Worker tasks | Normal cap |
| --- | --- | --- |
| New issuer / no dossier | filings, competition, thesis challenge | 3 |
| Event or earnings update | event scan, filings check, thesis challenge | 3 |
| Governance or stewardship question | governance review, filings check, thesis challenge | 3 |
| Routine refresh | event delta | 1 |
| Cross-domain, time-sensitive case | the above only as justified | 4 |

The available task cards are `filings-analyst`, `event-scout`, `competitive-analyst`, `governance-analyst`, `thesis-skeptic`, and `delta-analyst`. They are instructions, not a permanent organisation chart. A plan includes `max_workers`, a stop condition, allowed tools, per-worker source scope, and a required structured handoff:

```json
{
  "run_id": "case-run-id",
  "role": "thesis-skeptic",
  "sources": [{"source_id": "...", "url": "..."}],
  "findings": [{"statement": "...", "source_ids": ["..."], "confidence": "medium", "contradicts": []}],
  "open_questions": [],
  "recommendations_for_lead": []
}
```

## Components

```text
Codex or Claude Code (lead)
  ├─ shared research skill: choose workflow and request delegation plan
  ├─ native subagents: investigate bounded task cards in parallel when justified
  └─ local stdio MCP runtime
       ├─ public-source retrieval and extraction
       ├─ PDF / filing ingestion
       ├─ SQLite case store and source captures
       ├─ thesis, counter-view and citation packet compilation
       └─ later-run evidence delta
```

One source of truth is maintained per `ResearchCase`: issuer/question, captured sources, worker handoffs, thesis/counter-view, uncertainty, and versioned runs. SQLite is sufficient for v0; captured text and derived artifacts live in the case directory. The final brief is rendered from the compiled packet rather than being a second independent research record.

## Plugin and runtime layout

```text
research-dossier/
  .codex-plugin/plugin.json
  .claude-plugin/plugin.json
  .mcp.json
  pyproject.toml
  uv.lock
  skills/living-research/SKILL.md
  agents/                         # Claude Code task cards
  src/research_dossier/
    mcp_server.py
    delegation.py
    discovery.py
    ingestion.py
    filings.py
    dossier_store.py
    delta.py
  templates/
  tests/
```

The first permitted use prepares an isolated, locked `uv` environment for the plugin. It installs the runtime's declared dependencies, not arbitrary software into Codex or Claude Code. A normal run starts one local stdio MCP process. Browser automation is an opt-in extra for sources that genuinely require JavaScript; static public retrieval is the default. Existing Last30Days and Scrapling integrations may add signals, but the case lifecycle does not depend on either being present.

The v0 runtime uses Python 3.12, `mcp`, Pydantic, `httpx`, PDF extraction, Scrapling where it is already available, and the standard-library SQLite module. It deliberately excludes a second LLM provider, LangGraph, a cloud database, a web dashboard, A2A, and a trading/broker interface.

## Small MCP surface

1. `case_open` — create or reopen a named issuer/question case.
2. `source_collect` — retrieve and capture approved public sources.
3. `filing_ingest` — extract a local or public filing into the case.
4. `delegation_plan` — return task cards and join rules; does not spawn agents.
5. `run_save` — save worker handoffs and the lead's structured thesis packet.
6. `brief_render` — render the cited thesis, counter-view, risks, and open questions.
7. `case_compare` — compare two runs and report only evidence-level thesis changes.

All commands return structured data and explicit failure codes. A source failure, missing document, parsing failure, or host refusal to spawn a worker leaves the case usable with a visible gap; it never fabricates a result. The runtime will not silently use credentials, defeat access controls, or execute trades.

## Lifecycle

1. The lead opens a case with an issuer and research question.
2. It collects a bounded evidence set and asks the runtime for a delegation plan.
3. The host launches only the proposed task cards that fit the case and its available budget.
4. Workers return source-linked handoffs to the lead.
5. The lead resolves conflicts, writes the thesis/counter-view/risk packet, and renders a brief.
6. On a later run, the same process adds new evidence and `case_compare` generates the delta: what changed, what remains uncertain, and what should be revisited.

The first useful demo is two frozen issuer runs where the second produces a visibly decision-relevant update rather than a rewritten generic report.

## Acceptance checks for v0

- Install from either host starts the same locked local MCP runtime.
- A new case can create a cited brief with at least one thesis, counter-view, risk, and open question.
- A delegation plan chooses one to three relevant worker tasks for ordinary cases and assigns no more than four workers.
- A host can decline or lack subagent support and still complete a single-lead dossier with the omission recorded.
- Worker output cannot overwrite the canonical case record.
- A second frozen run returns a source-linked delta and does not call a broker or place a trade.
- Focused tests cover schema validation, source/worker handoff isolation, plan selection, and deterministic delta comparison.

## Delivery sequence

1. Package skeleton plus local case store and source capture.
2. MCP tools for open, collect, save, and render a single-lead dossier.
3. Delegation planner and Codex/Claude task cards.
4. Filing/PDF ingestion and run-to-run delta.
5. Optional browser retrieval and optional integrations after the core demo works.

This sequencing keeps the end-to-end output valuable at every stage while avoiding a second, competing investment platform.
