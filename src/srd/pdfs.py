from __future__ import annotations

from pathlib import Path

import pymupdf as fitz

from .errors import ExtractionFailed, SourceUnavailable
from .models import PdfImportMetadata, SourceCapture
from .store import CaseStore

MAX_BYTES = 15 * 1024 * 1024


def extract_pdf_bytes(data: bytes) -> str:
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:  # type: ignore[no-untyped-call]
            text = "\n".join(
                page.get_text().strip() for page in doc if page.get_text().strip()
            ).strip()
    except Exception as exc:
        raise ExtractionFailed(message="PDF extraction failed.") from exc
    if not text:
        raise ExtractionFailed()
    return text


def ingest_pdf_path(
    store: CaseStore,
    run_id: str,
    path: Path,
    metadata: PdfImportMetadata | None = None,
) -> SourceCapture:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise SourceUnavailable(str(resolved), "PDF path does not exist or is not a file.")
    if resolved.stat().st_size > MAX_BYTES:
        raise SourceUnavailable(str(resolved), "PDF exceeds 15 MB limit.")
    data = resolved.read_bytes()
    if metadata is not None:
        import asyncio

        import httpx

        from .collection import _public_address, _resolve_hostname

        asyncio.run(_public_address(httpx.URL(str(metadata.url)), _resolve_hostname))
    store.begin_collection(run_id)
    return store.add_source(
        run_id,
        url=str(metadata.url) if metadata else resolved.as_uri(),
        title=metadata.title if metadata else resolved.name,
        publisher=metadata.publisher if metadata else None,
        retrieval_method="pdf",
        text=extract_pdf_bytes(data),
        captured_at=metadata.captured_at if metadata else None,
    )
