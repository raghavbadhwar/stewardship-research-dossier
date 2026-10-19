# Stewardship Research Dossier

A local candidate portfolio prototype that researches a public issuer from one request,
captures evidence, retains a counter-view, and prepares a cited draft for analyst approval. It
is informed by publicly described AI, risk, and stewardship priorities; it was not requested,
used, or endorsed by NBIM.

## Requirements and local demo

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --all-groups
uv run srd doctor
uv run srd fixture-demo --offline
```

Cases stay under `~/.stewardship-research-dossier/` or an explicit test root. The frozen demo
uses local excerpts and makes no network call. It proves same-run citation binding, exact
captured excerpts, a linked counter-view, deterministic diagnostics, and later-run comparison;
it does not prove current facts or issuer operating effectiveness.

## Version 0.3 research flow

The host skill starts when the issuer and objective are sufficient, using named safe defaults. It
asks only when missing scope would materially change research, then records assumptions. The
analyst does not need to supply URLs. It then creates a four-bucket coverage plan, runs host-native institutional
discovery, invokes an embedded Last30Days recent-signals lane, deduplicates all output into an
untrusted lead ledger, captures selected public evidence, and reads every captured source in
bounded chunks.

The embedded default is fixed to keyless Reddit, Hacker News, and GitHub discovery for the 30
days ending on the run reference date. Last30Days 3.21.0 is vendored unchanged at commit
`c7460f6114449ddfe6ea3fc2f23c3d910c0e740c`; provenance and hashes are recorded in
`THIRD_PARTY_NOTICES.md` and `third_party/last30days.manifest.json`. Its raw output is a lead,
not evidence. Every cited claim must still use an exact excerpt captured through SRD.

The host saves a persistent packet draft, shows it to the analyst, and waits. Only an explicit
`packet_approve` call promotes the exact draft hash and allows canonical rendering. Incomplete
coverage requires the analyst to accept the named gaps with a rationale.

## Safety boundaries

The host owns reasoning, institutional web discovery, permissions, and any native workers. The
Python runtime remains deterministic: it does not call an LLM, start workers, make investment,
engagement, voting, risk, or trading decisions, execute trades, or contact anyone.

The recent-discovery subprocess receives a temporary home and configuration directory, a fixed
source list, bounded results and output, no shell, no browser cookies, and no ambient API keys,
tokens, credential aliases, or project configuration. Optional upstream credential, setup,
publishing, watchlist, corpus, and delivery capabilities are shipped for provenance completeness
but are not exposed by the SRD adapter.

Static capture validates and pins a public address on each request and redirect while preserving
the logical Host/TLS identity. After a material static failure or incomplete extraction, the host
may use an already-approved ordinary public renderer such as Scrapling and pass its bounded UTF-8
artifact to `source_import_rendered`. The host validates the final page and challenge state; SRD
does not launch a browser or permit credentials, stealth/CAPTCHA solving, or access-control bypass.

## Public MCP workflow

The main sequence is `case_open` → `research_plan_save` → `lead_import` and
`recent_discover` → evidence capture → complete `source_read` calls →
`packet_draft_save`/`packet_draft_read` → explicit analyst response → `packet_approve` →
`brief_render`. `packet_save` is not exposed publicly.

## Verification

```bash
uv lock --check
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src
uv run --locked pytest -q tests/test_mcp_stdio.py
```

Local tests use fake recent-discovery output and do not establish live source availability,
research quality, production readiness, investment suitability, or external adoption. Live
keyless discovery, host-cache refresh, real Codex/Claude plugin loading, and three independent
no-URL product pilots require separate authorization and verification.

## Host packaging

Claude Code can load this checkout for one session with `claude --plugin-dir .`; Codex can use
the repository marketplace manifest. The installed 0.3.1 Codex cache passes an MCP stdio smoke
test; actual desktop-session loading still requires a fresh Codex session.
