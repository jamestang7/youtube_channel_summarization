from __future__ import annotations

import argparse
import difflib
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib import error, request

from dotenv import load_dotenv

from . import config

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

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"


class OpenAIClient:
    def __init__(self, model: str) -> None:
        self.model = model

    def clean_text(self, original_full_text: str, video_title: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required. Please set it in .env")

        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        url = f"{base_url.rstrip('/')}/chat/completions"

        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": CLEAN_TEXT_SYSTEM_PROMPT},
                {
                "role": "user", 
                "content": f"VIDEO TITLE: {video_title}\n\nTRANSCRIPT TO CLEAN:\n{original_full_text}"
            },
            ],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        data = _post_json(url=url, payload=payload, headers=headers)
        return data["choices"][0]["message"]["content"].strip()


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


def load_transcript(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments") or []

    original_full_text = data.get("full_text")

    return {
        "video_id": data.get("video_id") or path.stem,
        "title": data.get("title") or path.stem,
        "youtube_url": data.get("youtube_url"),
        "segments": segments,
        "original_full_text": original_full_text,
    }


def align_segments(original_segments: list[dict[str, Any]], cleaned_full_text: str) -> list[dict[str, Any]]:
    original_full_text = "".join(str(seg.get("text", "")) for seg in original_segments)

    boundaries = [0]
    for seg in original_segments:
        boundaries.append(boundaries[-1] + len(str(seg.get("text", ""))))

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


def process_one_file(transcript_path: Path, output_dir: Path, client: OpenAIClient, force: bool) -> bool:
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

        length_ratio = len(cleaned_full_text) / max(len(original_full_text), 1)
        if abs(length_ratio - 1.0) > 0.10:
            logging.warning(
                "[WARN] %s cleaned length changed too much (orig=%s, cleaned=%s). Using original text for safety.",
                video_id,
                len(original_full_text),
                len(cleaned_full_text),
            )
            cleaned_full_text = original_full_text
            cleaned_segments = [dict(seg) for seg in original_segments]
        else:
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
    except Exception as exc:
        logging.exception("[FAIL] %s (%s)", video_id, exc)
        return False


def collect_input_files(transcripts_dir: Path, video_id: str | None) -> list[Path]:
    if video_id:
        direct_match = transcripts_dir / f"{video_id}.json"
        if direct_match.exists():
            return [direct_match]

        matches = [p for p in transcripts_dir.glob("*.json") if p.stem == video_id]
        return sorted(matches)

    return sorted(transcripts_dir.glob("*.json"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean transcript JSON files with OpenAI + difflib alignment")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N transcript files")
    parser.add_argument("--video-id", type=str, default=None, help="Process only one video_id")
    parser.add_argument("--force", action="store_true", help="Reprocess even if outputs already exist")
    return parser.parse_args()


def main() -> None:
    load_dotenv(config.ENV_FILE)

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

    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    client = OpenAIClient(model=model)

    success_count = 0
    fail_count = 0

    for file_path in files:
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
