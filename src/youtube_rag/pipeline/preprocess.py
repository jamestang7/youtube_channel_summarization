from __future__ import annotations

import argparse
import difflib
import json
import logging
import time
from pathlib import Path
from typing import Any, Iterator, TypeVar

from ..core import config
from ..core.models import TranscriptSegment
from ..rag.llm_client import LLMChatClient

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover - optional dependency
    tqdm = None

T = TypeVar("T")

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


class TranscriptCleanerClient:
    def __init__(self, provider: str) -> None:
        if provider not in {config.PROVIDER_OPENAI, config.PROVIDER_GROQ}:
            raise RuntimeError(f"Unsupported cleaner provider: {provider}")
        self.provider = provider
        self.chat_client = LLMChatClient(provider=provider)

    def active_model(self) -> str:
        return self.chat_client.active_model()

    def clean_text(self, original_full_text: str, video_title: str) -> str:
        max_chars = 15000 if self.provider == config.PROVIDER_OPENAI else 1500
        parts = self._split_text_by_char_budget(original_full_text, max_chars=max_chars)

        cleaned_parts: list[str] = []
        for part in parts:
            user_prompt = f"VIDEO TITLE: {video_title}\n\nTRANSCRIPT TO CLEAN:\n{part}"
            cleaned_parts.append(
                self.chat_client.generate(
                    system_prompt=CLEAN_TEXT_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0,
                )
            )
            if self.provider == config.PROVIDER_GROQ and len(parts) > 1:
                time.sleep(5)

        return "".join(cleaned_parts)

    @staticmethod
    def _split_text_by_char_budget(full_text: str, max_chars: int) -> list[str]:
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


def align_segments(original_segments: list[dict[str, Any]], cleaned_full_text: str) -> list[dict[str, Any]]:
    typed_segments = [
        TranscriptSegment(
            start=float(seg.get("start", 0.0)),
            end=float(seg.get("end", 0.0)),
            text=str(seg.get("text", "")),
        )
        for seg in original_segments
    ]
    original_full_text = "".join(seg.text for seg in typed_segments)

    boundaries = [0]
    for seg in typed_segments:
        boundaries.append(boundaries[-1] + len(seg.text))

    mapped_boundaries = _map_boundaries_with_difflib(
        original_text=original_full_text,
        cleaned_text=cleaned_full_text,
        boundaries=boundaries,
    )

    cleaned_segments: list[dict[str, Any]] = []
    for i, seg in enumerate(original_segments):
        start_j = mapped_boundaries[i]
        end_j = mapped_boundaries[i + 1]
        if end_j < start_j:
            end_j = start_j

        updated = dict(seg)
        updated["text"] = cleaned_full_text[start_j:end_j]
        cleaned_segments.append(updated)

    return cleaned_segments


def _map_boundaries_with_difflib(original_text: str, cleaned_text: str, boundaries: list[int]) -> list[int]:
    matcher = difflib.SequenceMatcher(a=original_text, b=cleaned_text, autojunk=False)
    opcodes = matcher.get_opcodes()

    mapped: list[int] = []
    op_idx = 0

    for boundary in boundaries:
        while op_idx < len(opcodes) - 1 and boundary > opcodes[op_idx][2]:
            op_idx += 1

        tag, i1, i2, j1, j2 = opcodes[op_idx]

        if tag == "equal":
            mapped_index = j1 + (boundary - i1)
        elif tag == "replace":
            span_i = max(i2 - i1, 1)
            span_j = j2 - j1
            ratio = (boundary - i1) / span_i
            mapped_index = j1 + int(round(ratio * span_j))
        elif tag == "delete":
            mapped_index = j1
        else:  # insert
            mapped_index = j2 if boundary >= i1 else j1

        mapped_index = max(0, min(len(cleaned_text), mapped_index))
        if mapped and mapped_index < mapped[-1]:
            mapped_index = mapped[-1]
        mapped.append(mapped_index)

    return mapped


def process_one_file(transcript_path: Path, output_dir: Path, client: TranscriptCleanerClient, force: bool) -> bool:
    payload = load_transcript(transcript_path)
    video_id = str(payload["video_id"])
    video_title = payload.get("title", "Unknown Title")
    cleaned_path = output_dir / f"{video_id}.cleaned.json"

    if not force and cleaned_path.exists():
        logging.info("[SKIP] %s already cleaned", video_id)
        return True

    original_segments = payload["segments"]
    original_full_text = str(payload["original_full_text"])

    try:
        cleaned_full_text = client.clean_text(original_full_text, video_title)
    except TimeoutError:
        total = len(original_full_text)
        mid = total // 2
        cleaned_full_text = client.clean_text(original_full_text[:mid], video_title) + client.clean_text(
            original_full_text[mid:], video_title
        )
    except Exception as exc:
        logging.exception("[FAIL] %s (%s)", video_id, exc)
        return False

    cleaned_segments = align_segments(
        original_segments=original_segments,
        cleaned_full_text=cleaned_full_text,
    )

    cleaned_payload = {
        "video_id": video_id,
        "title": payload["title"],
        "youtube_url": payload.get("youtube_url"),
        "cleaned_full_text": cleaned_full_text,
        "segments": cleaned_segments,
    }

    with cleaned_path.open("w", encoding="utf-8") as f:
        json.dump(cleaned_payload, f, ensure_ascii=False, indent=2)

    logging.info("[OK] %s -> %s", video_id, cleaned_path.name)
    return True


def collect_input_files(transcripts_dir: Path, video_id: str | None) -> list[Path]:
    if video_id:
        direct_match = transcripts_dir / f"{video_id}.json"
        if direct_match.exists():
            return [direct_match]

        matches = [p for p in transcripts_dir.glob("*.json") if p.stem == video_id]
        return sorted(matches)

    return sorted(transcripts_dir.glob("*.json"))


def iter_with_progress(items: list[T], desc: str) -> Iterator[T]:
    if tqdm is not None:
        yield from tqdm(items, desc=desc, unit="file")
        return
    total = len(items)
    for idx, item in enumerate(items, start=1):
        logging.info("%s [%d/%d]", desc, idx, total)
        yield item


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean transcript JSON files with LLM + difflib alignment")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N transcript files")
    parser.add_argument("--video-id", type=str, default=None, help="Process only one video_id")
    parser.add_argument("--force", action="store_true", help="Reprocess even if outputs already exist")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    transcripts_dir = Path(config.TRANSCRIPTS_DIR)
    output_dir = Path(config.PROCESSED_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    args = parse_args()
    files = collect_input_files(transcripts_dir=transcripts_dir, video_id=args.video_id)
    if args.limit is not None:
        files = files[: args.limit]

    if not files:
        logging.info("No transcript files found to process in %s", transcripts_dir)
        return

    provider = config.LLM_CLEANER.lower()
    client = TranscriptCleanerClient(provider=provider)
    logging.info("Cleaning provider=%s model=%s", provider, client.active_model())

    success_count = 0
    fail_count = 0

    for file_path in iter_with_progress(files, desc="Preprocessing"):
        ok = process_one_file(
            transcript_path=file_path,
            output_dir=output_dir,
            client=client,
            force=args.force,
        )
        if ok:
            success_count += 1
        else:
            fail_count += 1

    logging.info("Done. Success=%s, Failed=%s, Total=%s", success_count, fail_count, len(files))


if __name__ == "__main__":
    main()
