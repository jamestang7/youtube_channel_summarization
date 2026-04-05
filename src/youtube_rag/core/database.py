from __future__ import annotations

import sqlite3

PIPELINE_STAGES = ["downloaded", "transcribed", "cleaned", "summarized", "indexed", "error"]


def get_connection() -> sqlite3.Connection:
    from . import config

    return sqlite3.connect(config.DB_FILE)


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            channel_name      TEXT,
            video_id          TEXT PRIMARY KEY,
            title             TEXT,
            mp3_path          TEXT,
            srt_path          TEXT,
            cleaned_path      TEXT,
            outline_path      TEXT,
            upload_date       TEXT,
            duration_string   TEXT,
            media_type        TEXT,
            download_date     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            pipeline_stage    TEXT DEFAULT 'downloaded'  -- Default to downloaded because in main.py it triggers download/ sync channel by default
        )
        """
    )
    conn.commit()


def get_videos_at_stage(
    stage: str,
    video_id: str | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    conn = get_connection()
    q = "SELECT * FROM videos WHERE pipeline_stage = ?"
    params: list[object] = [stage]
    if video_id:
        q += " AND video_id = ?"
        params.append(video_id)
    if limit:
        q += " LIMIT ?"
        params.append(limit)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return rows


def advance_stage(conn: sqlite3.Connection, video_id: str, to_stage: str) -> None:
    conn.execute(
        "UPDATE videos SET pipeline_stage = ? WHERE video_id = ?",
        (to_stage, video_id),
    )
    conn.commit()


def mark_error(conn: sqlite3.Connection, video_id: str) -> None:
    conn.execute(
        "UPDATE videos SET pipeline_stage = ? WHERE video_id = ?",
        ("error", video_id),
    )
    conn.commit()
