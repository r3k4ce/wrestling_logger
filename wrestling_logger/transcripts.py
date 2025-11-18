"""Transcript retrieval utilities backed by yt-dlp."""
from __future__ import annotations

import json
import logging
import os
import re
from contextlib import closing
from dataclasses import dataclass
from typing import List

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from . import config

logger = logging.getLogger(__name__)


@dataclass
class TranscriptResult:
    video_id: str
    success: bool
    text: str | None = None
    error: str | None = None


class TranscriptLookupError(Exception):
    """Raised when yt-dlp cannot retrieve a transcript."""


def fetch_transcripts(video_ids: List[str], languages: List[str] | None = None) -> List[TranscriptResult]:
    preferred_languages = _normalize_languages(languages)
    ydl_options = _build_ytdlp_options(preferred_languages)
    ydl = YoutubeDL(ydl_options)

    results: List[TranscriptResult] = []
    logger.info(f"Fetching {len(video_ids)} transcripts...")
    for video_id in video_ids:
        try:
            text = _fetch_single_transcript(ydl, video_id, preferred_languages)
            results.append(TranscriptResult(video_id=video_id, success=True, text=text))
            logger.info(f"   > Transcript for '{video_id}' FOUND.")
        except TranscriptLookupError as exc:
            err = str(exc)
            results.append(TranscriptResult(video_id=video_id, success=False, error=err))
            logger.warning(f"   > Transcript for '{video_id}' FAILED: {err}.")
        except DownloadError as exc:
            err = f"yt-dlp error: {exc}"
            results.append(TranscriptResult(video_id=video_id, success=False, error=err))
            logger.error(f"   > Transcript for '{video_id}' FAILED: {err}.")
        except Exception as exc:  # noqa: BLE001
            err = f"Unexpected error: {exc}"
            results.append(TranscriptResult(video_id=video_id, success=False, error=err))
            logger.error(f"   > Transcript for '{video_id}' FAILED: {err}.")
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
    ordered = _dedupe_preserve_order(provided + config.DEFAULT_TRANSCRIPT_LANGUAGES)
    return ordered or config.DEFAULT_TRANSCRIPT_LANGUAGES.copy()


def _build_ytdlp_options(languages: List[str]) -> dict:
    subtitle_langs = _dedupe_preserve_order(languages + config.DEFAULT_TRANSCRIPT_LANGUAGES)
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

    cookies_file = os.getenv(config.COOKIES_FILE_ENV)
    cookies_browser = os.getenv(config.COOKIES_BROWSER_ENV)
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
