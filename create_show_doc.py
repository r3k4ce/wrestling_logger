from __future__ import annotations

"""Backward-compatible shim that re-exports the wrestling_logger package API."""

from wrestling_logger.ai_format import OpenAI as _OpenAI, format_document_with_ai
from wrestling_logger.cli import (
    _prompt_date,
    _prompt_required,
    _prompt_select_from_list,
    _prompt_yes_no,
    _read_multiline,
    main as _cli_main,
    prompt_metadata,
    prompt_personal_notes,
    prompt_play_by_play,
    prompt_video_ids,
)
from wrestling_logger.doc import (
    ShowMetadata,
    build_document_body,
    create_google_doc,
    delete_google_doc,
    get_credentials,
    write_doc_content,
)
from wrestling_logger.transcripts import (
    TranscriptLookupError,
    TranscriptResult,
    fetch_transcripts,
)

OpenAI = _OpenAI
main = _cli_main

__all__ = [
    "OpenAI",
    "format_document_with_ai",
    "ShowMetadata",
    "build_document_body",
    "create_google_doc",
    "delete_google_doc",
    "get_credentials",
    "write_doc_content",
    "TranscriptLookupError",
    "TranscriptResult",
    "fetch_transcripts",
    "prompt_metadata",
    "prompt_play_by_play",
    "prompt_personal_notes",
    "prompt_video_ids",
    "_prompt_date",
    "_prompt_required",
    "_prompt_select_from_list",
    "_prompt_yes_no",
    "_read_multiline",
    "main",
]


if __name__ == "__main__":
    main()