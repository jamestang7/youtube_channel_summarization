from youtube_rag.chunking import build_chunks_from_segments
from youtube_rag.models import AnswerResult, RetrievedSource, build_context_block


def test_build_chunks_from_segments_keeps_order_and_timing() -> None:
    segments = [
        {"start": 0.0, "end": 2.0, "text": "第一段"},
        {"start": 2.0, "end": 4.0, "text": "第二段"},
        {"start": 4.0, "end": 6.0, "text": "第三段"},
    ]

    chunks = build_chunks_from_segments(segments, max_chars_per_chunk=4, overlap_segments=1)

    assert len(chunks) >= 2
    assert chunks[0]["start_sec"] == 0.0
    assert chunks[0]["end_sec"] >= 2.0
    assert all("chunk_text" in chunk for chunk in chunks)


def test_context_block_formatting() -> None:
    sources = [
        RetrievedSource(
            video_id="abc123",
            title="测试标题",
            start_sec=12.0,
            end_sec=24.0,
            chunk_text="这是片段内容",
            youtube_url="https://youtube.com/watch?v=abc123",
            timestamp_url="https://youtube.com/watch?v=abc123&t=12s",
        )
    ]

    context = build_context_block(sources)

    assert "[Source 1]" in context
    assert "title=测试标题" in context
    assert "video_id=abc123" in context
    assert "text=这是片段内容" in context


def test_answer_result_schema_contract() -> None:
    source = RetrievedSource(
        video_id="xyz999",
        title="标题",
        start_sec=30.0,
        end_sec=40.0,
        chunk_text="内容",
        youtube_url="https://youtube.com/watch?v=xyz999",
        timestamp_url="https://youtube.com/watch?v=xyz999&t=30s",
    )

    result = AnswerResult(answer_text="回答", sources=[source]).to_dict()

    assert set(result.keys()) == {"answer_text", "sources"}
    assert result["answer_text"] == "回答"
    assert isinstance(result["sources"], list)
    assert result["sources"][0]["video_id"] == "xyz999"
    assert result["sources"][0]["timestamp_url"].endswith("&t=30s")
