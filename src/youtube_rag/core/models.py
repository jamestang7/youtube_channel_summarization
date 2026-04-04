from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class RetrievedSource:
    video_id: str
    title: str
    start_sec: float
    end_sec: float
    chunk_text: str
    youtube_url: str
    timestamp_url: str
    score: float | None = None

    def to_dict(self) -> dict:
        payload = {
            "video_id": self.video_id,
            "title": self.title,
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
            "chunk_text": self.chunk_text,
            "youtube_url": self.youtube_url,
            "timestamp_url": self.timestamp_url,
        }
        return payload


@dataclass
class AnswerResult:
    answer_text: str
    sources: list[RetrievedSource]

    def to_dict(self) -> dict:
        return {
            "answer_text": self.answer_text,
            "sources": [source.to_dict() for source in self.sources],
        }


def build_context_block(sources: list[RetrievedSource]) -> str:
    blocks: list[str] = []
    for i, src in enumerate(sources, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[Source {i}]",
                    f"title={src.title}",
                    f"video_id={src.video_id}",
                    f"start_sec={src.start_sec}",
                    f"end_sec={src.end_sec}",
                    f"text={src.chunk_text}",
                ]
            )
        )
    return "\n\n".join(blocks)
