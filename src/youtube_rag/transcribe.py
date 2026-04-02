import os
import sqlite3
import json
from pathlib import Path
import time
from dotenv import load_dotenv

from . import config

def transcribe_videos():
    import torch
    from faster_whisper import WhisperModel

    if "HF_TOKEN" not in os.environ:
        load_dotenv(config.ENV_FILE)
        if "HF_TOKEN" not in os.environ:
            raise("⚠️ Warning: HF_TOKEN still not found. Downloads may be throttled.")
        else:
            print("✅ HF_TOKEN loaded successfully from .env")
    else:
        print("🚀 Using HF_TOKEN found in system environment variables.")


    db = sqlite3.connect(config.DB_FILE)
    cur = db.cursor()

    # Ensure transcript directory exists
    Path(config.TRANSCRIPT_DIR).mkdir(parents=True, exist_ok=True)

    # 1. Open DB to fetch pending tasks
    with sqlite3.connect(config.DB_FILE) as db:
        cur = db.cursor()
        
        Path(config.TRANSCRIPT_DIR).mkdir(parents=True, exist_ok=True)

        # FIX: Look for pending transcriptions, not just downloaded files
        cur.execute("""
            SELECT video_id, mp3_path, title 
            FROM videos 
            WHERE download_status = 'downloaded' 
            AND transcribe_status = 'pending'
        """)
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
        compute_type="float16"
    )

    for video_id, mp3_path, title in items:
        mp3_path = Path(mp3_path).resolve()

        # Handle missing files
        if not mp3_path.is_file():
            print(f"❌ MP3 file missing for {video_id}: {mp3_path}")
            with sqlite3.connect(config.DB_FILE) as db:
                db.execute("UPDATE videos SET transcribe_status = 'error_missing_mp3' WHERE video_id = ?", (video_id,))
            continue

        print(f"\n🎙️ Transcribing: {title} ({video_id})")
        start_time = time.time()

        try:
            segments, info = model.transcribe(
                str(mp3_path),
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_speech_duration_ms=500),
                condition_on_previous_text=False
            )
            print(f"Detected language: {info.language} ({info.language_probability:.2%} certainty)")

            seg_list = []
            text_chunks = [] # FIX: Use a list for memory-efficient string building
            for seg in segments:
                seg_list.append({
                    "start": round(seg.start, 2), # Keep JSON sizes smaller by rounding
                    "end": round(seg.end, 2),
                    "text": seg.text.strip()
                })
                text_chunks.append(seg.text.strip())

                # Progress indicator: print an update every ~100 segments
                if len(seg_list) % 100 == 0:
                    print(f"   ... transcribed up to minute {seg.end / 60:.1f}")

            # Join all chunks at the very end
            transcript = {
                "video_id": video_id,
                "title": title,
                "language": info.language,
                "full_text": "".join(text_chunks),
                "segments": seg_list
            }

            json_path = (Path(config.TRANSCRIPT_DIR) / f"{video_id}.json").resolve()

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(transcript, f, ensure_ascii=False, indent=2)

            # FIX: Update transcribe_status, leave download_status alone
            with sqlite3.connect(config.DB_FILE) as db:
                db.execute(
                    "UPDATE videos SET transcribe_status = 'transcribed', srt_path = ? WHERE video_id = ?",
                    (str(json_path), video_id)
                )

            elapsed = time.time() - start_time
            print(f"✅ Finished in {elapsed:.1f}s -> Saved to {json_path.name}")

        except Exception as e:
            print(f"❌ Error transcribing {video_id}: {e}")
            with sqlite3.connect(config.DB_FILE) as db:
                db.execute("UPDATE videos SET transcribe_status = 'error' WHERE video_id = ?", (video_id,))

if __name__ == "__main__":
    transcribe_videos()