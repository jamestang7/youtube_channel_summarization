"""Local path configuration for the YouTube ingest + transcription pipeline.

All paths are expressed so they work on Windows. ``BASE_DIR`` is the directory
containing this file (the ``youtube_rag`` package folder).
"""

from __future__ import annotations

import os
from pathlib import Path

WHISPER_MODEL = "CWTchen/Belle-whisper-large-v3-zh-punct-ct2-float32"
LOCAL_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"

# LLM settings
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()  # openai | ollama
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# 1. Get the absolute path of the folder containing this file
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 2. Define the raw paths (Using raw strings r'' for Windows backslashes)
# We use .joinpath() to glue paths together safely
COOKIE_FILE = BASE_DIR / "cookies.firefox-private.txt"
FFMPEG_BIN = BASE_DIR / "ffmpeg-2026-03-26-git-fd9f1e9c52-essentials_build" / "bin"
DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "project.db"
AUDIO_DIR = DATA_DIR / "audio"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
TRANSCRIPT_DIR = TRANSCRIPTS_DIR  # Backward-compatible alias
PROCESSED_DIR = DATA_DIR / "processed"
ENV_FILE = BASE_DIR / ".env"
CHROMA_DB_DIR = DATA_DIR / "chroma_db"


def check_config():
    """A simple helper to make sure your files actually exist before starting."""
    if not COOKIE_FILE.exists():
        raise FileNotFoundError(f"⚠️ Warning: Cookie file not found at {COOKIE_FILE}")
    if not (FFMPEG_BIN / "ffmpeg.exe").exists():
        raise FileNotFoundError(f"⚠️ Warning: FFmpeg.exe not found in {FFMPEG_BIN}")
    if not (FFMPEG_BIN / "ffprobe.exe").exists():
        raise FileNotFoundError(f"⚠️ Warning: FFprobe.exe not found in {FFMPEG_BIN}")
