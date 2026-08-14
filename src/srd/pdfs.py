from __future__ import annotations

from pathlib import Path

import fitz  # type: ignore[import-untyped]

from .errors import ExtractionFailed, SourceUnavailable
from .models import SourceCapture
from .store import CaseStore

MAX_BYTES = 15 * 1024 * 1024


def extract_pdf_bytes(data: bytes) -> str:
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            text = "\n".join(
                page.get_text().strip() for page in doc if page.get_text().strip()
            ).strip()
    except Exception as exc:
        raise ExtractionFailed(message="PDF extraction failed.") from exc
    if not text:
        raise ExtractionFailed()
    return text


def ingest_pdf_path(store: CaseStore, run_id: str, path: Path) -> SourceCapture:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise SourceUnavailable(str(resolved), "PDF path does not exist or is not a file.")
    data = resolved.read_bytes()
    if len(data) > MAX_BYTES:
        raise SourceUnavailable(str(resolved), "PDF exceeds 15 MB limit.")
    return store.add_source(
        run_id,
        url=resolved.as_uri(),
        title=resolved.name,
        publisher=None,
        retrieval_method="pdf",
        text=extract_pdf_bytes(data),
    )
