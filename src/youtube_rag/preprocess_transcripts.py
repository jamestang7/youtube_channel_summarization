from __future__ import annotations

import argparse
import gc
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib import error, request

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

from . import config

SYSTEM_PROMPT = (
    "You are an expert Chinese political and historical analyst. I will provide you with an "
    "AI-generated transcript from a YouTube video.\n"
    "Your tasks:\n"
    "- Clean up errors: Silently correct obvious phonetic/homophone mistakes (e.g., incorrectly "
    "transcribed names of historical figures or political terms).\n"
    "- Summarize: Provide a comprehensive summary of the video's main arguments and narrative.\n"
    "- Extract Entities: List the key people, organizations, and historical events mentioned.\n"
    "- Formatting: Output your response in clean Markdown format with headings for 'Summary', "
    "'Key Entities', and 'Core Arguments'. Do not include any conversational filler."
)

CLEAN_TEXT_SYSTEM_PROMPT = (
    "You are a careful Chinese transcript editor. Correct obvious homophone/ASR errors while "
    "preserving the original meaning and order. Output only the cleaned transcript text with no "
    "headings, markdown, or commentary. For instance, '楚军' should be '储君', and '古墓' should be "
    "the political figure '谷牧'."
)


class LLMClient:
    def __init__(self, provider: str, openai_model: str, ollama_model: str) -> None:
        self.provider = provider
        self.openai_model = openai_model
        self.ollama_model = ollama_model

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        if self.provider == "openai":
            return self._chat_openai(system_prompt, user_prompt)
        if self.provider == "ollama":
            return self._chat_ollama(system_prompt, user_prompt)
        raise ValueError(f"Unsupported LLM_PROVIDER: {self.provider}")

    def _chat_openai(self, system_prompt: str, user_prompt: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")

        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        url = f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.openai_model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        data = _post_json(url=url, payload=payload, headers=headers)
        return data["choices"][0]["message"]["content"].strip()

    def _chat_ollama(self, system_prompt: str, user_prompt: str) -> str:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        url = f"{base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        data = _post_json(url=url, payload=payload, headers={"Content-Type": "application/json"})
        return data["message"]["content"].strip()


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    req = request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP error {exc.code} for {url}: {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Connection error for {url}: {exc}") from exc


def build_summary_user_prompt(title: str, youtube_url: str | None, full_text: str) -> str:
    return (
        f"Video title: {title}\n"
        f"YouTube URL: {youtube_url or 'N/A'}\n"
        "\n"
        "Transcript:\n"
        f"{full_text}"
    )


def build_clean_text_user_prompt(title: str, full_text: str) -> str:
    return (
        f"Video title: {title}\n"
        "\n"
        "Please return the corrected transcript text only:\n"
        f"{full_text}"
    )


def load_transcript(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments") or []
    full_text = data.get("full_text")
    if not full_text:
        # Chinese handling: never insert spaces when stitching chunks
        full_text = "".join(str(seg.get("text", "")) for seg in segments)

    return {
        "video_id": data.get("video_id") or path.stem,
        "title": data.get("title") or path.stem,
        "full_text": full_text,
        "segments": segments,
        "youtube_url": data.get("youtube_url"),
    }


def cleanup_local_gpu_cache() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def process_one_file(transcript_path: Path, output_dir: Path, llm_client: LLMClient, force: bool) -> bool:
    payload = load_transcript(transcript_path)
    video_id = str(payload["video_id"])
    summary_path = output_dir / f"{video_id}.summary.md"
    cleaned_path = output_dir / f"{video_id}.cleaned.json"

    if not force and summary_path.exists() and cleaned_path.exists():
        logging.info("[SKIP] %s already processed", video_id)
        return True

    try:
        summary_markdown = llm_client.chat(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_summary_user_prompt(
                title=str(payload["title"]),
                youtube_url=payload.get("youtube_url"),
                full_text=str(payload["full_text"]),
            ),
        )
        cleaned_full_text = llm_client.chat(
            system_prompt=CLEAN_TEXT_SYSTEM_PROMPT,
            user_prompt=build_clean_text_user_prompt(
                title=str(payload["title"]),
                full_text=str(payload["full_text"]),
            ),
        )

        summary_path.write_text(summary_markdown, encoding="utf-8")
        cleaned_payload = {
            "video_id": video_id,
            "title": payload["title"],
            "youtube_url": payload.get("youtube_url"),
            "cleaned_full_text": cleaned_full_text,
            "segments": payload["segments"],
            "summary_markdown_path": str(summary_path),
        }
        with cleaned_path.open("w", encoding="utf-8") as f:
            json.dump(cleaned_payload, f, ensure_ascii=False, indent=2)

        logging.info("[OK] %s -> %s, %s", video_id, summary_path.name, cleaned_path.name)
        return True
    except Exception as exc:
        logging.exception("[FAIL] %s (%s)", video_id, exc)
        return False
    finally:
        if llm_client.provider == "ollama":
            cleanup_local_gpu_cache()


def collect_input_files(transcripts_dir: Path, video_id: str | None) -> list[Path]:
    if video_id:
        direct_match = transcripts_dir / f"{video_id}.json"
        if direct_match.exists():
            return [direct_match]

        matches = [p for p in transcripts_dir.glob("*.json") if p.stem == video_id]
        return sorted(matches)

    return sorted(transcripts_dir.glob("*.json"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preprocess transcript JSON files with LLM cleaning and summarization")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N transcript files")
    parser.add_argument("--video-id", type=str, default=None, help="Process only one video_id")
    parser.add_argument("--force", action="store_true", help="Reprocess even if outputs already exist")
    return parser.parse_args()


def main() -> None:
    if load_dotenv is not None:
        load_dotenv(config.ENV_FILE)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    transcripts_dir = Path(config.TRANSCRIPTS_DIR)
    output_dir = Path(config.PROCESSED_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = collect_input_files(transcripts_dir=transcripts_dir, video_id=args.video_id)
    if args.limit is not None:
        files = files[: args.limit]

    if not files:
        logging.info("No transcript files found to process in %s", transcripts_dir)
        return

    llm_client = LLMClient(
        provider=config.LLM_PROVIDER,
        openai_model=config.OPENAI_MODEL,
        ollama_model=config.OLLAMA_MODEL,
    )

    success_count = 0
    fail_count = 0
    for file_path in files:
        ok = process_one_file(
            transcript_path=file_path,
            output_dir=output_dir,
            llm_client=llm_client,
            force=args.force,
        )
        if ok:
            success_count += 1
        else:
            fail_count += 1

    logging.info("Done. Success=%s, Failed=%s, Total=%s", success_count, fail_count, len(files))


if __name__ == "__main__":
    args = parse_args()
    main()
