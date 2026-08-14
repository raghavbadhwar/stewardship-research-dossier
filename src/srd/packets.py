from __future__ import annotations

import json
from pathlib import Path

from .errors import InvalidStateTransition, PacketIncomplete, PacketSourceMismatch
from .models import PacketRef, ResearchPacket
from .store import CaseStore


def save_packet(
    store: CaseStore, run_id: str, packet: ResearchPacket, decision_implication: str
) -> PacketRef:
    if not decision_implication.strip():
        raise PacketIncomplete("Decision implication is required.")
    run = store.get_run(run_id)
    if run.state not in {"SYNTHESIS_PENDING", "PARTIAL"}:
        raise InvalidStateTransition(run.state, "COMPLETE")
    valid = {s.source_id for s in store.list_sources(run_id)}
    for f in [*packet.thesis, *packet.counter_view, *packet.risks]:
        for sid in f.source_ids:
            if sid not in valid:
                raise PacketSourceMismatch(sid)
    path = store.run_path(run_id) / "packet.json"
    payload = {**packet.model_dump(mode="json"), "decision_implication": decision_implication}
    path.write_text(json.dumps(payload, sort_keys=True, indent=2))
    conn = store._db(run.case_key)
    conn.execute(
        "INSERT OR REPLACE INTO packets(packet_id,run_id,artifact_path,brief_path) VALUES(?,?,?,NULL)",
        (f"P-{run.ordinal:04d}", run_id, str(path)),
    )
    conn.commit()
    conn.close()
    return PacketRef(packet_id=f"P-{run.ordinal:04d}", run_id=run_id, path=str(path))


def render_brief(store: CaseStore, run_id: str) -> Path:
    row = store.packet_row(run_id)
    if row is None:
        raise PacketIncomplete("No packet saved for run.")
    data = json.loads(Path(row["artifact_path"]).read_text())
    run = store.get_run(run_id)
    conn = store._db(run.case_key)
    case = conn.execute("SELECT * FROM cases").fetchone()
    conn.close()
    lines = [
        f"# {case['issuer_name']} — {case['theme'].title()} Research Brief",
        "",
        "## Analyst review required",
        "True",
    ]
    for heading, key in [
        ("Current thesis", "thesis"),
        ("Counter-view", "counter_view"),
        ("Risks", "risks"),
    ]:
        lines += ["", f"## {heading}"]
        lines += [f"- {f['statement']} [{', '.join(f['source_ids'])}]" for f in data[key]]
    lines += [
        "",
        "## Open questions",
        *[f"- {q}" for q in data["open_questions"]],
        "",
        "## Decision implication",
        data["decision_implication"],
        "",
        "## Evidence ledger",
    ]
    for s in store.list_sources(run_id):
        lines.append(f"- {s.source_id} — {s.title}, {s.url}, captured {s.captured_at.isoformat()}")
    path = store.run_path(run_id) / "brief.md"
    path.write_text("\n".join(lines) + "\n")
    conn = store._db(run.case_key)
    conn.execute("UPDATE packets SET brief_path=? WHERE run_id=?", (str(path), run_id))
    conn.commit()
    conn.close()
    if run.state == "SYNTHESIS_PENDING":
        store.transition(run_id, "COMPLETE")
    return path
