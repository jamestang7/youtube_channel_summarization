"""Shared configuration for the YouTube RAG monolith."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

WHISPER_MODEL = "CWTchen/Belle-whisper-large-v3-zh-punct-ct2-float32"
LOCAL_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"

# Provider constants
PROVIDER_OPENAI = "openai"
PROVIDER_GROQ = "groq"
PROVIDER_OLLAMA = "ollama"
SUPPORTED_PROVIDERS = (PROVIDER_OPENAI, PROVIDER_GROQ, PROVIDER_OLLAMA)

# LLM settings
LLM_CLEANER = PROVIDER_OPENAI
LLM_PROVIDER = PROVIDER_OPENAI
OPENAI_MODEL = "gpt-5.4-mini"
OLLAMA_MODEL = "llama3.1:8b"
GROQ_MODEL = "llama-3.3-70b-versatile"

# HTTP base URLs
OPENAI_BASE_URL = "https://api.openai.com/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OLLAMA_BASE_URL = "http://localhost:11434"

# Pipeline statuses
DOWNLOAD_STATUS_PENDING = "pending"
DOWNLOAD_STATUS_DOWNLOADED = "downloaded"
DOWNLOAD_STATUS_ERROR = "error"
TRANSCRIBE_STATUS_PENDING = "pending"
TRANSCRIBE_STATUS_TRANSCRIBED = "transcribed"
TRANSCRIBE_STATUS_ERROR = "error"
TRANSCRIBE_STATUS_ERROR_MISSING_MP3 = "error_missing_mp3"

BASE_DIR = Path(__file__).resolve().parent.parent.parent
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

load_dotenv(ENV_FILE)


def check_config() -> None:
    if not COOKIE_FILE.exists():
        raise FileNotFoundError(f"⚠️ Warning: Cookie file not found at {COOKIE_FILE}")
    if not (FFMPEG_BIN / "ffmpeg.exe").exists():
        raise FileNotFoundError(f"⚠️ Warning: FFmpeg.exe not found in {FFMPEG_BIN}")
    if not (FFMPEG_BIN / "ffprobe.exe").exists():
        raise FileNotFoundError(f"⚠️ Warning: FFprobe.exe not found in {FFMPEG_BIN}")
