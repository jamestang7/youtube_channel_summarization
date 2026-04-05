"""Download YouTube audio into ``AUDIO_DIR`` using ``yt_dlp.YoutubeDL``.

Supports single-video downloads and channel sync with SQLite deduplication via
``project.db``.
"""

from __future__ import annotations

import random
import sqlite3
import time
from pathlib import Path
from typing import Any

import yt_dlp

from ..core import config
from ..core.database import get_connection, init_db
from ..core.utils import iter_with_progress


def add_video_to_registry(
    conn: sqlite3.Connection,
    video_data: dict[str, Any],
    error_message: str | None = None,
) -> None:
    """Upserts a video record into the database."""
    c = conn.cursor()

    vid = str(video_data["id"])
    title = str(video_data.get("title", "Unknown title"))
    ch = video_data.get("channel_name")
    mp3 = str(video_data["local_path"]) if not error_message and video_data.get("local_path") else None
    err_log = error_message.strip() if error_message else None
    upload_date = str(video_data["upload_date"]) if video_data.get("upload_date") is not None else None
    duration_string = (
        str(video_data["duration_string"]) if video_data.get("duration_string") is not None else None
    )
    media_type = str(video_data["media_type"]) if video_data.get("media_type") is not None else None
    pipeline_stage = "error" if error_message else "downloaded"

    c.execute(
        """
        INSERT INTO videos (
            channel_name,
            video_id,
            title,
            mp3_path,
            upload_date,
            duration_string,
            media_type,
            pipeline_stage
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id) DO UPDATE SET
            channel_name = excluded.channel_name,
            title = excluded.title,
            mp3_path = excluded.mp3_path,
            upload_date = excluded.upload_date,
            duration_string = excluded.duration_string,
            media_type = excluded.media_type,
            pipeline_stage = excluded.pipeline_stage
        """,
        (
            ch,
            vid,
            title,
            mp3,
            upload_date,
            duration_string,
            media_type,
            pipeline_stage,
        ),
    )
    conn.commit()

    if error_message:
        print(f"⚠️ Recorded failure for [{vid}]: {err_log[:80]}...")
    else:
        print(f"✅ Registered: {title}")


def _collect_video_ids(info: dict[str, Any]) -> list[str]:
    """
    Collects YouTube video IDs from a yt-dlp info dict.
    Handles Channels (multi-tab), Playlists, and Single Videos.
    """
    video_ids = []

    if "entries" not in info:
        vid_id = info.get("id")
        return [vid_id] if vid_id else []

    entries = info.get("entries", [])

    for entry in entries:
        if not entry:
            continue

        if "entries" in entry:
            tab_title = entry.get("title", "Unknown Tab")
            sub_entries = entry.get("entries", [])

            print(f"📂 Processing {tab_title}: found {len(sub_entries)} items")

            for sub_item in sub_entries:
                # skip 'live_status': 'is_upcoming'
                if sub_item.get("live_status") == "is_upcoming":
                    continue
                if sub_item and "id" in sub_item:
                    video_ids.append(sub_item["id"])
        elif "id" in entry:
            video_ids.append(entry["id"])

    unique_ids = list(dict.fromkeys(video_ids))
    print(f"✅ Total unique videos collected: {len(unique_ids)}")

    return unique_ids


def _channel_list_ydl_opts() -> dict[str, Any]:
    """Options for listing a channel/playlist without downloading media."""

    return {
        "ignoreerrors": True,
        "remote_components": "ejs:github",
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": False,
        "cookiefile": str(config.COOKIE_FILE.resolve()),
        "ffmpeg_location": str(config.FFMPEG_BIN.resolve()),
        "extractor_args": {"youtube": {"player_client": ["mweb"]}},
        "js_runtimes": {"node": {}},
        "sleep_interval": 1,
        "max_sleep_interval": 3,
        "retries": 3,
    }


