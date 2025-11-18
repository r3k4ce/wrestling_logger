"""Configuration settings for the Wrestling Logger application."""
import os
from typing import List

# Google API Scopes
SCOPES: List[str] = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
]

# File paths
CREDENTIALS_FILE: str = os.getenv("WRESTLING_LOGGER_CREDENTIALS", "credentials.json")
TOKEN_FILE: str = os.getenv("WRESTLING_LOGGER_TOKEN", "token.json")

# Transcript settings
DEFAULT_TRANSCRIPT_LANGUAGES: List[str] = ["en", "en-US"]
COOKIES_FILE_ENV: str = "YTDLP_COOKIES_FILE"
COOKIES_BROWSER_ENV: str = "YTDLP_COOKIES_FROM_BROWSER"

# OpenAI settings
OPENAI_MODEL: str = "gpt-5-nano"
