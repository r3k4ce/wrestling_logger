from __future__ import annotations

import json
import os
import re
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from typing import List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
DEFAULT_TRANSCRIPT_LANGUAGES = ["en", "en-US"]
COOKIES_FILE_ENV = "YTDLP_COOKIES_FILE"
COOKIES_BROWSER_ENV = "YTDLP_COOKIES_FROM_BROWSER"


@dataclass
class ShowMetadata:
    event_date: str
    promotion: str
    show_name: str
    show_type: str = "TV"

    @property
    def doc_title(self) -> str:
        promo = re.sub(r"\s+", "_", self.promotion.strip().upper()) or "PROMO"
        show = re.sub(r"\s+", "_", self.show_name.strip().upper()) or "SHOW"
        show_type = re.sub(r"\s+", "_", self.show_type.strip().upper()) if self.show_type else "TV"
        return f"{self.event_date}_{promo}_{show_type}_{show}"


@dataclass
class TranscriptResult:
    video_id: str
    success: bool
    text: str | None = None
    error: str | None = None


class TranscriptLookupError(Exception):
    """Raised when yt-dlp cannot retrieve a transcript."""


def prompt_metadata() -> ShowMetadata:
    print("## STEP 1: METADATA\n")
    date_str = _prompt_date("Enter event date (YYYY-MM-DD): ")
    promotion = _prompt_required("Enter promotion (e.g., WWE or AEW): ")
    # Normalize promotion for lookups
    promo_key = promotion.strip().upper()
    # Known promotions and their TV shows
    KNOWN_PROMOTIONS: dict = {
        "WWE": ["RAW", "SMACKDOWN"],
        "AEW": ["DYNAMITE", "COLLISION"],
    }

    is_ppv = _prompt_yes_no("Is this a PPV (Pay-Per-View)? (y/N): ")
    show_type = "PPV" if is_ppv else "TV"
    if is_ppv:
        show_name = _prompt_required("Enter PPV show name (e.g., Royal Rumble): ")
    else:
        if promo_key in KNOWN_PROMOTIONS:
            options = KNOWN_PROMOTIONS[promo_key]
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


def fetch_transcripts(video_ids: List[str], languages: List[str] | None = None) -> List[TranscriptResult]:
    preferred_languages = _normalize_languages(languages)
    ydl_options = _build_ytdlp_options(preferred_languages)
    ydl = YoutubeDL(ydl_options)

    results: List[TranscriptResult] = []
    print(f"\nFetching {len(video_ids)} transcripts...")
    for video_id in video_ids:
        try:
            text = _fetch_single_transcript(ydl, video_id, preferred_languages)
            results.append(TranscriptResult(video_id=video_id, success=True, text=text))
            print(f"   > Transcript for '{video_id}' FOUND.")
        except TranscriptLookupError as exc:
            err = str(exc)
            results.append(TranscriptResult(video_id=video_id, success=False, error=err))
            print(f"   > Transcript for '{video_id}' FAILED: {err}.")
        except DownloadError as exc:
            err = f"yt-dlp error: {exc}"
            results.append(TranscriptResult(video_id=video_id, success=False, error=err))
            print(f"   > Transcript for '{video_id}' FAILED: {err}.")
        except Exception as exc:  # noqa: BLE001
            err = f"Unexpected error: {exc}"
            results.append(TranscriptResult(video_id=video_id, success=False, error=err))
            print(f"   > Transcript for '{video_id}' FAILED: {err}.")
    return results


def _fetch_single_transcript(ydl: YoutubeDL, video_id: str, languages: List[str]) -> str:
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    info = ydl.extract_info(video_url, download=False)
    if not info:
        raise TranscriptLookupError("Unable to fetch video metadata")

    text = _extract_caption_text(ydl, info, languages)
    if text:
        return text
    raise TranscriptLookupError("Transcript unavailable in requested languages")


