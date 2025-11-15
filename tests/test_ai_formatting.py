from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from create_show_doc import format_document_with_ai, OpenAI


def _patch_openai(monkeypatch: pytest.MonkeyPatch, factory):
    monkeypatch.setattr("create_show_doc.OpenAI", factory)
    monkeypatch.setattr("wrestling_logger.ai_format.OpenAI", factory)


AI_TEST_PROMPT = "2025-11-10 | WWE | RAW\n--- PLAY BY PLAY ANALYSIS ---\nWWE Raw Results\n"


def test_ai_formatting_returns_text(monkeypatch):
    """Ensure the AI formatting helper can format a short sample document."""
    # Monkeypatch the OpenAI client so tests do not call the real API
    class DummyCompletions:
        def __init__(self):
            self.called_with = None

        def create(self, **kwargs):
            self.called_with = kwargs
            class _Message:
                def __init__(self):
                    self.content = AI_TEST_PROMPT

            class _Choice:
                def __init__(self):
                    self.message = _Message()

            return type("Resp", (), {"choices": [_Choice()]})()

    class DummyChat:
        def __init__(self):
            self.completions = DummyCompletions()

    class DummyClient:
        def __init__(self, api_key=None):
            self.chat = DummyChat()

    monkeypatch.setenv("OPENAI_API_KEY", "testkey")
    _patch_openai(monkeypatch, lambda api_key=None: DummyClient(api_key=api_key))

    formatted = format_document_with_ai(AI_TEST_PROMPT)
    assert isinstance(formatted, str)
    assert AI_TEST_PROMPT.strip() in formatted


def test_other_features_placeholder() -> None:  # pragma: no cover
    """Placeholder for future tests covering the rest of the script."""
    pytest.skip("Pending future feature tests")


def test_model_param_selection(monkeypatch):
    """Ensure we set the correct param for gpt-5 family and older models."""
    # Build a dummy completions.create shim to capture received kwargs
    class DummyCompletions:
        def __init__(self):
            self.called_with = None

        def create(self, **kwargs):
            self.called_with = kwargs
            class _Message:
                def __init__(self):
                    self.content = "ok"

            class _Choice:
                def __init__(self):
                    self.message = _Message()

            return type("Resp", (), {"choices": [_Choice()]})()

    # Shared completions instance so tests can inspect what was called
    dummy_completions = DummyCompletions()

    class DummyChat:
        def __init__(self):
            self.completions = dummy_completions

    class DummyClient:
        def __init__(self, api_key=None):
            self.chat = DummyChat()

    monkeypatch.setenv("OPENAI_API_KEY", "testkey")
    _patch_openai(monkeypatch, lambda api_key=None: DummyClient(api_key=api_key))

    # Call with a gpt-5 model name
    formatted = format_document_with_ai(AI_TEST_PROMPT, model="gpt-5-nano")
    assert isinstance(formatted, str)
    # Verify the captured call used the `max_completion_tokens` kwarg
    assert isinstance(dummy_completions.called_with, dict)
    assert "max_completion_tokens" in dummy_completions.called_with

    # Now check with an older model name — should use max_tokens instead
    dummy_completions.called_with = None
    formatted2 = format_document_with_ai(AI_TEST_PROMPT, model="gpt-4o")
    assert isinstance(formatted2, str)
    assert isinstance(dummy_completions.called_with, dict)
    assert "max_tokens" in dummy_completions.called_with


