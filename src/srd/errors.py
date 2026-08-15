"""Stable domain errors for callers and MCP envelopes."""

from __future__ import annotations


class SrdError(Exception):
    def __init__(self, code: str, message: str, url: str | None = None) -> None:
        self.code, self.message, self.url = code, message, url
        super().__init__(message)


class InvalidRequest(SrdError):
    def __init__(self, message: str) -> None:
        super().__init__("INVALID_REQUEST", message)


class CaseNotFound(SrdError):
    def __init__(self, case_key: str) -> None:
        super().__init__("CASE_NOT_FOUND", f"Case {case_key} was not found.")


class CaseExists(SrdError):
    def __init__(self, case_key: str) -> None:
        super().__init__("CASE_EXISTS", f"Case {case_key} already exists with different details.")


class InvalidStateTransition(SrdError):
    def __init__(self, state: str, to_state: str) -> None:
        super().__init__(
            "INVALID_STATE_TRANSITION", f"Cannot transition from {state} to {to_state}."
        )


class SourceUnavailable(SrdError):
    def __init__(self, url: str, message: str = "Source could not be retrieved.") -> None:
        super().__init__("SOURCE_UNAVAILABLE", message, url)


class UnsupportedContentType(SrdError):
    def __init__(self, url: str, content_type: str = "") -> None:
        super().__init__(
            "UNSUPPORTED_CONTENT_TYPE", f"Unsupported content type: {content_type}.", url
        )


class ExtractionFailed(SrdError):
    def __init__(
        self, url: str | None = None, message: str = "No readable text could be extracted."
    ) -> None:
        super().__init__("EXTRACTION_FAILED", message, url)


class PacketSourceMismatch(SrdError):
    def __init__(self, source_id: str) -> None:
        super().__init__(
            "PACKET_SOURCE_MISMATCH", f"Source {source_id} is not captured in this run."
        )


class PacketIncomplete(SrdError):
    def __init__(self, message: str = "Packet is incomplete.") -> None:
        super().__init__("PACKET_INCOMPLETE", message)


class EvidenceExcerptMismatch(SrdError):
    def __init__(self, source_id: str) -> None:
        super().__init__(
            "EVIDENCE_EXCERPT_MISMATCH",
            f"The cited excerpt was not found in source {source_id}.",
        )


class ArtifactUnavailable(SrdError):
    def __init__(self, path: str) -> None:
        super().__init__("ARTIFACT_UNAVAILABLE", f"Stored artifact is unavailable: {path}.")


class RunNotComparable(SrdError):
    def __init__(self, run_id: str) -> None:
        super().__init__("RUN_NOT_COMPARABLE", f"Run {run_id} is not complete or packet-backed.")


class DiscoveryUnavailable(SrdError):
    def __init__(self, message: str = "Recent discovery is unavailable.") -> None:
        super().__init__("DISCOVERY_UNAVAILABLE", message)


class DiscoveryTimeout(SrdError):
    def __init__(self) -> None:
        super().__init__("DISCOVERY_TIMEOUT", "Recent discovery exceeded its 90-second limit.")


class DiscoveryOutputTooLarge(SrdError):
    def __init__(self) -> None:
        super().__init__(
            "DISCOVERY_OUTPUT_TOO_LARGE", "Recent discovery output exceeded its limit."
        )


class DiscoveryOutputInvalid(SrdError):
    def __init__(self) -> None:
        super().__init__("DISCOVERY_OUTPUT_INVALID", "Recent discovery returned invalid JSON data.")


class DraftNotFound(SrdError):
    def __init__(self) -> None:
        super().__init__("DRAFT_NOT_FOUND", "No packet draft was saved for this run.")


class DraftNotApprovable(SrdError):
    def __init__(self, message: str = "The packet draft cannot be approved.") -> None:
        super().__init__("DRAFT_NOT_APPROVABLE", message)


class PacketNotApproved(SrdError):
    def __init__(self) -> None:
        super().__init__("PACKET_NOT_APPROVED", "Analyst approval is required before rendering.")