def _normalize_languages(languages: List[str] | None) -> List[str]:
    provided = languages or []
    ordered = _dedupe_preserve_order(provided + DEFAULT_TRANSCRIPT_LANGUAGES)
    return ordered or DEFAULT_TRANSCRIPT_LANGUAGES.copy()


def _build_ytdlp_options(languages: List[str]) -> dict:
    subtitle_langs = _dedupe_preserve_order(languages + DEFAULT_TRANSCRIPT_LANGUAGES)
    options: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": subtitle_langs,
        "subtitlesformat": "json3",
        "cachedir": False,
    }

    cookies_file = os.getenv(COOKIES_FILE_ENV)
    cookies_browser = os.getenv(COOKIES_BROWSER_ENV)
    if cookies_file:
        options["cookiefile"] = cookies_file
    elif cookies_browser:
        options["cookiesfrombrowser"] = cookies_browser

    return options


def _extract_caption_text(ydl: YoutubeDL, info: dict, languages: List[str]) -> str | None:
    sources = _ordered_caption_sources(info)
    if not sources:
        return None

    for lang in languages:
        for source in sources:
            entries = source.get(lang)
            if not entries:
                continue
            for entry in _ensure_list(entries):
                text = _download_caption_entry(ydl, entry)
                if text:
                    return text

    for source in sources:  # fallback to any remaining caption
        for entries in source.values():
            for entry in _ensure_list(entries):
                text = _download_caption_entry(ydl, entry)
                if text:
                    return text
    return None


def _ordered_caption_sources(info: dict) -> List[dict]:
    requested = info.get("requested_subtitles") or {}
    subtitles = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}

    sources: List[dict] = []
    if requested:
        sources.append(requested)
    if subtitles:
        sources.append(subtitles)
    if automatic:
        sources.append(automatic)
    return sources


def _ensure_list(entries) -> List[dict]:
    if isinstance(entries, list):
        return entries
    if entries is None:
        return []
    return [entries]


def _download_caption_entry(ydl: YoutubeDL, entry: dict) -> str | None:
    url = entry.get("url")
    ext = (entry.get("ext") or "json3").lower()
    if not url:
        return None

    try:
        with closing(ydl.urlopen(url)) as response:
            data = response.read()
    except Exception:
        return None

    if ext == "json3":
        try:
            payload = json.loads(data.decode("utf-8"))
        except Exception:
            return None
        return _json3_payload_to_text(payload)

    try:
        text_data = data.decode("utf-8")
    except UnicodeDecodeError:
        text_data = data.decode("utf-8", errors="ignore")
    return _strip_caption_markup(text_data)


def _json3_payload_to_text(payload: dict) -> str:
    segments: List[str] = []
    for event in payload.get("events", []):
        for seg in event.get("segs", []) or []:
            chunk = seg.get("utf8", "").replace("\n", " ").strip()
            if chunk:
                segments.append(chunk)
    return " ".join(segments).strip()


TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3} --> ")
CUE_INDEX_RE = re.compile(r"^\d+$")


def _strip_caption_markup(raw_text: str) -> str:
    lines: List[str] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("WEBVTT") or stripped.startswith("NOTE"):
            continue
        if TIMESTAMP_RE.match(stripped) or CUE_INDEX_RE.match(stripped):
            continue
        lines.append(stripped)
    return " ".join(lines).strip()


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


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
        if not line:  # EOF
            break
        if line.strip() == "::end::":
            break
        lines.append(line.rstrip("\n"))
    content = "\n".join(lines).strip()
    if not content:
        raise ValueError("Input cannot be empty. Please paste your text before typing ::end::")
    return content


def _prompt_yes_no(message: str, default: bool = False) -> bool:
    default_str = "Y/n" if default else "y/N"
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