def test_chunking_long_input(monkeypatch):
    """Ensure long documents are chunked and processed across multiple calls."""
    # Build a dummy completions.create shim to capture received kwargs and return the
    # user's chunk as the formatted response (simulating an identity format pass).
    class DummyCompletions:
        def __init__(self):
            self.call_count = 0

        def create(self, **kwargs):
            self.call_count += 1
            messages = kwargs.get("messages") or []
            # The chunked content is in the user's message (index 1) after the
            # instructions; slice out the tail which contains the chunk text.
            user_text = ""
            if len(messages) >= 2:
                user_text = messages[1].get("content", "")
                # Attempt to find the start of the chunk by searching for the
                # chunk marker we insert in the prompt: '(Chunk'. Fallback to
                # returning the whole user_text if marker not found.
                marker = "(Chunk"
                marker_idx = user_text.find(marker)
                if marker_idx != -1:
                    # The actual chunk content follows the marker line after
                    # a blank line; find the first blank-line separator.
                    sep = "\n\n"
                    sep_idx = user_text.find(sep, marker_idx)
                    if sep_idx != -1:
                        chunk_text = user_text[sep_idx + len(sep) :]
                    else:
                        chunk_text = user_text[marker_idx:]
                else:
                    chunk_text = user_text
            else:
                chunk_text = ""

            class _Message:
                def __init__(self, content):
                    self.content = content

            class _Choice:
                def __init__(self, content):
                    self.message = _Message(content)

            return type("Resp", (), {"choices": [_Choice(chunk_text)]})()

    dummy_completions = DummyCompletions()

    class DummyChat:
        def __init__(self):
            self.completions = dummy_completions

    class DummyClient:
        def __init__(self, api_key=None):
            self.chat = DummyChat()

    monkeypatch.setenv("OPENAI_API_KEY", "testkey")
    _patch_openai(monkeypatch, lambda api_key=None: DummyClient(api_key=api_key))

    # Build a long document that contains a clear START and END marker.
    long_doc = ("START\n" + AI_TEST_PROMPT + "\n") + (AI_TEST_PROMPT * 300) + ("\nEND")
    assert len(long_doc) > 10_000

    formatted = format_document_with_ai(long_doc, model="gpt-5-nano")
    # The dummy returns chunk_text so the assembled value should contain both START and END
    assert "START" in formatted
    assert "END" in formatted
    # There should have been multiple create calls for the long document
    assert dummy_completions.call_count > 1


def test_chunk_empty_response_fallback(monkeypatch):
    """If the AI returns empty output, we should fallback to the original chunk."""

    class DummyCompletions:
        def __init__(self):
            self.call_count = 0

        def create(self, **kwargs):
            self.call_count += 1

            class _Message:
                def __init__(self):
                    self.content = ""

            class _Choice:
                def __init__(self):
                    self.message = _Message()

            return type("Resp", (), {"choices": [_Choice()]})()

    dummy_completions = DummyCompletions()

    class DummyChat:
        def __init__(self):
            self.completions = dummy_completions

    class DummyClient:
        def __init__(self, api_key=None):
            self.chat = DummyChat()

    monkeypatch.setenv("OPENAI_API_KEY", "testkey")
    _patch_openai(monkeypatch, lambda api_key=None: DummyClient(api_key=api_key))

    formatted = format_document_with_ai(AI_TEST_PROMPT, model="gpt-5-nano")
    assert formatted.strip() == AI_TEST_PROMPT.strip()
    assert dummy_completions.call_count == 1


def test_message_content_list_is_parsed(monkeypatch):
    """Ensure list-based message content from OpenAI is combined into text."""

    class DummyMessage:
        def __init__(self):
            self.content = [
                {"type": "output_text", "text": "START\n"},
                "MIDDLE",
                {"type": "output_text", "text": "\nEND"},
            ]

    class DummyCompletions:
        def __init__(self):
            self.called = False

        def create(self, **kwargs):
            self.called = True

            class _Choice:
                def __init__(self):
                    self.message = DummyMessage()

            return type("Resp", (), {"choices": [_Choice()]})()

    dummy_completions = DummyCompletions()

    class DummyChat:
        def __init__(self):
            self.completions = dummy_completions

    class DummyClient:
        def __init__(self, api_key=None):
            self.chat = DummyChat()

    monkeypatch.setenv("OPENAI_API_KEY", "testkey")
    _patch_openai(monkeypatch, lambda api_key=None: DummyClient(api_key=api_key))

    formatted = format_document_with_ai("header\nbody", model="gpt-4o")
    assert "START" in formatted
    assert "END" in formatted
    assert dummy_completions.called
