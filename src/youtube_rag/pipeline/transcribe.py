import json
import os
import time
from pathlib import Path

from ..core import config
from ..core.database import advance_stage, get_connection, mark_error
from ..core.utils import iter_with_progress


def transcribe_videos(video_id: str | None = None):
    import torch
    from faster_whisper import WhisperModel

    if "HF_TOKEN" not in os.environ:
        raise RuntimeError("HF_TOKEN not found in environment or .env file. Transcription cannot proceed.")
    else:
        print("🚀 Using HF_TOKEN found in system environment variables.")

    Path(config.TRANSCRIPTS_DIR).mkdir(parents=True, exist_ok=True)

    query = "SELECT video_id, mp3_path, title FROM videos WHERE pipeline_stage = ?"
    params: list[object] = ["downloaded"]
    if video_id:
        query += " AND video_id = ?"
        params.append(video_id)

    with get_connection() as db:
        items = db.execute(query, params).fetchall()

    if not items:
        print("🏁 No videos pending transcription.")
        return

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"🚀 Initializing WhisperModel on {device}...")
    model = WhisperModel(
        config.WHISPER_MODEL,
        device=device,
        compute_type="float16",
    )

    for current_video_id, mp3_path, title in iter_with_progress(items, desc="Transcribing", unit="video"):
        mp3_path = Path(mp3_path).resolve()

        if not mp3_path.is_file():
            print(f"❌ MP3 file missing for {current_video_id}: {mp3_path}")
            with get_connection() as db:
                mark_error(db, current_video_id)
            continue

        print(f"\n🎙️ Transcribing: {title} ({current_video_id})")
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
                "video_id": current_video_id,
                "title": title,
                "language": info.language,
                "full_text": "".join(text_chunks),
                "segments": seg_list,
            }

            json_path = (Path(config.TRANSCRIPTS_DIR) / f"{current_video_id}.json").resolve()

            with json_path.open("w", encoding="utf-8") as f:
                json.dump(transcript, f, ensure_ascii=False, indent=2)

            with get_connection() as db:
                db.execute(
                    "UPDATE videos SET srt_path = ? WHERE video_id = ?",
                    (str(json_path), current_video_id),
                )
                advance_stage(db, current_video_id, "transcribed")

            elapsed = time.time() - start_time
            print(f"✅ Finished in {elapsed:.1f}s -> Saved to {json_path.name}")

        except Exception as e:
            print(f"❌ Error transcribing {current_video_id}: {e}")
            with get_connection() as db:
                mark_error(db, current_video_id)


if __name__ == "__main__":
    transcribe_videos()