def sync_channel(channel_url: str) -> None:
    """List all videos on a channel (or playlist), download missing ones, and throttle requests."""
    config.check_config()

    conn = get_connection()
    init_db(conn)

    list_opts = _channel_list_ydl_opts()
    with yt_dlp.YoutubeDL(list_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)

    if not info:
        conn.close()
        raise RuntimeError("yt-dlp returned no metadata for the channel URL.")

    video_ids = _collect_video_ids(info)
    if not video_ids:
        conn.close()
        raise RuntimeError("No video ids found; try a /videos URL or check the channel response.")

    try:
        for i, vid in enumerate(iter_with_progress(video_ids, desc="Downloading", unit="video")):
            already_exists = conn.execute("SELECT 1 FROM videos WHERE video_id = ?", (vid,)).fetchone() is not None
            if already_exists:
                print(f"Skipping [{vid}]")
                continue

            watch_url = f"https://www.youtube.com/watch?v={vid}"
            download_audio(watch_url, conn=conn)

            rest = video_ids[i + 1 :]
            if any(conn.execute("SELECT 1 FROM videos WHERE video_id = ?", (x,)).fetchone() is None for x in rest):
                time.sleep(random.uniform(2, 5))
    finally:
        conn.close()


def download_audio(youtube_url: str, conn: sqlite3.Connection | None = None) -> tuple[Path | None, str]:
    """Download the best available audio and extract it as MP3 under ``AUDIO_DIR``."""
    config.check_config()

    own_conn = conn is None
    active_conn = conn or get_connection()
    init_db(active_conn)

    config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    outtmpl = str(config.AUDIO_DIR / "%(id)s.%(ext)s")

    ydl_opts: dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "remote_components": "ejs:github",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ],
        "extractor_args": {"youtube": {"player_client": ["mweb"]}},
        "js_runtimes": {"node": {}},
        "cookiefile": str(config.COOKIE_FILE.resolve()),
        "ffmpeg_location": str(config.FFMPEG_BIN.resolve()),
        "quiet": False,
        "no_warnings": False,
        "ignoreerrors": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(youtube_url, download=True)
            except Exception as exc:
                vid = youtube_url.split("v=")[-1][:11]
                err_text = str(exc)
                print(f"Failed to download {vid}: {err_text}")
                add_video_to_registry(
                    active_conn,
                    {
                        "id": vid,
                        "title": "Failed Download",
                        "channel_name": "Unknown",
                    },
                    error_message=err_text,
                )
                return None, vid

            if info is None:
                raise RuntimeError("yt-dlp returned no metadata.")

            if "entries" in info and info.get("entries"):
                first = info["entries"][0]
                if first is None:
                    raise RuntimeError("First playlist entry is empty.")
                info = first

        if info is None:
            raise RuntimeError("yt-dlp returned no metadata.")

        mp3_path = _resolve_final_mp3(ydl, info, config.AUDIO_DIR)

        if not mp3_path.is_file():
            raise RuntimeError(f"File not found after download: {mp3_path}")

        vid = info.get("id")
        channel_name = info.get("channel")
        if not vid:
            raise RuntimeError("yt-dlp info missing video id after download.")

        metadata = {
            "id": str(vid),
            "title": info.get("title", "Unknown Title"),
            "local_path": mp3_path.resolve(),
            "channel_name": channel_name,
            "upload_date": info.get("upload_date"),
            "duration_string": info.get("duration_string"),
            "media_type": info.get("media_type"),
        }
        add_video_to_registry(active_conn, metadata)

        return mp3_path.resolve(), str(vid)
    finally:
        if own_conn:
            active_conn.close()


def _resolve_final_mp3(ydl: yt_dlp.YoutubeDL, info: dict[str, Any], data_dir: Path) -> Path:
    """Pick the output ``.mp3`` path after FFmpeg postprocessing."""
    fp = info.get("filepath")
    if fp:
        candidate = Path(fp)
        if candidate.suffix.lower() == ".mp3" and candidate.is_file():
            return candidate

    for part in reversed(info.get("requested_downloads") or []):
        p = part.get("filepath")
        if p:
            path = Path(p)
            if path.suffix.lower() == ".mp3" and path.is_file():
                return path

    vid = str(info.get("id") or "")
    if vid:
        direct = data_dir / f"{vid}.mp3"
        if direct.is_file():
            return direct
        matches = sorted(data_dir.glob(f"{vid}*.mp3"), key=lambda x: x.stat().st_mtime, reverse=True)
        if matches:
            return matches[0]

    guess = Path(ydl.prepare_filename(info)).with_suffix(".mp3")
    if guess.is_file():
        return guess

    raise RuntimeError("Could not resolve final MP3 path; inspect yt-dlp output and AUDIO_DIR.")
