# Candidate demo review

- [x] both frozen fixture runs render locally without network access
- [x] every brief finding includes a same-run source ID, locator, and validated excerpt
- [x] the evidence ledger includes final URL, capture time, retrieval method, and SHA-256
- [x] the first brief contains a narrow board-oversight thesis and a substantive evidence-limit counter-view
- [x] the delta identifies one added, withdrawn, superseded, and unchanged source
- [x] the lead implication names the unresolved Board-evidence question without automating a decision
- [x] a lead-only run works and delegation remains bounded
- [x] version 0.3.0 adds a persisted four-bucket research plan, append-only untrusted lead ledger, fully tracked Last30Days 3.21.0 snapshot, isolated keyless recent discovery, persistent packet drafts, exact-hash analyst approval, and an approval-gated public MCP workflow
- [ ] independent five-minute reviewer rubric: unverified; no independent reviewer was used during implementation
- [x] live static capture: the official NBIM Strategy 28 page reached `SYNTHESIS_PENDING` as `S-0001`, with the official final URL, title `Strategy 28 | Norges Bank Investment Management`, 17,915 captured characters, and no error
- [x] automated 0.3.0 gate: 66 tests passed; vendor manifest, lock, Ruff, formatting, mypy, doctor, MCP stdio, offline demo, shell syntax, and diff hygiene passed on 2026-08-14
- [x] upstream snapshot gate: all 4,008 collected Last30Days 3.21.0 tests passed under Python 3.12 with isolated HOME/environment and bytecode/cache writes disabled; one earlier ambient-HOME run failed only because it detected the user's Grok installation outside PATH
- [ ] live 0.3.0 recent discovery: not run; real Reddit, Hacker News, and GitHub availability and result quality require separate authorization
- [ ] Claude 0.3.0 host call: not run; no credential change, plugin-cache refresh, or new paid provider call was authorized
- [ ] Codex 0.3.0 plugin load: not run; the repository manifest is updated, but installed plugin-cache refresh requires separate authorization
- [ ] three independent no-URL product pilots: not run; stable-governance, recent-event, and difficult-acquisition pilots remain product-level validation gates

The test run emitted six dependency warnings: five PyMuPDF/SWIG deprecations and one FastMCP/Pydantic unresolved-forward-reference warning. They did not fail the local gate but remain dependency-level noise.

This remains local candidate-prototype evidence. The local gates, historical live capture, and earlier Codex host call do not establish live 0.3.0 discovery quality, Claude/Codex 0.3.0 end-to-end integration, production readiness, investment suitability, issuer operating effectiveness, or Microsoft/NBIM use or endorsement.
