from __future__ import annotations

from pathlib import Path

import pytest

from youtube_rag.transcriber import transcribe_audio


def test_transcriber_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.wav"
    with pytest.raises(FileNotFoundError):
        transcribe_audio(missing, "en")


@pytest.mark.skip(reason="Loads faster-whisper + model; enable for local GPU/CPU integration runs.")
def test_transcriber_integration_tiny_audio() -> None:
    """Placeholder hook for optional on-machine integration tests."""
    pass
