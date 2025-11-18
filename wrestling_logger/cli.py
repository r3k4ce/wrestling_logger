"""Interactive CLI for building wrestling show documents."""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import List

from . import config
from .ai_format import format_document_with_ai
from .doc import (
    ShowMetadata,
    build_document_body,
    create_google_doc,
    delete_google_doc,
    get_credentials,
    write_doc_content,
)
from .transcripts import fetch_transcripts

logger = logging.getLogger(__name__)


def prompt_metadata() -> ShowMetadata:
    print("## STEP 1: METADATA\n")
    date_str = _prompt_date("Enter event date (YYYY-MM-DD): ")
    promotion = _prompt_required("Enter promotion (e.g., WWE or AEW): ")
    promo_key = promotion.strip().upper()
    known_promotions: dict = {
        "WWE": ["RAW", "SMACKDOWN"],
        "AEW": ["DYNAMITE", "COLLISION"],
    }

    is_ppv = _prompt_yes_no("Is this a PPV (Pay-Per-View)? (y/N): ")
    show_type = "PPV" if is_ppv else "TV"
    if is_ppv:
        show_name = _prompt_required("Enter PPV show name (e.g., Royal Rumble): ")
    else:
        if promo_key in known_promotions:
            options = known_promotions[promo_key]
            choice = _prompt_select_from_list(f"Select the show for {promo_key}:", options)
            show_name = choice
        else:
            show_name = _prompt_required("Enter show (e.g., RAW): ")
    metadata = ShowMetadata(event_date=date_str, promotion=promotion, show_name=show_name)
    metadata.show_type = show_type
    print(f"\nGenerating doc named '{metadata.doc_title}'...\n")
    return metadata


def prompt_play_by_play() -> str:
    print("## STEP 2: Play-by-Play\n")
    prompt = (
        "Paste your copied Play-by-Play recap text.\n"
        "Finish with a line containing only '::end::' (without quotes)."
    )
    return _read_multiline(prompt)


def prompt_personal_notes() -> str:
    print("\n## STEP 3: YOUR ANGLE (Personal Notes)\n")
    prompt = (
        "Paste your personal notes.\n"
        "Finish with a line containing only '::end::' (without quotes)."
    )
    return _read_multiline(prompt)


def prompt_video_ids() -> List[str]:
    print("\n## STEP 4: YouTube Transcripts\n")
    raw_ids = _prompt_required("Enter all YouTube video IDs, separated by a comma: ")
    video_ids = [vid.strip() for vid in raw_ids.split(",") if vid.strip()]
    if not video_ids:
        raise ValueError("At least one video ID is required to proceed.")
    return video_ids


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("Starting the wrestling logger...")
    print("This script will build your Master Doc.\n")
    metadata = prompt_metadata()
    recap_text = prompt_play_by_play()
    personal_notes = prompt_personal_notes()
    video_ids = prompt_video_ids()
    transcript_results = fetch_transcripts(video_ids)

    doc_body = build_document_body(metadata, recap_text, personal_notes, transcript_results)

    print("\nCollected Data Summary:")
    print(f" - Metadata Title: {metadata.doc_title}")
    print(f" - Play-by-Play length: {len(recap_text.split())} words")
    print(f" - Personal Notes length: {len(personal_notes.split())} words")
    successes = sum(1 for result in transcript_results if result.success)
    print(f" - Transcript successes: {successes}/{len(transcript_results)}")
    print("\n## STEP 5: BUILDING DOCUMENT")
    logger.info("Authenticating with Google...")
    creds = get_credentials()
    logger.info("Creating new Google Doc...")
    doc_id = create_google_doc(metadata.doc_title, creds)
    logger.info(f"... New Doc ID: {doc_id}")
    logger.info("Writing sections to doc...")
    use_ai = False
    try:
        use_ai = _prompt_yes_no("Would you like to format this document with OpenAI (gpt-5-nano)? (y/N): ")
    except Exception:
        use_ai = False

    if use_ai:
        try:
            logger.info("Formatting document with AI...")
            doc_body = format_document_with_ai(doc_body, model=config.OPENAI_MODEL)
            logger.info("AI formatting applied successfully.")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"AI formatting failed: {exc}")
            logger.info("Continuing with unformatted document.")
    try:
        write_doc_content(doc_id, doc_body, creds)
    except RuntimeError as exc:
        logger.error(f"Writing failed: {exc}")
        logger.info("Cleaning up the placeholder doc...")
        try:
            delete_google_doc(doc_id, creds)
            logger.info("Placeholder doc removed.")
        except Exception:  # noqa: BLE001
            logger.warning("Unable to remove the placeholder doc; please delete it manually.")
        raise
    print("... Success!\n")
    print("Your new document is ready in your Google Drive.")
    print(f"https://docs.google.com/document/d/{doc_id}/edit")


def _prompt_date(message: str) -> str:
    while True:
        response = input(message).strip()
        try:
            datetime.strptime(response, "%Y-%m-%d")
            return response
        except ValueError:
            print("Invalid date format. Please use YYYY-MM-DD.")


def _prompt_required(message: str) -> str:
    while True:
        response = input(message).strip()
        if response:
            return response
        print("This field is required.")


def _read_multiline(prompt: str) -> str:
    print(prompt)
    lines: List[str] = []
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        if line.strip() == "::end::":
            break
        lines.append(line.rstrip("\n"))
    content = "\n".join(lines).strip()
    if not content:
        raise ValueError("Input cannot be empty. Please paste your text before typing ::end::")
    return content


def _prompt_yes_no(message: str, default: bool = False) -> bool:
    while True:
        resp = input(f"{message}").strip().lower()
        if not resp:
            return default
        if resp in ("y", "yes"):
            return True
        if resp in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")


def _prompt_select_from_list(message: str, options: List[str]) -> str:
    print(message)
    for i, opt in enumerate(options, start=1):
        print(f" {i}) {opt}")
    while True:
        choice = input("Enter the number of your choice: ")
        try:
            idx = int(choice)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        except ValueError:
            pass
        print("Invalid selection; enter the number corresponding to your choice.")


__all__ = [
    "prompt_metadata",
    "prompt_play_by_play",
    "prompt_personal_notes",
    "prompt_video_ids",
    "main",
]
