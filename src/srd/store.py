from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlsplit, urlunsplit

from .errors import (
    ArtifactUnavailable,
    CaseExists,
    CaseNotFound,
    EvidenceExcerptMismatch,
    InvalidRequest,
    InvalidStateTransition,
    PacketSourceMismatch,
)
from .models import (
    CaseOpenRequest,
    CaseRef,
    EvidenceCitation,
    LeadCandidate,
    PacketStatus,
    PersistedLead,
    RecentDiscoveryRecord,
    ResearchPlan,
    RunRef,
    RunSnapshot,
    SourceCapture,
    SourceTextChunk,
    WorkerHandoff,
    parse_run_id,
    validate_case_key,
)

ALLOWED_TRANSITIONS = {
    "OPEN": {"COLLECTING", "BLOCKED"},
    "COLLECTING": {"INVESTIGATING", "SYNTHESIS_PENDING", "PARTIAL", "BLOCKED"},
    "INVESTIGATING": {"SYNTHESIS_PENDING", "PARTIAL", "BLOCKED"},
    "SYNTHESIS_PENDING": {"REVIEW_PENDING", "COMPLETE", "PARTIAL", "BLOCKED"},
    "REVIEW_PENDING": {"COMPLETE", "PARTIAL", "BLOCKED"},
    "PARTIAL": {
        "COLLECTING",
        "INVESTIGATING",
        "SYNTHESIS_PENDING",
        "REVIEW_PENDING",
        "COMPLETE",
    },
    "COMPLETE": set(),
    "BLOCKED": {"COLLECTING"},
}
MAX_SOURCE_READ_CHARS = 20_000


def now() -> str:
    return datetime.now(UTC).isoformat()


