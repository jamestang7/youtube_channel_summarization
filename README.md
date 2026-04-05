# youtube-channel-summarization

Local pipeline: **download YouTube audio** (yt-dlp, with optional cookies) → **transcribe** with **faster-whisper** → **clean / summarize** transcripts → **embed into ChromaDB** for retrieval.

## Setup (Windows + NVIDIA)

1. **Python 3.12+** recommended.
2. Install **PyTorch with CUDA** from [pytorch.org](https://pytorch.org/get-started/locally/) so `faster-whisper` and embeddings can use the GPU.
3. Install the project:

```bash
python -m pip install -e ".[dev]"
```

Or use pinned production dependencies only:

```bash
python -m pip install -r requirements.txt
```

4. Ensure your local requirements are ready:
   - valid `.env`
   - `HF_TOKEN`
   - `cookies.firefox-private.txt`
   - FFmpeg binaries in the configured folder
   - Ollama running locally if you use summarize

## Golden Path CLI

### 1. First-time initialization

```bash
uv run python -m youtube_rag.main update --channel-url "https://www.youtube.com/@zrzjpl"
```

This command:
- discovers channel videos
- downloads only missing videos
- transcribes pending videos
- preprocesses pending transcripts
- summarizes pending cleaned transcripts
- indexes pending items into the local knowledge base

### 2. Future channel updates

Use the same command again whenever the channel uploads a new video:

```bash
uv run python -m youtube_rag.main update --channel-url "https://www.youtube.com/@zrzjpl"
```

### 3. Ask the local knowledge base

```bash
uv run python -m youtube_rag.main ask --query "鲁社长怎么看薄熙来？"
```

### 4. Optionally add one video directly

```bash
uv run python -m youtube_rag.main add --video-url "https://www.youtube.com/watch?v=VIDEO_ID"
```

## Advanced / internal commands

These remain available for debugging or manual recovery, but they are not the recommended normal workflow:

```bash
uv run python -m youtube_rag.main ingest --channel-url "..."
uv run python -m youtube_rag.main transcribe
uv run python -m youtube_rag.main preprocess
uv run python -m youtube_rag.main summarize
uv run python -m youtube_rag.main index --pending-only
```

## Development

```bash
python -m pytest
```

## Running locally

Terminal 1 — Python API server:

```bash
uvicorn api:app --port 8000 --reload
```

Terminal 2 — Next.js frontend:

```bash
cd web && npm run dev
```

Then open http://localhost:3000
The search bar will now call the Python RAG backend.

To verify the API is running:

```bash
curl http://127.0.0.1:8000/health
```