def build_document_body(
    metadata: ShowMetadata,
    recap_text: str,
    personal_notes: str,
    transcript_results: List[TranscriptResult],
) -> str:
    header = f"{metadata.event_date} | {metadata.promotion} | {metadata.show_name}\n\n"
    play_by_play_section = f"--- PLAY BY PLAY ANALYSIS ---\n{recap_text.strip()}\n\n"
    angle_section = f"--- YOUR ANGLE ---\n{personal_notes.strip()}\n\n"

    transcript_lines: List[str] = ["--- HIGHLIGHT TRANSCRIPTS ---"]
    for result in transcript_results:
        if result.success and result.text:
            transcript_lines.append(
                f"[Video ID: {result.video_id}]\n{result.text.strip()}\n"
            )
        else:
            transcript_lines.append(
                f"[Video ID: {result.video_id}] Transcript missing ({result.error}).\n"
            )
    transcripts_section = "\n".join(transcript_lines).strip() + "\n\n"

    summary_lines = ["--- TRANSCRIPT SUMMARY ---"]
    for result in transcript_results:
        status = "OK" if result.success else "FAILED"
        detail = "ready" if result.success else (result.error or "unknown error")
        summary_lines.append(f"- {result.video_id}: {status} ({detail})")
    summary_section = "\n".join(summary_lines)

    return header + play_by_play_section + angle_section + transcripts_section + summary_section


def get_credentials() -> Credentials:
    creds: Credentials | None = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    "Missing credentials.json. Follow the Drive/Docs quickstart to download it."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
    return creds


def create_google_doc(title: str, creds: Credentials) -> str:
    drive_service = build("drive", "v3", credentials=creds)
    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
    }
    try:
        file = (
            drive_service.files()
            .create(body=file_metadata, fields="id")
            .execute()
        )
    except HttpError as exc:  # noqa: BLE001
        raise RuntimeError(f"Unable to create Google Doc: {exc}") from exc
    return file["id"]


def write_doc_content(doc_id: str, content: str, creds: Credentials) -> None:
    docs_service = build("docs", "v1", credentials=creds)
    requests_body = {
        "requests": [
            {
                "insertText": {
                    "endOfSegmentLocation": {},
                    "text": content,
                }
            }
        ]
    }
    try:
        docs_service.documents().batchUpdate(documentId=doc_id, body=requests_body).execute()
    except HttpError as exc:  # noqa: BLE001
        reason = _extract_error_reason(exc)
        if reason == "SERVICE_DISABLED":
            raise RuntimeError(
                "Google Docs API is disabled for this project. Enable it at "
                "https://console.developers.google.com/apis/api/docs.googleapis.com"
                " and retry."
            ) from exc
        raise RuntimeError(f"Unable to write Google Doc content: {exc}") from exc


def delete_google_doc(doc_id: str, creds: Credentials) -> None:
    drive_service = build("drive", "v3", credentials=creds)
    drive_service.files().delete(fileId=doc_id).execute()


def _extract_error_reason(exc: HttpError) -> str | None:
    try:
        payload = json.loads(exc.content.decode("utf-8"))
        details = payload.get("error", {}).get("details")
        if isinstance(details, list):
            for detail in details:
                reason = detail.get("reason") or detail.get("metadata", {}).get("reason")
                if reason:
                    return reason
        if isinstance(payload.get("error"), dict):
            return payload["error"].get("status")
    except Exception:  # noqa: BLE001
        pass
    return None


def main() -> None:
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
    print("Authenticating with Google...")
    creds = get_credentials()
    print("Creating new Google Doc...")
    doc_id = create_google_doc(metadata.doc_title, creds)
    print(f"... New Doc ID: {doc_id}")
    print("Writing sections to doc...")
    try:
        write_doc_content(doc_id, doc_body, creds)
    except RuntimeError as exc:
        print(f"Writing failed: {exc}")
        print("Cleaning up the placeholder doc...")
        try:
            delete_google_doc(doc_id, creds)
            print("Placeholder doc removed.")
        except Exception:  # noqa: BLE001
            print("Warning: Unable to remove the placeholder doc; please delete it manually.")
        raise
    print("... Success!\n")
    print("Your new document is ready in your Google Drive.")
    print(f"https://docs.google.com/document/d/{doc_id}/edit")


if __name__ == "__main__":
    main()