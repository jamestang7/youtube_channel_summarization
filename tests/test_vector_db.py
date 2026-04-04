from __future__ import annotations

from youtube_rag.vector_db import segments_to_documents


def test_segments_to_documents_batches_short_segments() -> None:
    segments = [
        {"text_segment": "a" * 400, "start_time": 0.0, "end_time": 1.0},
        {"text_segment": "b" * 400, "start_time": 1.0, "end_time": 2.0},
    ]
    docs = segments_to_documents(
        segments,
        source_url="https://example.com/watch?v=x",
        title="t",
        chunk_size=1000,
        chunk_overlap=0,
    )
    assert len(docs) == 1
    assert docs[0].metadata["start_time"] == 0.0
    assert docs[0].metadata["end_time"] == 2.0
    assert "aaaa" in docs[0].page_content and "bbbb" in docs[0].page_content


def test_segments_to_documents_splits_long_segment_with_interpolation() -> None:
    segments = [{"text_segment": "word " * 200, "start_time": 0.0, "end_time": 10.0}]
    docs = segments_to_documents(
        segments,
        source_url="https://example.com/watch?v=x",
        title="t",
        chunk_size=80,
        chunk_overlap=0,
    )
    assert len(docs) >= 2
    starts = [d.metadata["start_time"] for d in docs]
    ends = [d.metadata["end_time"] for d in docs]
    assert min(starts) >= 0.0
    assert max(ends) <= 10.0
