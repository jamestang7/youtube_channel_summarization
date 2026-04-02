# youtube-channel-summarization

Local pipeline: **download YouTube audio** (yt-dlp, with optional cookies) → **transcribe** with **faster-whisper** → **chunk + embed** with **LangChain** + **sentence-transformers** → **ChromaDB** for retrieval.

## Setup (Windows + NVIDIA)

1. **Python 3.12+** recommended.

2. Install **PyTorch with CUDA** from [pytorch.org](https://pytorch.org/get-started/locally/) so `faster-whisper` and embeddings can use the GPU (8GB-class cards: prefer `distil-small.en` / `small` and `int8_float16`).

3. Install the project:

```bash
python -m pip install -e ".[dev]"
```

Or use pinned production dependencies only:

```bash
python -m pip install -r requirements.txt
```

4. **FFmpeg**: the repo depends on `static-ffmpeg`, which tries to ship a binary. If audio extraction still fails, install FFmpeg and ensure `ffmpeg` is on `PATH`.

## CLI

```bash
python -m youtube_rag.main --url "https://www.youtube.com/watch?v=VIDEO_ID" --language en
```

Installed entry point (after editable install):

```bash
youtube-rag --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Members-only / subscriber content

Use a **Netscape cookie file** or **browser cookies** (same semantics as yt-dlp):

```bash
python -m youtube_rag.main --url "..." --cookies-from-browser chrome
python -m youtube_rag.main --url "..." --cookies-file "C:\Users\you\cookies-youtube-com.txt"
```

Do **not** commit cookie files. Refresh cookies if you see HTTP 403 / sign-in errors.

### Live streams

```bash
python -m youtube_rag.main --url "..." --live-from-start
python -m youtube_rag.main --url "..." --wait-for-video 15
```

## Layout

- `src/youtube_rag/youtube_ingest.py` — yt-dlp wrapper, typed errors, cookie + live flags.
- `src/youtube_rag/transcriber.py` — faster-whisper segmentation.
- `src/youtube_rag/vector_db.py` — chunking w/ timestamps, Chroma ingest.
- `src/youtube_rag/main.py` — argparse orchestrator.

Artifacts:

- Audio: `downloads/` by default.
- Vectors: `chroma_data/` default persistence directory.

## Development

```bash
python -m pytest
```
 yt-dlp "https://www.youtube.com/watch?v=rd-oTL3PlKc&t=822s" --cookies .\cookies.firefox-private.txt --extractor-args "youtube:player-client=mweb" --js-runtimes node --extract-audio --audio-format mp3 --remote-components ejs:github --ffmpeg-location .\ffmpeg-2026-03-26-git-fd9f1e9c52-essentials_build\bin\