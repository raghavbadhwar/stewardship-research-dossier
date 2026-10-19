from __future__ import annotations

import json

from .errors import InvalidRequest, RunNotComparable
from .models import EvidenceDelta
from .store import CaseStore


def compare_runs(
    store: CaseStore, case_key: str, base_run_id: str, later_run_id: str, lead_implication: str
) -> EvidenceDelta:
    if not lead_implication.strip():
        raise InvalidRequest("Lead implication is required.")
    base_run = store.get_run(base_run_id)
    later_run = store.get_run(later_run_id)
    for run in (base_run, later_run):
        if (
            run.case_key != case_key
            or (run.state not in {"COMPLETE", "PARTIAL"})
            or store.packet_row(run.run_id) is None
        ):
            raise RunNotComparable(run.run_id)
    if base_run.ordinal >= later_run.ordinal:
        raise RunNotComparable(later_run_id)
    base = store.list_sources(base_run_id)
    later = store.list_sources(later_run_id)
    by_url = {(str(s.url), s.content_sha256): s for s in base}
    base_urls = {str(s.url): s for s in base}
    added = []
    sup = []
    same = []
    for s in later:
        old = by_url.get((str(s.url), s.content_sha256))
        if old:
            same.append(s.source_id)
        elif str(s.url) in base_urls:
            sup.append((base_urls[str(s.url)].source_id, s.source_id))
        else:
            added.append(s.source_id)
    later_urls = {str(s.url) for s in later}
    withdrawn = [source.source_id for url, source in base_urls.items() if url not in later_urls]
    delta = EvidenceDelta(
        added=sorted(added),
        withdrawn=sorted(withdrawn),
        superseded=sorted(sup),
        unchanged=sorted(same),
        lead_implication=lead_implication,
    )
    path = store.run_path(later_run_id) / f"delta-from-{base_run.ordinal:04d}.json"
    path.write_text(json.dumps(delta.model_dump(), indent=2, sort_keys=True))
    md = path.with_suffix(".md")
    md.write_text(
        f"# Evidence delta: Run {later_run.ordinal:04d} vs Run {base_run.ordinal:04d}"
        f"\n\n## Added\n{', '.join(delta.added) or 'None'}"
        f"\n\n## Withdrawn\n{', '.join(delta.withdrawn) or 'None'}"
        f"\n\n## Superseded\n{', '.join(f'{a} → {b}' for a, b in delta.superseded) or 'None'}"
        f"\n\n## Unchanged\n{', '.join(delta.unchanged) or 'None'}"
        f"\n\n## Lead implication\n{lead_implication}\n"
    )
    return delta
