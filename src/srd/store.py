from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, cast

from .errors import CaseExists, CaseNotFound, InvalidRequest, InvalidStateTransition
from .models import (
    CaseOpenRequest,
    CaseRef,
    LeadCandidate,
    RunRef,
    SourceCapture,
    WorkerHandoff,
    parse_run_id,
    validate_case_key,
)

ALLOWED_TRANSITIONS = {
    "OPEN": {"COLLECTING", "BLOCKED"},
    "COLLECTING": {"INVESTIGATING", "SYNTHESIS_PENDING", "PARTIAL", "BLOCKED"},
    "INVESTIGATING": {"SYNTHESIS_PENDING", "PARTIAL", "BLOCKED"},
    "SYNTHESIS_PENDING": {"COMPLETE", "PARTIAL", "BLOCKED"},
    "PARTIAL": {"COLLECTING", "INVESTIGATING", "SYNTHESIS_PENDING", "COMPLETE"},
    "COMPLETE": set(),
    "BLOCKED": {"COLLECTING"},
}


def now() -> str:
    return datetime.now(UTC).isoformat()


class CaseStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def case_path(self, case_key: str) -> Path:
        return self.root / validate_case_key(case_key)

    def _db(self, case_key: str) -> sqlite3.Connection:
        path = self.case_path(case_key) / "dossier.sqlite"
        if not path.exists():
            raise CaseNotFound(case_key)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""CREATE TABLE cases(case_key TEXT PRIMARY KEY, issuer_name TEXT NOT NULL, question TEXT NOT NULL, theme TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE runs(run_id TEXT PRIMARY KEY, case_key TEXT NOT NULL, ordinal INTEGER NOT NULL, state TEXT NOT NULL, reference_date TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT, UNIQUE(case_key,ordinal));
CREATE TABLE sources(source_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL, publisher TEXT, captured_at TEXT NOT NULL, retrieval_method TEXT NOT NULL, content_sha256 TEXT NOT NULL, text_path TEXT NOT NULL);
CREATE TABLE handoffs(handoff_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, role TEXT NOT NULL, artifact_path TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE packets(packet_id TEXT PRIMARY KEY, run_id TEXT UNIQUE NOT NULL, artifact_path TEXT NOT NULL, brief_path TEXT);""")

    def open_case(self, request: CaseOpenRequest) -> CaseRef:
        path = self.case_path(request.case_key)
        if path.exists():
            conn = self._db(request.case_key)
            row = conn.execute("SELECT * FROM cases").fetchone()
            conn.close()
            if (
                row["issuer_name"] != request.issuer_name
                or row["question"] != request.question
                or row["theme"] != request.theme
            ):
                raise CaseExists(request.case_key)
            return CaseRef(
                case_key=request.case_key,
                issuer_name=row["issuer_name"],
                question=row["question"],
                theme=row["theme"],
            )
        path.mkdir(parents=True, exist_ok=False)
        try:
            conn = sqlite3.connect(path / "dossier.sqlite")
            conn.execute("PRAGMA foreign_keys=ON")
            self._schema(conn)
            conn.execute(
                "INSERT INTO cases VALUES(?,?,?,?,?)",
                (request.case_key, request.issuer_name, request.question, request.theme, now()),
            )
            conn.commit()
            conn.close()
        except Exception:
            shutil.rmtree(path, ignore_errors=True)
            raise
        return CaseRef(
            case_key=request.case_key,
            issuer_name=request.issuer_name,
            question=request.question,
            theme=request.theme,
        )

    def start_run(self, case_key: str, reference_date: date) -> RunRef:
        case_key = validate_case_key(case_key)
        conn = self._db(case_key)
        ordinal = int(conn.execute("SELECT COALESCE(MAX(ordinal),0)+1 FROM runs").fetchone()[0])
        run_id = f"{case_key}:{ordinal:04d}"
        run_path = self.case_path(case_key) / "runs" / f"{ordinal:04d}"
        try:
            with conn:
                conn.execute(
                    "INSERT INTO runs VALUES(?,?,?,?,?,?,NULL)",
                    (run_id, case_key, ordinal, "OPEN", reference_date.isoformat(), now()),
                )
            run_path.mkdir(parents=True, exist_ok=False)
            (run_path / "sources").mkdir()
            (run_path / "handoffs").mkdir()
            (run_path / "request.json").write_text(
                json.dumps(
                    {"case_key": case_key, "reference_date": reference_date.isoformat()},
                    sort_keys=True,
                    indent=2,
                )
            )
        except Exception:
            shutil.rmtree(run_path, ignore_errors=True)
            conn.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
            conn.commit()
            raise
        finally:
            conn.close()
        return RunRef(
            run_id=run_id,
            case_key=case_key,
            ordinal=ordinal,
            state="OPEN",
            reference_date=reference_date,
        )

    def get_run(self, run_id: str) -> RunRef:
        case_key, _ = parse_run_id(run_id)
        conn = self._db(case_key)
        row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        conn.close()
        if row is None:
            raise CaseNotFound(run_id)
        return RunRef(
            run_id=row["run_id"],
            case_key=row["case_key"],
            ordinal=row["ordinal"],
            state=row["state"],
            reference_date=date.fromisoformat(row["reference_date"]),
        )

    def run_path(self, run_id: str) -> Path:
        r = self.get_run(run_id)
        return self.case_path(r.case_key) / "runs" / f"{r.ordinal:04d}"

    def transition(self, run_id: str, to_state: str) -> RunRef:
        run = self.get_run(run_id)
        if to_state not in ALLOWED_TRANSITIONS.get(run.state, set()):
            raise InvalidStateTransition(run.state, to_state)
        conn = self._db(run.case_key)
        conn.execute(
            "UPDATE runs SET state=?, completed_at=? WHERE run_id=?",
            (to_state, now() if to_state == "COMPLETE" else None, run_id),
        )
        conn.commit()
        conn.close()
        return self.get_run(run_id)

    def add_source(
        self,
        run_id: str,
        *,
        url: str,
        title: str,
        publisher: str | None,
        retrieval_method: str,
        text: str,
        captured_at: datetime | None = None,
        content_sha256: str | None = None,
    ) -> SourceCapture:
        import hashlib

        run = self.get_run(run_id)
        if run.state not in {"COLLECTING", "INVESTIGATING"}:
            raise InvalidStateTransition(run.state, "COLLECTING")
        conn = self._db(run.case_key)
        n = int(conn.execute("SELECT COUNT(*) FROM sources", ()).fetchone()[0]) + 1
        sid = f"S-{n:04d}"
        path = self.run_path(run_id) / "sources" / sid
        textpath = path.with_suffix(".txt")
        actual_sha256 = hashlib.sha256(text.encode()).hexdigest()
        if content_sha256 is not None and content_sha256 != actual_sha256:
            raise InvalidRequest("Source text does not match its recorded SHA-256 hash.")
        textpath.write_text(text, encoding="utf-8")
        cap = SourceCapture(
            source_id=sid,
            url=url,  # type: ignore[arg-type]
            title=title,
            publisher=publisher,
            captured_at=captured_at or datetime.now(UTC),
            retrieval_method=cast(Literal["static", "pdf", "rendered"], retrieval_method),
            content_sha256=actual_sha256,
            text_path=str(textpath),
        )
        path.with_suffix(".json").write_text(cap.model_dump_json(indent=2))
        conn.execute(
            "INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?)",
            (
                sid,
                run_id,
                str(cap.url),
                title,
                publisher,
                cap.captured_at.isoformat(),
                retrieval_method,
                cap.content_sha256,
                str(textpath),
            ),
        )
        conn.commit()
        conn.close()
        return cap

    def list_sources(self, run_id: str) -> list[SourceCapture]:
        run = self.get_run(run_id)
        conn = self._db(run.case_key)
        rows = conn.execute(
            "SELECT * FROM sources WHERE run_id=? ORDER BY source_id", (run_id,)
        ).fetchall()
        conn.close()
        return [SourceCapture(**dict(x)) for x in rows]

    def save_handoff(self, handoff: WorkerHandoff) -> str:
        valid = {x.source_id for x in self.list_sources(handoff.run_id)}
        if any(s not in valid for s in handoff.sources):
            from .errors import PacketSourceMismatch

            raise PacketSourceMismatch(next(s for s in handoff.sources if s not in valid))
        conn = self._db(self.get_run(handoff.run_id).case_key)
        n = (
            int(
                conn.execute(
                    "SELECT COUNT(*) FROM handoffs WHERE run_id=?", (handoff.run_id,)
                ).fetchone()[0]
            )
            + 1
        )
        hid = f"H-{n:04d}"
        path = self.run_path(handoff.run_id) / "handoffs" / f"{hid}.json"
        path.write_text(handoff.model_dump_json(indent=2))
        conn.execute(
            "INSERT INTO handoffs VALUES(?,?,?,?,?)",
            (hid, handoff.run_id, handoff.role, str(path), "saved"),
        )
        conn.commit()
        conn.close()
        return hid

    def import_leads(self, run_id: str, leads: list[LeadCandidate]) -> Path:
        """Persist untrusted host/Last30Days leads; they are never evidence sources."""
        run = self.get_run(run_id)
        path = self.run_path(run_id) / "leads.json"
        payload = {
            "run_id": run.run_id,
            "untrusted": True,
            "leads": [lead.model_dump(mode="json") for lead in leads],
        }
        path.write_text(json.dumps(payload, sort_keys=True, indent=2))
        return path

    def packet_row(self, run_id: str) -> sqlite3.Row | None:
        run = self.get_run(run_id)
        conn = self._db(run.case_key)
        x = conn.execute("SELECT * FROM packets WHERE run_id=?", (run_id,)).fetchone()
        conn.close()
        return cast(sqlite3.Row | None, x)
