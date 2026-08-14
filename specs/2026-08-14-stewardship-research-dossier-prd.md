# Stewardship Research Dossier — Product Requirements Document

**Status:** planning baseline; the local candidate prototype is implemented, while external deployment remains out of scope.
**Audience:** Raghav Badhwar, future implementation contributors, and reviewers of the public portfolio demo
**Product type:** local, host-native research tool for Codex and Claude Code
**Version:** v0.1

## 1. Product decision

Build a local **Stewardship Research Dossier** that turns public company evidence into a cited governance and risk brief, keeps the contrary view beside the thesis, and tells an analyst what changed on the next review.

It is a portfolio prototype informed by Norges Bank Investment Management's public priorities. It is **not** described as an NBIM product, a request from NBIM, a production system, or an investment-decision engine.

The product's one-sentence description is:

> A host-native research workspace that converts scattered public evidence into a source-linked governance and risk brief, preserves counter-evidence, and surfaces the decision-relevant delta on the next review.

## 2. Why this problem is worth solving

NBIM's graduate programme says its AI work spans investment analysis, risk management, trading, portfolio management, compliance, governance, data pipelines, AI infrastructure, and adoption across the fund. Its public reporting describes LLM screening of new equity-portfolio entrants, deeper searches outside normal data-vendor coverage, and human review before investment or risk decisions. It also reports tools delivering customised governance and sustainability intelligence to investment and stewardship professionals. [Graduate programme](https://www.nbim.no/en/about-us/career/graduate-programme/) · [Responsible Investment Report 2025](https://www.nbim.no/en/news-and-insights/reports/2025/responsible-investment-2025/web-report-responsible-investment-2025/)

