from __future__ import annotations

import json

from .errors import RunNotComparable
from .models import EvidenceDelta
from .store import CaseStore


def compare_runs(
    store: CaseStore, case_key: str, base_run_id: str, later_run_id: str, lead_implication: str
) -> EvidenceDelta:
    for rid in (base_run_id, later_run_id):
        run = store.get_run(rid)
        if (
            run.case_key != case_key
            or (run.state not in {"COMPLETE", "PARTIAL"})
            or store.packet_row(rid) is None
        ):
            raise RunNotComparable(rid)
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
    delta = EvidenceDelta(
        added=sorted(added),
        superseded=sorted(sup),
        unchanged=sorted(same),
        lead_implication=lead_implication,
    )
    path = (
        store.run_path(later_run_id) / f"delta-from-{store.get_run(base_run_id).ordinal:04d}.json"
    )
    path.write_text(json.dumps(delta.model_dump(), indent=2, sort_keys=True))
    md = path.with_suffix(".md")
    md.write_text(
        f"# Evidence delta: Run {store.get_run(later_run_id).ordinal:04d} vs Run {store.get_run(base_run_id).ordinal:04d}\n\n## Added\n{', '.join(delta.added) or 'None'}\n\n## Superseded\n{', '.join(f'{a} → {b}' for a, b in delta.superseded) or 'None'}\n\n## Unchanged\n{', '.join(delta.unchanged) or 'None'}\n\n## Lead implication\n{lead_implication}\n"
    )
    return delta
