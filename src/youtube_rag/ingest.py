"""Download YouTube audio into ``AUDIO_DIR`` using ``yt_dlp.YoutubeDL``.

Supports single-video downloads and channel sync with SQLite deduplication via
``project.db`` (see :func:`init_db`).
"""

from __future__ import annotations

import random
import sqlite3
import time
from pathlib import Path
from typing import Any

import yt_dlp

from . import config


def init_db() -> sqlite3.Connection:
    """Create the central catalog if it doesn't exist."""
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            channel_name TEXT,
            video_id TEXT PRIMARY KEY,
            title TEXT,
            mp3_path TEXT,
            srt_path TEXT,
            download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            download_status TEXT DEFAULT 'pending',
            transcribe_status TEXT DEFAULT 'pending'
        )
        """
    )
    conn.commit()
    return conn

def add_video_to_registry(video_data: dict[str, Any], error_message: str | None = None) -> None:
    """Upserts a video record into the database."""
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    
    vid = str(video_data["id"])
    title = str(video_data.get("title", "Unknown title"))
    ch = video_data.get("channel_name")
    mp3 = str(video_data["local_path"]) if not error_message else None
    status = 'error' if error_message else 'downloaded'
    err_log = error_message.strip() if error_message else None
    
    # We use SQLite's UPSERT (ON CONFLICT) to update fields without destroying existing srt_paths
    c.execute(
        """
        INSERT INTO videos (channel_name, video_id, title, mp3_path, download_status)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(video_id) DO UPDATE SET
            title = excluded.title,
            mp3_path = excluded.mp3_path,
            download_status = excluded.download_status
        """,
        (ch, vid, title, mp3, status)
    )
    conn.commit()
    conn.close()
    
    if error_message:
        print(f"⚠️ Recorded failure for [{vid}]: {err_log[:80]}...")
    else:
        print(f"✅ Registered: {title}")


def _video_id_in_db(conn: sqlite3.Connection, video_id: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM videos WHERE video_id = ? LIMIT 1", (video_id,))
    return cur.fetchone() is not None


def _collect_video_ids(info: dict[str, Any]) -> list[str]:
    """
    Collects YouTube video IDs from a yt-dlp info dict.
    Handles Channels (multi-tab), Playlists, and Single Videos.
    """
    video_ids = []

    # Case 1: The info is a single video (no 'entries' list)
    if "entries" not in info:
        vid_id = info.get("id")
        return [vid_id] if vid_id else []

    # Case 2: The info is a Channel or Playlist (contains 'entries')
    entries = info.get("entries", [])

    for entry in entries:
        if not entry:
            continue

        # If the entry has its own 'entries', it's a 'Tab' (Videos/Streams/Shorts)
        # or a nested playlist. We extract IDs from within it.
        if "entries" in entry:
            tab_title = entry.get("title", "Unknown Tab")
            sub_entries = entry.get("entries", [])
            
            print(f"📂 Processing {tab_title}: found {len(sub_entries)} items")
            
            for sub_item in sub_entries:
                if sub_item and "id" in sub_item:
                    video_ids.append(sub_item["id"])
        
        # If the entry is just a video directly (common in standard playlists)
        elif "id" in entry:
            video_ids.append(entry["id"])

    # Remove duplicates while preserving order (using dict keys)
    unique_ids = list(dict.fromkeys(video_ids))
    print(f"✅ Total unique videos collected: {len(unique_ids)}")
    
    return unique_ids


def _channel_list_ydl_opts() -> dict[str, Any]:
    """Options for listing a channel/playlist without downloading media."""
    
    return {
        # "skip_download": True,
        "ignoreerrors": True,
        "remote_components": "ejs:github",
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": False,
        "cookiefile": str(config.COOKIE_FILE.resolve()),
        "ffmpeg_location": str(config.FFMPEG_BIN.resolve()),
        "extractor_args": {"youtube": {"player_client": ["mweb"]}},
        # 'remote_components': 'ejs:github',
        "js_runtimes": {"node": {}},
        'sleep_interval': 1,
        'max_sleep_interval': 3,
        'retries': 3
    }



def sync_channel(channel_url: str) -> None:
    """List all videos on a channel (or playlist), download missing ones, and throttle requests.

    Steps:

    1. Call ``ydl.extract_info(channel_url, download=False)`` to enumerate ids (no files yet).
    2. For each id, if it exists in ``videos`` in ``project.db``, print ``Skipping [id]``.
    3. Otherwise call :func:`download_audio` with ``https://www.youtube.com/watch?v=<id>``.
    4. Between consecutive **downloads** (when another download remains later in the list),
       sleep for ``random.uniform(2, 5)`` seconds.

    Args:
        channel_url: A channel, uploads, or playlist URL understood by yt-dlp.

    Raises:
        FileNotFoundError / RuntimeError: Propagated from config checks or listing failures.
    """
    config.check_config()
    init_db()
    conn = sqlite3.connect(config.DB_FILE)

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

    n = len(video_ids)
    try:
        for i, vid in enumerate(video_ids):
            if _video_id_in_db(conn, vid):
                print(f"Skipping [{vid}]")
                continue

            watch_url = f"https://www.youtube.com/watch?v={vid}"
            download_audio(watch_url)
                
            rest = video_ids[i + 1 :]
            if any(not _video_id_in_db(conn, x) for x in rest):
                time.sleep(random.uniform(2, 5))
    finally:
        conn.close()


def download_audio(youtube_url: str) -> tuple[Path, str]:
    """Download the best available audio and extract it as MP3 under ``AUDIO_DIR``.

    Uses :class:`yt_dlp.YoutubeDL` (Python API, not subprocess). Options include:

    * ``outtmpl`` rooted at :data:`~youtube_rag.config.AUDIO_DIR`.
    * ``cookiefile`` / ``ffmpeg_location`` from :mod:`youtube_rag.config`.
    * ``format`` = ``bestaudio/best``, postprocessor FFmpeg extract to MP3.

    On success, registers the file in ``project.db`` via :func:`add_video_to_registry`.

    Args:
        youtube_url: A single-video URL supported by yt-dlp.

    Returns:
        ``(mp3_path, video_id)`` — absolute path to the ``.mp3`` and the YouTube id string.

    Raises:
        FileNotFoundError: If the cookie file or FFmpeg directory is missing.
        RuntimeError: If yt-dlp completes without a usable MP3 path.
    """
    config.check_config()
    init_db()

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
        "ignoreerrors": False
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(youtube_url, download=True)
            vid = info.get("id")
        except Exception as exc:
            vid = youtube_url.split("v=")[-1][:11]
            err_text = str(exc)
            print(f"Failed to download {vid}: {err_text}")
            # Log the failure in the DB so we don't try again
            add_video_to_registry({
                "id": vid, "title": "Failed Download", "channel_name": "Unknown"
            }, error_message=err_text)
            
            return None, vid

        if info is None:
            raise RuntimeError("yt-dlp returned no metadata.")

        # Playlist/shelf URL passed in: take first entry only (single-video URLs have no entries)
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
    }
    add_video_to_registry(metadata)

    return mp3_path.resolve(), str(vid)


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