Strategy 28 adds the connective problem: data and knowledge must be structured, user-friendly and usable by AI; AI should take on complex analytical tasks while improving decision-making. [Strategy 28](https://www.nbim.no/en/news-and-insights/strategy-for-the-fund-management/strategy-28/)

The public sources do not establish an internal NBIM gap. The product hypothesis is narrower and testable: **when AI-assisted research crosses investment, risk and stewardship work, a durable source trail, explicit counter-view and later evidence delta produce a more useful review artifact than an isolated one-off summary.**

## 3. User and job to be done

### Primary user

An investment, risk or stewardship analyst working with a Codex or Claude Code session. The user starts with an issuer and an answerable question, for example:

> Does Company X present a material governance risk that merits a deeper company-engagement brief after its latest filing and public reporting?

### Job story

When I need to assess an issuer or stewardship issue using scattered public sources, I want the agent to collect and retain the evidence, show me both the thesis and challenge, and show me later what changed, so I can decide what deserves further human investigation without redoing the research from scratch.

### Secondary user

Raghav, demonstrating an evidence-first AI-workflow design to graduate-programme reviewers. The demo must show good judgement, not claim that the tool has been adopted or produced investment performance.

## 4. Target workflow

1. The user opens a case with issuer, question, theme and reference date.
2. The host discovers candidate sources using its existing web capability; the runtime captures approved URLs, public filings and PDFs locally.
3. The runtime returns a bounded delegation plan. The host may launch one to three native specialist subagents; a simple case remains single-lead.
4. Each worker returns a source-linked handoff. The lead writes a structured research packet containing thesis, counter-view, risks, questions and recommended next investigation.
5. The runtime renders a readable Markdown brief with citations.
6. On a later run, the user adds new evidence and receives a source-linked delta rather than a rewritten generic brief.

## 5. Product requirements

### P0 — required for the first credible demo

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| P0-1 | Local case history | Opening the same `case_key` reuses the same local case without overwriting prior runs. |
| P0-2 | Source capture | Every cited statement in a saved packet refers to a captured source ID, URL, title, capture time and extracted text path. |
| P0-3 | Public-web and PDF ingestion | The runtime statically retrieves public HTML and extracts local/public PDFs; failures appear as visible gaps. |
| P0-4 | Structured research packet | A packet requires a thesis, at least one counter-view, risk, open question and cited findings before it can render. |
| P0-5 | Human-led synthesis | The runtime does not make an investment, risk or engagement decision. The host lead supplies and owns the final packet. |
| P0-6 | Evidence delta | Comparing two completed runs identifies added, withdrawn and unchanged evidence and lists thesis implications supplied by the lead. |
| P0-7 | Adaptive delegation | A deterministic planner recommends only relevant specialist tasks, with a normal cap of three and hard cap of four. It never spawns agents itself. |
| P0-8 | Both hosts | Codex and Claude Code can start the same local MCP runtime and use the same case format. |
| P0-9 | Reproducible demo | Two frozen, public-source case fixtures can be re-run offline from captured material. |

### P1 — valuable after the core demo

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| P1-1 | SEC filing helper | A US-listed issuer can retrieve a supplied SEC filing URL with an explicit user-agent and save it as a source. |
| P1-2 | Optional rendered-page retrieval | When static retrieval fails and the user has installed the optional extra, the tool can use Scrapling for the named URL and records the method. |
| P1-3 | Event-candidate input | Host web search or Last30Days output can be imported as untrusted leads, each requiring a captured primary source before it becomes evidence. |
| P1-4 | Case export | A completed case exports as a portable folder containing the SQLite manifest, run artifacts and Markdown brief. |

### Explicitly out of scope

- Trade execution, broker connectivity, price prediction, portfolio optimisation or claimed investment performance.
- A web dashboard, multi-user collaboration, cloud database, background job service or automatic external messaging.
- A second LLM provider, LangGraph, A2A protocol, agent teams or an always-on swarm.
- Claims of institutional immutability, legal custody, complete web coverage, or compliance certification.
- Bypassing paywalls, access controls, robots restrictions or user consent.

## 6. Core experience and outputs

### Input

```json
{
  "case_key": "acme-governance-2026",
  "issuer_name": "Acme Corporation",
  "question": "Do recent disclosures create a governance issue worth a deeper review?",
  "theme": "governance",
  "reference_date": "2026-08-14",
  "source_urls": ["https://example.com/filing", "https://example.com/report.pdf"]
}
```

### Brief output

```text
# Acme Corporation — Governance Research Brief

## Current thesis
… [S-001, S-003]

## Counter-view
… [S-002]

## Risks and unresolved questions
…

## Evidence ledger
S-001 — title, URL, captured date
```

### Delta output

```text
## Evidence delta: Run 002 vs Run 001
Added evidence: S-008
Withdrawn or superseded evidence: S-003
Unchanged evidence: S-001, S-002
Lead assessment: the prior thesis should be revisited because …
```

## 7. Delegation model

The runtime recommends a plan; the host decides whether and how to run it. This keeps Codex and Claude Code in charge of permissions, models and concurrency.

| Case type | Recommended specialists | Maximum |
| --- | --- | --- |
| New issuer | filings analyst, competitive analyst, thesis sceptic | 3 |
| Governance/stewardship issue | governance analyst, filings analyst, thesis sceptic | 3 |
| Event or earnings update | event scout, filings analyst, thesis sceptic | 3 |
| Routine refresh | delta analyst | 1 |
| Cross-domain event | only the directly relevant specialists | 4 |

Each specialist receives a bounded question, allowed source IDs/URLs, a deadline/stop condition, and a required JSON handoff. The lead is the only actor permitted to create the canonical research packet and rendered brief.

## 8. Success measures

The prototype succeeds when a reviewer can complete the two frozen cases and agree that:

1. Each material assertion in the brief can be traced to captured source material.
2. The counter-view is substantive rather than decorative.
3. The second run makes it easy to locate what changed and why that matters.
4. The host can use the workflow with one lead or a bounded set of native subagents.
5. The final artifact looks useful for a research or stewardship discussion, even though it is not a recommendation or production system.

There is no revenue, user-adoption, alpha, risk-reduction, or NBIM-validation metric in v0.

## 9. Quality and safety boundaries

- Evidence, agent output and discovered content are untrusted input.
- A network or parsing failure is displayed as a missing source; it cannot be silently converted into an assertion.
- The default network posture is static retrieval of public URLs. Rendered-page retrieval requires an explicit optional installation and user request.
- Credentials are never installed, stored or inferred by the tool. Private or protected sources are out of scope.
- The case store is local; filesystem hashes establish local integrity only, not legal immutability or institutional records management.
- The final brief always includes an `Analyst review required` notice.

## 10. Portfolio presentation

When the demo exists, the public description must be:

> I built a local research prototype that turns public evidence into a cited governance and risk brief, preserves counter-evidence, and highlights what has changed since the last review. It is informed by publicly described priorities around AI-assisted research and human review in investment management.

The only appropriate invitation is: **“If useful, I would be glad to share a short walkthrough.”** Do not imply that NBIM requested, uses, endorses or needs the tool.

## 11. Release decision

Proceed to implementation only after the specification and implementation plan are reviewed. The first build is complete when the P0 acceptance criteria pass against two frozen cases, a local Codex smoke test, and a local Claude Code smoke test. It remains a candidate portfolio prototype until independently reviewed and actually demonstrated.
