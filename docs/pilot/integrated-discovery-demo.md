# Integrated discovery offline demonstration

**Date:** 2026-08-14  
**Capability:** 0.3.0 candidate  
**Network:** disabled by test design; recent discovery used a fake subprocess response

## Demonstrated path

1. `case_open` created a new local run from issuer, question, theme, and reference date.
2. `research_plan_save` persisted all four evidence buckets and bounded budgets.
3. `recent_discover` invoked the adapter boundary with deterministic fake raw JSON.
4. The resulting Hacker News item became untrusted lead `L-0001`; it did not become a source.
5. A separately captured same-run source supported a validated packet draft.
6. `brief_render` returned `PACKET_NOT_APPROVED` before approval.
7. `packet_approve` recorded the analyst label, note, named accepted gaps, and exact draft hash.
8. `brief_render` then wrote the canonical brief and completed the run.
9. A real stdio MCP client initialized the server and observed the new tool surface without the
   former public `packet_save` bypass.

## Evidence

The behavior is exercised in `tests/test_recent.py`, `tests/test_packet_approval.py`,
`tests/test_mcp_server.py`, and `tests/test_mcp_stdio.py`. Vendor provenance is checked by
`tests/test_vendor_snapshot.py`.

## Not demonstrated

- live Reddit, Hacker News, or GitHub availability or result quality;
- live institutional host discovery or browser fallback;
- installed Codex or Claude host-cache loading;
- an independent analyst's five-minute review;
- three no-URL product pilots;
- NBIM, Microsoft, issuer, customer, production, or investment validation.
