from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from youtube_rag.youtube_ingest import (
    CookieError,
    MembersOnlyError,
    YtDlpFailedError,
    download_audio,
    fetch_metadata,
)


def test_download_audio_rejects_conflicting_cookie_sources(tmp_path: Path) -> None:
    fake_file = tmp_path / "cookies.txt"
    fake_file.write_text("# Netscape\n", encoding="utf-8")

    with pytest.raises(CookieError):
        download_audio(
            "https://example.com/watch?v=abc",
            out_dir=tmp_path / "out",
            cookies_from_browser="chrome",
            cookies_file=fake_file,
        )


def test_fetch_metadata_raises_members_only() -> None:
    stderr = "ERROR: Members-only content; join this channel to get access"
    mocked = MagicMock()
    mocked.returncode = 1
    mocked.stdout = ""
    mocked.stderr = stderr

    with patch("youtube_rag.youtube_ingest.subprocess.run", return_value=mocked):
        with pytest.raises(MembersOnlyError):
            fetch_metadata("https://example.com/watch?v=abc")


def test_download_audio_happy_path(tmp_path: Path) -> None:
    out = tmp_path / "out"
    video_id = "vid123"
    meta = (
        '{ "id": "'
        + video_id
        + '", "title": "Hello", "webpage_url": "https://youtu.be/'
        + video_id
        + '", "duration": 12.5 }\n'
    )
    audio_path = out / f"{video_id}.mp3"
    out.mkdir(parents=True, exist_ok=True)

    def fake_run(cmd: list[str], **kwargs):  # type: ignore[no-untyped-def]
        m = MagicMock()
        if "--skip-download" in cmd:
            m.returncode = 0
            m.stdout = meta
            m.stderr = ""
        else:
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            audio_path.write_bytes(b"fake")
        return m

    with patch("youtube_rag.youtube_ingest.subprocess.run", side_effect=fake_run):
        result = download_audio("https://example.com/watch?v=" + video_id, out_dir=out)

    assert result.audio_path.resolve() == audio_path.resolve()
    assert result.title == "Hello"
    assert result.duration == 12.5


def test_parse_invalid_json() -> None:
    from youtube_rag.youtube_ingest import _parse_json_object, _YtDlpRun

    run = _YtDlpRun(args=[], returncode=0, stdout="not-json", stderr="")
    with pytest.raises(YtDlpFailedError):
        _parse_json_object(run)
