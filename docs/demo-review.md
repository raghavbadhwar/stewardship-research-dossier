# Candidate demo review

- [x] both fixture runs render locally
- [x] every brief finding has local source IDs
- [x] at least one counter-view is visible
- [x] delta identifies an added and superseded source
- [x] a lead-only run works (the fixture demo uses no delegation workers)
- [x] a three-worker plan is bounded
- [x] Claude plugin load explicitly marked not checked: `claude --plugin-dir .` accepted the local-plugin flag, but its configured model identifier failed before session/MCP startup on 2026-08-14.
- [x] Codex plugin load explicitly marked not checked: it requires a configuration-changing marketplace installation and explicit approval.

Local evidence only: `pytest`, Ruff, mypy, the locked MCP stdio protocol test, the fixture demo, and manifest validation passed on 2026-08-14. This does not prove host integration, live retrieval, production readiness, or issuer suitability.
