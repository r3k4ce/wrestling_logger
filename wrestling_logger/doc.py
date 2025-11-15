"""Document construction and Google Docs helpers."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .transcripts import TranscriptResult

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


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
