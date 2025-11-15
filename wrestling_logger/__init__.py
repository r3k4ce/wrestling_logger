"""Core package for wrestling logger CLI."""

from .cli import main  # noqa: F401
from .doc import (
    ShowMetadata,
    build_document_body,
    create_google_doc,
    delete_google_doc,
    get_credentials,
    write_doc_content,
)
from .transcripts import TranscriptLookupError, TranscriptResult, fetch_transcripts
from .ai_format import format_document_with_ai, OpenAI

__all__ = [
    "main",
    "ShowMetadata",
    "build_document_body",
    "create_google_doc",
    "delete_google_doc",
    "get_credentials",
    "write_doc_content",
    "TranscriptLookupError",
    "TranscriptResult",
    "fetch_transcripts",
    "format_document_with_ai",
    "OpenAI",
]
