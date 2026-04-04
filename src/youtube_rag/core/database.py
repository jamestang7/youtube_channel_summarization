from __future__ import annotations

import sqlite3

from . import config


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(config.DB_FILE)


def init_db(conn: sqlite3.Connection) -> None:
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


def video_exists(conn: sqlite3.Connection, video_id: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM videos WHERE video_id = ? LIMIT 1", (video_id,))
    return cur.fetchone() is not None
