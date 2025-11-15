"""OpenAI-powered document formatting utilities."""
from __future__ import annotations

import os

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore[assignment]


def format_document_with_ai(content: str, model: str = "gpt-5-nano") -> str:
    """Format `content` using OpenAI while preserving its words."""
    if OpenAI is None:
        raise RuntimeError(
            "openai package not installed. Install via `pip install openai>=1.0.0` to use AI formatting."
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable not set.")
    client = OpenAI(api_key=api_key)

    MAX_TOTAL_CHARS = 1_000_000
    if len(content) > MAX_TOTAL_CHARS:
        raise RuntimeError(
            f"Document too large for AI formatting ({len(content)} chars). Please shorten or skip AI formatting."
        )

    system_prompt = (
        "You are an assistant that only formats the provided text. Do not rewrite, change, or omit any words or punctuation. "
        "Only adjust spacing, line breaks, and add clear headers while keeping all content identical. Output ONLY the formatted text — no explanations, no notes."
    )

    user_instructions = (
        "Input is a wrestling recap document with sections such as a date header, play-by-play text, personal notes, and raw transcript blocks. "
        "Please format the document as follows: \n"
        " - Keep all text exactly as-is; DO NOT change sentence meaning or wording. \n"
        " - Keep the title/header (line like `YYYY-MM-DD | PROMOTION | SHOW`) at the very top, centered or preserved. \n"
        " - Convert section markers `--- ... ---` into clearly labeled bold uppercase section headers, separated by a single blank line. For example, `--- PLAY BY PLAY ANALYSIS ---` becomes `*** PLAY BY PLAY ANALYSIS ***`.\n"
        " - Ensure that the Play-by-Play and Your Angle sections are separated by blank lines and retain paragraph breaks.\n"
        " - For each transcript: add a single-line header like `VIDEO TRANSCRIPT: <video_id>` and then put the transcript content in a quoted block (preserve line breaks).\n"
        " - After formatting, provide a short transcript summary but keep it in the same place.\n"
        " - Output must be plain text without code fences or markdown headings other than plaintext bold-like markers (e.g., `*** HEADER ***`).\n"
        " - Preserve the order and all characters of the content.\n"
        "Now format the following document exactly as requested.\n\n"
    )

    CHUNK_MAX_CHARS = 10_000
    chunks = _split_into_chunks(content, CHUNK_MAX_CHARS)

    formatted_chunks: list[str] = []
    if not chunks:
        return ""
    try:
        for i, chunk in enumerate(chunks, start=1):
            prompt = user_instructions + f"(Chunk {i}/{len(chunks)})\n\n" + chunk
            completion_args = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "n": 1,
            }
            if isinstance(model, str) and model.startswith("gpt-5"):
                completion_args["max_completion_tokens"] = 4096
            else:
                completion_args["max_tokens"] = 4096
                completion_args["temperature"] = 0.0

            response = client.chat.completions.create(**completion_args)
            choices = getattr(response, "choices", []) or []
            if not choices:
                raise RuntimeError("AI returned no choices; formatted content unavailable.")
            message_obj = getattr(choices[0], "message", {}) or {}
            if isinstance(message_obj, dict):
                message_content = message_obj.get("content", "")
            else:
                message_content = getattr(message_obj, "content", "")
            formatted_text = _message_content_to_text(message_content)
            if not formatted_text.strip():
                print(
                    f"[WARN] AI returned empty formatted content for chunk {i}/{len(chunks)}; keeping original chunk text."
                )
                formatted_text = chunk
            formatted_chunks.append(formatted_text)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"AI formatting failed: {exc}") from exc

    return "\n".join(formatted_chunks)


def _split_into_chunks(text: str, chunk_size: int) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    pos = 0
    length = len(text)
    while pos < length:
        end = min(pos + chunk_size, length)
        if end < length:
            split_at = text.rfind("\n", pos, end)
            if split_at <= pos:
                split_at = text.rfind(" ", pos, end)
            if split_at <= pos:
                split_at = end
        else:
            split_at = end
        chunks.append(text[pos:split_at])
        pos = split_at
        while pos < length and text[pos] in ("\n", " "):
            pos += 1
    return chunks


def _message_content_to_text(message_content) -> str:
    if not message_content:
        return ""
    if isinstance(message_content, str):
        return message_content
    if isinstance(message_content, list):
        parts: list[str] = []
        for item in message_content:
            text_piece = ""
            if isinstance(item, str):
                text_piece = item
            elif isinstance(item, dict):
                text_piece = item.get("text") or item.get("content") or ""
            elif hasattr(item, "text"):
                text_piece = getattr(item, "text", "") or ""
            elif hasattr(item, "content"):
                text_piece = getattr(item, "content", "") or ""
            if text_piece:
                parts.append(str(text_piece))
        return "".join(parts)
    return str(message_content)


__all__ = ["format_document_with_ai", "OpenAI"]
