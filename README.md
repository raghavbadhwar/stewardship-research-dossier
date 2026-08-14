# Stewardship Research Dossier

A local candidate portfolio prototype that turns public company evidence into a source-linked governance and risk brief, retains a counter-view, and compares later research runs. It is informed by publicly described AI, risk and stewardship priorities; it is not requested, used or endorsed by NBIM.

## Requirements and demo

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --all-groups
uv run srd doctor
uv run srd fixture-demo --offline
```

Cases are local-only under `~/.stewardship-research-dossier/` (or an explicit test root). The frozen offline demo creates two runs and exposes source IDs, a counter-view, and a later evidence delta.

The frozen corpus is a small local excerpt set with recorded capture timestamps and SHA-256 hashes. It points to Microsoft’s [2024 annual report](https://www.microsoft.com/investor/reports/ar24/) and [corporate-governance framework](https://www.microsoft.com/en-us/Investor/corporate-governance/framework); it is not live retrieval or a view on the issuer.

## Boundaries

The host owns reasoning, web discovery, permissions, and any native subagents; the lead alone saves a packet. The runtime captures public static sources and PDFs locally. It makes no investment decision or recommendation, executes no trade, uses no credentials, bypasses no access controls, and is not a production service.

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

## Optional rendered retrieval and recent leads

The `rendered` optional dependency group includes Scrapling. The MCP `source_collect` accepts `rendered_fallback=true` only on an explicit caller request, after static collection fails. Last30Days remains a host-owned discovery mechanism: use `lead_import` to retain its candidate URLs as **untrusted leads**; each lead must still be captured as a primary public source before it may appear in a packet.

## Host packaging

Claude Code can load this checkout for one session with `claude --plugin-dir .`. The package starts the locked local MCP runtime through `bin/srd-mcp`. On 2026-08-14, the local-plugin smoke command was accepted but stopped before a session or MCP call because this machine's configured Claude model identifier was rejected; no Claude host-load claim is made.

Codex uses the repository marketplace manifest. Adding that marketplace and installing the plugin changes Codex configuration, so run the documented marketplace commands only with explicit approval. That host-load test is currently unverified.