def _write_atomic(path: Path, text: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _canonicalize_url(raw: str) -> str:
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise InvalidRequest("Lead URL must be a public HTTP(S) URL.")
    if parsed.username is not None or parsed.password is not None:
        raise InvalidRequest("Lead URL must not contain credentials.")
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


class CaseStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def case_path(self, case_key: str) -> Path:
        return self.root / validate_case_key(case_key)

    @contextmanager
    def _db(self, case_key: str) -> Iterator[sqlite3.Connection]:
        path = self.case_path(case_key) / "dossier.sqlite"
        if not path.exists():
            raise CaseNotFound(case_key)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    def _schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""CREATE TABLE cases(case_key TEXT PRIMARY KEY, issuer_name TEXT NOT NULL, question TEXT NOT NULL, theme TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE runs(run_id TEXT PRIMARY KEY, case_key TEXT NOT NULL, ordinal INTEGER NOT NULL, state TEXT NOT NULL, reference_date TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT, UNIQUE(case_key,ordinal));
CREATE TABLE sources(source_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL, publisher TEXT, captured_at TEXT NOT NULL, retrieval_method TEXT NOT NULL, content_sha256 TEXT NOT NULL, text_path TEXT NOT NULL);
CREATE TABLE handoffs(handoff_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, role TEXT NOT NULL, artifact_path TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE packets(packet_id TEXT PRIMARY KEY, run_id TEXT UNIQUE NOT NULL, artifact_path TEXT NOT NULL, brief_path TEXT);""")

    def open_case(self, request: CaseOpenRequest) -> CaseRef:
        path = self.case_path(request.case_key)
        if path.exists():
            with self._db(request.case_key) as conn:
                row = conn.execute("SELECT * FROM cases").fetchone()
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
            try:
                conn.execute("PRAGMA foreign_keys=ON")
                self._schema(conn)
                conn.execute(
                    "INSERT INTO cases VALUES(?,?,?,?,?)",
                    (
                        request.case_key,
                        request.issuer_name,
                        request.question,
                        request.theme,
                        now(),
                    ),
                )
                conn.commit()
            finally:
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
        with self._db(case_key) as conn:
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
                _write_atomic(
                    run_path / "request.json",
                    json.dumps(
                        {"case_key": case_key, "reference_date": reference_date.isoformat()},
                        sort_keys=True,
                        indent=2,
                    ),
                )
            except Exception:
                shutil.rmtree(run_path, ignore_errors=True)
                with conn:
                    conn.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
                raise
        return RunRef(
            run_id=run_id,
            case_key=case_key,
            ordinal=ordinal,
            state="OPEN",
            reference_date=reference_date,
        )

    def get_run(self, run_id: str) -> RunRef:
        case_key, _ = parse_run_id(run_id)
        with self._db(case_key) as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise CaseNotFound(run_id)
        return RunRef(
            run_id=row["run_id"],
            case_key=row["case_key"],
            ordinal=row["ordinal"],
            state=row["state"],
            reference_date=date.fromisoformat(row["reference_date"]),
        )

    def get_case(self, case_key: str) -> CaseRef:
        with self._db(case_key) as conn:
            row = conn.execute("SELECT * FROM cases WHERE case_key=?", (case_key,)).fetchone()
        if row is None:
            raise CaseNotFound(case_key)
        return CaseRef(
            case_key=row["case_key"],
            issuer_name=row["issuer_name"],
            question=row["question"],
            theme=row["theme"],
        )

    def run_path(self, run_id: str) -> Path:
        r = self.get_run(run_id)
        return self.case_path(r.case_key) / "runs" / f"{r.ordinal:04d}"

    def transition(self, run_id: str, to_state: str) -> RunRef:
        run = self.get_run(run_id)
        if to_state not in ALLOWED_TRANSITIONS.get(run.state, set()):
            raise InvalidStateTransition(run.state, to_state)
        with self._db(run.case_key) as conn, conn:
            conn.execute(
                "UPDATE runs SET state=?, completed_at=? WHERE run_id=?",
                (to_state, now() if to_state == "COMPLETE" else None, run_id),
            )
        return self.get_run(run_id)

    def begin_collection(self, run_id: str) -> RunRef:
        run = self.get_run(run_id)
        if run.state in {"OPEN", "BLOCKED"}:
            return self.transition(run_id, "COLLECTING")
        if run.state in {"COLLECTING", "INVESTIGATING"}:
            return run
        raise InvalidStateTransition(run.state, "COLLECTING")

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
        with self._db(run.case_key) as conn:
            n = int(
                conn.execute(
                    "SELECT COALESCE(MAX(CAST(SUBSTR(source_id,3) AS INTEGER)),0)+1 FROM sources"
                ).fetchone()[0]
            )
            sid = f"S-{n:04d}"
            path = self.run_path(run_id) / "sources" / sid
            textpath = path.with_suffix(".txt")
            actual_sha256 = hashlib.sha256(text.encode()).hexdigest()
            if content_sha256 is not None and content_sha256 != actual_sha256:
                raise InvalidRequest("Source text does not match its recorded SHA-256 hash.")
            cap = SourceCapture(
                source_id=sid,
                url=url,  # type: ignore[arg-type]
                title=title,
                publisher=publisher,
                captured_at=captured_at or datetime.now(UTC),
                retrieval_method=cast(Literal["static", "pdf", "host_rendered"], retrieval_method),
                content_sha256=actual_sha256,
                text_path=str(textpath),
            )
            metadata_path = path.with_suffix(".json")
            try:
                _write_atomic(textpath, text)
                _write_atomic(metadata_path, cap.model_dump_json(indent=2))
                with conn:
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
            except Exception:
                textpath.unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
                raise
        return cap

    def list_sources(self, run_id: str) -> list[SourceCapture]:
        run = self.get_run(run_id)
        with self._db(run.case_key) as conn:
            rows = conn.execute(
                "SELECT * FROM sources WHERE run_id=? ORDER BY source_id", (run_id,)
            ).fetchall()
        return [SourceCapture(**dict(x)) for x in rows]

    def read_source_text(self, run_id: str, source_id: str) -> str:
        run = self.get_run(run_id)
        with self._db(run.case_key) as conn:
            row = conn.execute(
                "SELECT text_path FROM sources WHERE run_id=? AND source_id=?",
                (run_id, source_id),
            ).fetchone()
        if row is None:
            raise PacketSourceMismatch(source_id)
        path = Path(row["text_path"])
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ArtifactUnavailable(str(path)) from exc

    def inspect_run(self, run_id: str) -> RunSnapshot:
        run = self.get_run(run_id)
        row = self.packet_row(run_id)
        packet = (
            PacketStatus(
                packet_id=row["packet_id"],
                artifact_path=row["artifact_path"],
                brief_path=row["brief_path"],
            )
            if row is not None
            else None
        )
        return RunSnapshot(
            case=self.get_case(run.case_key),
            run=run,
            sources=self.list_sources(run_id),
            packet=packet,
        )

    def read_source_chunk(
        self, run_id: str, source_id: str, offset: int = 0, limit: int = 12_000
    ) -> SourceTextChunk:
        if offset < 0 or limit < 1 or limit > MAX_SOURCE_READ_CHARS:
            raise InvalidRequest(
                "offset must be non-negative and limit must be between 1 and 20000."
            )
        text = self.read_source_text(run_id, source_id)
        if offset > len(text):
            raise InvalidRequest("offset exceeds captured source length.")
        end = min(len(text), offset + limit)
        complete = end == len(text)
        return SourceTextChunk(
            source_id=source_id,
            offset=offset,
            next_offset=None if complete else end,
            complete=complete,
            text=text[offset:end],
        )

    def validate_citation(self, run_id: str, citation: EvidenceCitation) -> None:
        captured = " ".join(self.read_source_text(run_id, citation.source_id).split())
        if " ".join(citation.excerpt.split()) not in captured:
            raise EvidenceExcerptMismatch(citation.source_id)

    def save_handoff(self, handoff: WorkerHandoff) -> str:
        valid = {x.source_id for x in self.list_sources(handoff.run_id)}
        if any(s not in valid for s in handoff.sources):
            raise PacketSourceMismatch(next(s for s in handoff.sources if s not in valid))
        allowed = set(handoff.sources)
        for finding in handoff.findings:
            for citation in finding.citations:
                if citation.source_id not in allowed:
                    raise PacketSourceMismatch(citation.source_id)
                self.validate_citation(handoff.run_id, citation)
        with self._db(self.get_run(handoff.run_id).case_key) as conn:
            n = int(
                conn.execute(
                    "SELECT COALESCE(MAX(CAST(SUBSTR(handoff_id,3) AS INTEGER)),0)+1 FROM handoffs"
                ).fetchone()[0]
            )
            hid = f"H-{n:04d}"
            path = self.run_path(handoff.run_id) / "handoffs" / f"{hid}.json"
            try:
                _write_atomic(path, handoff.model_dump_json(indent=2))
                with conn:
                    conn.execute(
                        "INSERT INTO handoffs VALUES(?,?,?,?,?)",
                        (hid, handoff.run_id, handoff.role, str(path), "saved"),
                    )
            except Exception:
                path.unlink(missing_ok=True)
                raise
        return hid

    def save_research_plan(self, run_id: str, plan: ResearchPlan) -> Path:
        run = self.get_run(run_id)
        if plan.run_id != run_id:
            raise InvalidRequest("Research plan run_id does not match the target run_id.")
        case = self.get_case(run.case_key)
        if (
            plan.issuer != case.issuer_name
            or plan.question != case.question
            or plan.theme != case.theme
            or plan.reference_date != run.reference_date
        ):
            raise InvalidRequest(
                "Research plan issuer, question, theme, and reference date must match the run."
            )
        if run.state in {"COMPLETE", "BLOCKED", "REVIEW_PENDING"}:
            raise InvalidStateTransition(run.state, "COLLECTING")
        if not plan.issues:
            raise InvalidRequest("New research plans require at least one issue.")
        captured = {source.source_id for source in self.list_sources(run_id)}
        for bucket in plan.coverage.values():
            unknown = set(bucket.source_ids) - captured
            if unknown:
                raise PacketSourceMismatch(next(iter(unknown)))
        for issue in plan.issues:
            unknown = (set(issue.source_ids) | set(issue.counter_source_ids)) - captured
            if unknown:
                raise PacketSourceMismatch(next(iter(unknown)))
        path = self.run_path(run_id) / "research-plan.json"
        _write_atomic(path, plan.model_dump_json(indent=2))
        return path

    def load_research_plan(self, run_id: str) -> ResearchPlan:
        path = self.run_path(run_id) / "research-plan.json"
        try:
            return ResearchPlan.model_validate_json(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ArtifactUnavailable(str(path)) from exc

    def list_leads(self, run_id: str) -> list[PersistedLead]:
        path = self.run_path(run_id) / "leads.json"
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            values = payload["leads"]
            if not isinstance(values, list):
                raise TypeError
            return [PersistedLead.model_validate(value) for value in values]
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ArtifactUnavailable(str(path)) from exc

    def import_leads(self, run_id: str, leads: list[LeadCandidate]) -> list[PersistedLead]:
        """Append untrusted discovery leads without turning them into evidence sources."""
        run = self.get_run(run_id)
        if run.state in {"COMPLETE", "BLOCKED"}:
            raise InvalidStateTransition(run.state, "COLLECTING")
        persisted = self.list_leads(run_id)
        plan_path = self.run_path(run_id) / "research-plan.json"
        lead_budget = self.load_research_plan(run_id).lead_budget if plan_path.exists() else 50
        by_url = {str(lead.canonical_url): lead for lead in persisted}
        returned: list[PersistedLead] = []
        next_id = max((int(lead.lead_id[2:]) for lead in persisted), default=0) + 1
        for lead in leads:
            canonical = _canonicalize_url(str(lead.url))
            existing = by_url.get(canonical)
            if existing is not None:
                returned.append(existing)
                continue
            if len(persisted) >= lead_budget:
                raise InvalidRequest("Imported leads exceed the saved research plan lead budget.")
            value = PersistedLead(
                **lead.model_dump(exclude={"discovered_at"}),
                lead_id=f"L-{next_id:04d}",
                canonical_url=canonical,  # type: ignore[arg-type]
                discovered_at=lead.discovered_at or datetime.now(UTC),
            )
            next_id += 1
            persisted.append(value)
            by_url[canonical] = value
            returned.append(value)
        path = self.run_path(run_id) / "leads.json"
        payload = {
            "run_id": run.run_id,
            "untrusted": True,
            "leads": [lead.model_dump(mode="json") for lead in persisted],
        }
        _write_atomic(path, json.dumps(payload, sort_keys=True, indent=2))
        return returned

    def save_recent_discovery(self, record: RecentDiscoveryRecord) -> Path:
        self.get_run(record.run_id)
        path = self.run_path(record.run_id) / "recent-discovery.json"
        _write_atomic(path, record.model_dump_json(indent=2))
        return path

    def load_recent_discovery(self, run_id: str) -> RecentDiscoveryRecord | None:
        path = self.run_path(run_id) / "recent-discovery.json"
        if not path.exists():
            return None
        try:
            return RecentDiscoveryRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ArtifactUnavailable(str(path)) from exc

    def export_case(self, case_key: str, destination: Path) -> Path:
        source = self.case_path(case_key).resolve()
        self.get_case(case_key)
        destination = destination.expanduser().resolve()
        if destination.exists():
            raise InvalidRequest("Destination already exists.")
        if destination == source or destination.is_relative_to(source):
            raise InvalidRequest("Destination must be outside the case directory.")
        shutil.copytree(source, destination)
        return destination

    def packet_row(self, run_id: str) -> sqlite3.Row | None:
        run = self.get_run(run_id)
        with self._db(run.case_key) as conn:
            x = conn.execute("SELECT * FROM packets WHERE run_id=?", (run_id,)).fetchone()
        return cast(sqlite3.Row | None, x)

    def save_packet_row(self, run_id: str, packet_id: str, artifact_path: Path) -> None:
        run = self.get_run(run_id)
        with self._db(run.case_key) as conn, conn:
            conn.execute(
                "INSERT INTO packets(packet_id,run_id,artifact_path,brief_path) VALUES(?,?,?,NULL)",
                (packet_id, run_id, str(artifact_path)),
            )

    def set_brief_path(self, run_id: str, brief_path: Path) -> None:
        run = self.get_run(run_id)
        with self._db(run.case_key) as conn, conn:
            conn.execute(
                "UPDATE packets SET brief_path=? WHERE run_id=?", (str(brief_path), run_id)
            )
