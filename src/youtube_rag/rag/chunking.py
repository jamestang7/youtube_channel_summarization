from __future__ import annotations

from typing import Any


def build_chunks_from_segments(
    segments: list[dict[str, Any]],
    max_chars_per_chunk: int = 800,
    overlap_segments: int = 1,
) -> list[dict[str, Any]]:
    if not segments:
        return []

    chunks: list[dict[str, Any]] = []
    start_idx = 0
    n = len(segments)

    while start_idx < n:
        current_chars = 0
        end_idx = start_idx

        while end_idx < n:
            seg_text = str(segments[end_idx].get("text", ""))
            seg_len = len(seg_text)

            if end_idx > start_idx and current_chars + seg_len > max_chars_per_chunk:
                break

            current_chars += seg_len
            end_idx += 1

            if current_chars >= max_chars_per_chunk:
                break

        if end_idx == start_idx:
            end_idx = start_idx + 1

        seg_slice = segments[start_idx:end_idx]
        chunk_text = "".join(str(seg.get("text", "")) for seg in seg_slice)
        start_sec = float(seg_slice[0].get("start", 0.0))
        end_sec = float(seg_slice[-1].get("end", start_sec))

        chunks.append(
            {
                "chunk_text": chunk_text,
                "start_sec": start_sec,
                "end_sec": end_sec,
            }
        )

        if end_idx >= n:
            break

        next_start = end_idx - overlap_segments
        if next_start <= start_idx:
            next_start = start_idx + 1
        start_idx = max(0, next_start)

    return chunks
