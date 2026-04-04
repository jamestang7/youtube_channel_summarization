import json
import os
import time
from pathlib import Path
from typing import Iterator, TypeVar

from ..core import config
from ..core.database import get_connection

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover - optional dependency
    tqdm = None

T = TypeVar("T")


def iter_with_progress(items: list[T], desc: str) -> Iterator[T]:
    if tqdm is not None:
        yield from tqdm(items, desc=desc, unit="video")
        return
    total = len(items)
    for idx, item in enumerate(items, start=1):
        print(f"{desc} [{idx}/{total}]")
        yield item


def transcribe_videos():
    import torch
    from faster_whisper import WhisperModel

    if "HF_TOKEN" not in os.environ:
        raise RuntimeError("HF_TOKEN not found in environment or .env file. Transcription cannot proceed.")
    else:
        print("🚀 Using HF_TOKEN found in system environment variables.")

    # Ensure transcript directory exists
    Path(config.TRANSCRIPT_DIR).mkdir(parents=True, exist_ok=True)

    # 1. Open DB to fetch pending tasks
    with get_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            SELECT video_id, mp3_path, title
            FROM videos
            WHERE download_status = ?
            AND transcribe_status = ?
        """,
            (config.DOWNLOAD_STATUS_DOWNLOADED, config.TRANSCRIBE_STATUS_PENDING),
        )
        items = cur.fetchall()

    if not items:
        print("🏁 No videos pending transcription.")
        return

    # 2. Initialize Model
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"🚀 Initializing WhisperModel on {device}...")
    model = WhisperModel(
        config.WHISPER_MODEL,
        device=device,
        compute_type="float16",
    )

    for video_id, mp3_path, title in iter_with_progress(items, desc="Transcribing"):
        mp3_path = Path(mp3_path).resolve()

        # Handle missing files
        if not mp3_path.is_file():
            print(f"❌ MP3 file missing for {video_id}: {mp3_path}")
            with get_connection() as db:
                db.execute(
                    "UPDATE videos SET transcribe_status = ? WHERE video_id = ?",
                    (config.TRANSCRIBE_STATUS_ERROR_MISSING_MP3, video_id),
                )
            continue

        print(f"\n🎙️ Transcribing: {title} ({video_id})")
        start_time = time.time()

        try:
            segments, info = model.transcribe(
                str(mp3_path),
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_speech_duration_ms=500),
                condition_on_previous_text=False,
            )
            print(f"Detected language: {info.language} ({info.language_probability:.2%} certainty)")

            seg_list = []
            text_chunks = []
            for seg in segments:
                seg_list.append(
                    {
                        "start": round(seg.start, 2),
                        "end": round(seg.end, 2),
                        "text": seg.text.strip(),
                    }
                )
                text_chunks.append(seg.text.strip())

                if len(seg_list) % 100 == 0:
                    print(f"   ... transcribed up to minute {seg.end / 60:.1f}")

            transcript = {
                "video_id": video_id,
                "title": title,
                "language": info.language,
                "full_text": "".join(text_chunks),
                "segments": seg_list,
            }

            json_path = (Path(config.TRANSCRIPT_DIR) / f"{video_id}.json").resolve()

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(transcript, f, ensure_ascii=False, indent=2)

            with get_connection() as db:
                db.execute(
                    "UPDATE videos SET transcribe_status = ?, srt_path = ? WHERE video_id = ?",
                    (config.TRANSCRIBE_STATUS_TRANSCRIBED, str(json_path), video_id),
                )

            elapsed = time.time() - start_time
            print(f"✅ Finished in {elapsed:.1f}s -> Saved to {json_path.name}")

        except Exception as e:
            print(f"❌ Error transcribing {video_id}: {e}")
            with get_connection() as db:
                db.execute(
                    "UPDATE videos SET transcribe_status = ? WHERE video_id = ?",
                    (config.TRANSCRIBE_STATUS_ERROR, video_id),
                )


if __name__ == "__main__":
    transcribe_videos()
