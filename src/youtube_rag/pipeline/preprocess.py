from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

from ..core import config
from ..core.database import advance_stage, get_connection, mark_error
from ..core.models import TranscriptSegment
from ..core.utils import iter_with_progress
from ..rag.llm_client import active_model, llm_generate

CLEAN_TEXT_SYSTEM_PROMPT = (
    "You are a specialized linguistic corrector for high-level Chinese political and historical audio transcripts. "
    "The input is a raw Whisper ASR transcript. Your task is to fix phonetic/homophone errors (同音字) "
    "while maintaining the exact original narrative structure.\n\n"
    "CORE RULES:\n"
    "1. VIDEO TITLE AS SOURCE OF TRUTH: I will provide the video title in the user prompt. "
    "The names and terms in the title are 100% correct. If the transcript contains phonetic variations "
    "of names found in the title, you MUST correct them to match the title's spelling exactly.\n"
    "2. POLITICAL ENTITIES: Prioritize historical figures and political terms. "
    "Examples: '博呱呱' -> '薄瓜瓜', '李旺之' -> '李望知', '古墓' -> '谷牧', '古开来' -> '谷开来'.\n"
    "3. NO SUMMARIZATION: Do not shorten the text or 'clean up' the grammar. Keep it raw but correctly spelled.\n"
    "4. NO MARKDOWN: Return ONLY the raw cleaned Chinese string. No code blocks, no intro text.\n"
    "5. ALIGNMENT: Keep the character count within 2% of the input to ensure timestamp alignment."
)


def clean_text(provider: str, original_full_text: str, video_title: str) -> str:
    provider = provider.lower()
    max_chars = 15000 if provider == config.PROVIDER_OPENAI else 1500
    parts = split_text_by_char_budget(original_full_text, max_chars=max_chars)

    cleaned_parts: list[str] = []
    for part in parts:
        user_prompt = f"VIDEO TITLE: {video_title}\n\nTRANSCRIPT TO CLEAN:\n{part}"
        cleaned_parts.append(
            llm_generate(
                provider=provider,
                system=CLEAN_TEXT_SYSTEM_PROMPT,
                user=user_prompt,
                temperature=0,
            )
        )
        if provider == config.PROVIDER_GROQ and len(parts) > 1:
            time.sleep(5)

    return "".join(cleaned_parts)


def split_text_by_char_budget(full_text: str, max_chars: int) -> list[str]:
    if len(full_text) <= max_chars:
        return [full_text]
    parts: list[str] = []
    start = 0
    while start < len(full_text):
        end = min(start + max_chars, len(full_text))
        parts.append(full_text[start:end])
        start = end
    return parts


def load_transcript(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments") or []
    return {
        "video_id": data.get("video_id") or path.stem,
        "title": data.get("title") or path.stem,
        "youtube_url": data.get("youtube_url"),
        "segments": segments,
        "original_full_text": data.get("full_text"),
    }


def process_one_file(transcript_path: Path, output_dir: Path, provider: str, force: bool) -> bool:
    payload = load_transcript(transcript_path)
    video_id = str(payload["video_id"])
    video_title = payload.get("title", "Unknown Title")
    cleaned_path = output_dir / f"{video_id}.cleaned.json"

    if not force and cleaned_path.exists():
        logging.info("[SKIP] %s already cleaned", video_id)
        return True

    original_segments = [
        TranscriptSegment(
            start=float(seg.get("start", 0.0)),
            end=float(seg.get("end", 0.0)),
            text=str(seg.get("text", "")),
        )
        for seg in payload["segments"]
    ]
    original_full_text = str(payload["original_full_text"])

    try:
        cleaned_full_text = clean_text(provider, original_full_text, video_title)
    except TimeoutError:
        total = len(original_full_text)
        mid = total // 2
        cleaned_full_text = clean_text(provider, original_full_text[:mid], video_title) + clean_text(
            provider, original_full_text[mid:], video_title
        )
    except Exception as exc:
        logging.exception("[FAIL] %s (%s)", video_id, exc)
        return False

    cleaned_payload = {
        "video_id": video_id,
        "title": payload["title"],
        "youtube_url": payload.get("youtube_url"),
        "cleaned_full_text": cleaned_full_text,
        "segments": [
            {"start": seg.start, "end": seg.end, "text": seg.text}
            for seg in original_segments
        ],
    }

    with cleaned_path.open("w", encoding="utf-8") as f:
        json.dump(cleaned_payload, f, ensure_ascii=False, indent=2)

    logging.info("[OK] %s -> %s", video_id, cleaned_path.name)
    return True


def collect_pending_items(video_id: str | None = None, limit: int | None = None) -> list[tuple[str, Path]]:
    query = [
        "SELECT video_id, srt_path FROM videos",
        "WHERE pipeline_stage = ?",
    ]
    params: list[object] = ["transcribed"]

    if video_id:
        query.append("AND video_id = ?")
        params.append(video_id)

    query.append("ORDER BY download_date")
    if limit is not None:
        query.append("LIMIT ?")
        params.append(limit)

    with get_connection() as db:
        rows = db.execute(" ".join(query), params).fetchall()

    return [(str(row[0]), Path(row[1])) for row in rows if row[1]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean transcript JSON files with LLM")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N transcript files")
    parser.add_argument("--video-id", type=str, default=None, help="Process only one video_id")
    parser.add_argument("--force", action="store_true", help="Reprocess even if outputs already exist")
    return parser.parse_args()


def run_pending(video_id: str | None = None, limit: int | None = None, force: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    output_dir = Path(config.PROCESSED_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    items = collect_pending_items(video_id=video_id, limit=limit)
    if not items:
        logging.info("No transcribed videos pending preprocessing.")
        return

    provider = config.LLM_CLEANER.lower()
    logging.info("Cleaning provider=%s model=%s", provider, active_model(provider))

    success_count = 0
    fail_count = 0

    for current_video_id, transcript_path in iter_with_progress(items, desc="Preprocessing", unit="file"):
        cleaned_path = output_dir / f"{current_video_id}.cleaned.json"
        try:
            ok = process_one_file(
                transcript_path=transcript_path,
                output_dir=output_dir,
                provider=provider,
                force=force,
            )
        except Exception:
            ok = False
            logging.exception("[FAIL] %s unexpected preprocess failure", current_video_id)

        with get_connection() as db:
            if ok:
                db.execute(
                    "UPDATE videos SET cleaned_path = ? WHERE video_id = ?",
                    (str(cleaned_path.resolve()), current_video_id),
                )
                advance_stage(db, current_video_id, "cleaned")
                success_count += 1
            else:
                mark_error(db, current_video_id)
                fail_count += 1

    logging.info("Done. Success=%s, Failed=%s, Total=%s", success_count, fail_count, len(items))


def main() -> None:
    args = parse_args()
    run_pending(video_id=args.video_id, limit=args.limit, force=args.force)


if __name__ == "__main__":
    main()
