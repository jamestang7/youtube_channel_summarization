# YouTube Channel Summarization

A local YouTube transcript RAG system for Chinese-language channels.

This project does three main jobs:
- downloads videos from a YouTube channel
- transcribes audio with `faster-whisper`
- turns transcripts into a searchable knowledge base with ChromaDB

It also includes a web interface built with Next.js and a small FastAPI backend for question answering.

## What is in this repository?

### Backend (`src/`)
The Python backend handles the ingestion and RAG pipeline:
- `src/youtube_rag/pipeline/ingest.py` — discover channel videos and download audio
- `src/youtube_rag/pipeline/transcribe.py` — generate transcripts
- `src/youtube_rag/pipeline/preprocess.py` — clean transcript text
- `src/youtube_rag/pipeline/summarize.py` — create summaries
- `src/youtube_rag/rag/indexer.py` — write embeddings into ChromaDB
- `src/youtube_rag/rag/search_engine.py` — retrieve chunks and answer questions
- `src/youtube_rag/main.py` — CLI entry point

### Web app (`web/`)
The frontend is a Next.js app with:
- homepage with trending questions and recent videos
- search page for asking questions against the local RAG backend
- outline pages for processed videos
- API routes that proxy requests to the Python backend

### API (`api.py`)
A minimal FastAPI server that exposes:
- `GET /health`
- `POST /api/ask`

## How the pipeline works

The normal workflow is:

1. sync a YouTube channel
2. download missing audio
3. transcribe pending videos
4. clean transcripts
5. summarize cleaned transcripts
6. index them into ChromaDB
7. ask questions with source citations and timestamps

## Requirements

- Windows 11 recommended
- Python `3.12.x`
- NVIDIA GPU recommended for transcription and embeddings
- FFmpeg binaries available locally
- a valid YouTube cookies file if required for downloads
- local or remote LLM access depending on your configuration

## Python dependencies

This project is managed with `uv` and defined in `pyproject.toml`.

Important packages include:
- `yt-dlp`
- `faster-whisper`
- `chromadb`
- `sentence-transformers`
- `fastapi`
- `uvicorn`
- CUDA-enabled `torch`

## Installation

### 1. Create and activate an environment

Using `uv`:

```bash
uv venv
.venv\Scripts\activate
```

### 2. Install dependencies

Development install:

```bash
uv sync
```

If you prefer `pip`:

```bash
python -m pip install -e ".[dev]"
```

## Configuration

Create a root-level `.env` file and configure the models and providers you want to use.

Current config values are loaded from `src/youtube_rag/core/config.py`.

Examples of important settings:
- `OPENAI_MODEL`
- `OPENAI_BASE_URL`
- `GROQ_MODEL`
- `GROQ_BASE_URL`
- `OLLAMA_MODEL`
- `OLLAMA_BASE_URL`
- `LLM_CLEANER`
- `LLM_PROVIDER`

The backend also expects these local paths to exist:
- `cookies.firefox-private.txt`
- `ffmpeg-.../bin/ffmpeg.exe`
- `ffmpeg-.../bin/ffprobe.exe`

## Data directories

Generated data is stored under `data/`:
- `data/audio/` — downloaded audio files
- `data/transcripts/` — raw transcripts
- `data/processed/` — cleaned transcript JSON files
- `data/chroma_db/` — vector database
- `data/project.db` — SQLite / DuckDB-style project metadata database used by the app

## CLI usage

The main CLI entry point is:

```bash
uv run python -m youtube_rag.main
```

### Sync and process a full channel

```bash
uv run python -m youtube_rag.main update --channel-url "https://www.youtube.com/@your-channel"
```

This is the recommended command for normal use.

### Watch a channel continuously

```bash
uv run python -m youtube_rag.main update --channel-url "https://www.youtube.com/@your-channel" --watch
```

### Add a single video

```bash
uv run python -m youtube_rag.main add --video-url "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Ask the knowledge base

```bash
uv run python -m youtube_rag.main ask --query "What does this channel say about a given topic?"
```

## Run the backend API

Start the FastAPI server:

```bash
uv run uvicorn api:app --host 127.0.0.1 --port 8000 --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Run the web app

From the `web/` directory:

```bash
npm install
npm run dev
```

The web app runs at:
- `http://localhost:3000`

By default, the frontend sends search requests to:
- `http://127.0.0.1:8000/api/ask`

You can override that in `web/.env.local` with:

```bash
BACKEND_ASK_URL=http://127.0.0.1:8000/api/ask
```

## Full local development flow

Use two terminals.

### Terminal 1 — Python backend

```bash
uv run uvicorn api:app --host 127.0.0.1 --port 8000 --reload
```

### Terminal 2 — Next.js frontend

```bash
cd web
npm install
npm run dev
```

Then open:

```text
http://localhost:3000
```

## Frontend routes

Main routes in `web/app/`:
- `/` — homepage
- `/search` — search and answer page
- `/video/[videoId]/outline` — outline view for one processed video

API routes in the web app:
- `/api/ask`
- `/api/events`
- `/api/outline/[videoId]`

## Notes about models

The current backend configuration uses:
- Whisper model: `CWTchen/Belle-whisper-large-v3-zh-punct-ct2-float32`
- Embedding model: `BAAI/bge-small-zh-v1.5`

The default answering provider is controlled by `LLM_PROVIDER`.

## Development and testing

Run tests:

```bash
python -m pytest
```

## Troubleshooting

### Backend cannot start
Check:
- Python version is `3.12`
- `.env` exists
- FFmpeg binaries are present
- the cookies file exists if your downloads need it

### Frontend cannot answer questions
Check:
- FastAPI is running on port `8000`
- `BACKEND_ASK_URL` points to the correct backend
- the channel has already been processed and indexed

### No search results
Check:
- the pipeline has completed indexing
- `data/chroma_db/` exists
- processed transcript files exist in `data/processed/`

## Repository structure

```text
.
├── api.py
├── README.md
├── pyproject.toml
├── src/
│   └── youtube_rag/
│       ├── core/
│       ├── pipeline/
│       ├── rag/
│       └── main.py
├── web/
│   ├── app/
│   ├── components/
│   └── lib/
└── data/
```
