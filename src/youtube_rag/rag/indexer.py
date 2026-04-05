from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from ..core import config
from ..core.database import advance_stage, get_connection, mark_error
from .chunking import build_chunks_from_segments

DEFAULT_COLLECTION_NAME = "youtube_transcript_chunks"


def get_chroma_collection(*, rebuild: bool = False, collection_name: str = DEFAULT_COLLECTION_NAME) -> Any:
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    import chromadb

    chroma_path = Path(config.CHROMA_DB_DIR)
    chroma_path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(chroma_path))

    if rebuild:
        try:
            client.delete_collection(name=collection_name)
            logging.info("Rebuilt collection: %s", collection_name)
        except Exception:
            pass

    embedding_fn = SentenceTransformerEmbeddingFunction(model_name=config.LOCAL_EMBEDDING_MODEL)
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )


def load_doc(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        logging.exception("[FAIL] Invalid JSON: %s", path.name)
        return None
    except Exception:
        logging.exception("[FAIL] Could not load %s", path.name)
        return None

    segments = data.get("segments")
    if not isinstance(segments, list) or not segments:
        logging.warning("[SKIP] %s has no valid segments", path.name)
        return None

    return {
        "video_id": data.get("video_id") or path.stem.replace(".cleaned", ""),
        "title": data.get("title") or "",
        "youtube_url": data.get("youtube_url") or "",
        "segments": segments,
        "source_file": str(path),
    }


def collect_pending_docs(video_id: str | None = None, limit: int | None = None) -> tuple[list[dict[str, Any]], int, int]:
    query = [
        "SELECT video_id, cleaned_path FROM videos",
        "WHERE pipeline_stage = ?",
    ]
    params: list[object] = ["summarized"]

    if video_id:
        query.append("AND video_id = ?")
        params.append(video_id)

    query.append("ORDER BY download_date")
    if limit is not None:
        query.append("LIMIT ?")
        params.append(limit)

    with get_connection() as db:
        rows = db.execute(" ".join(query), params).fetchall()

    docs: list[dict[str, Any]] = []
    skipped = 0
    failed = 0
    for row_video_id, cleaned_path in rows:
        if not cleaned_path:
            skipped += 1
            continue

        doc = load_doc(Path(cleaned_path))
        if doc is None:
            failed += 1
            continue

        if str(doc["video_id"]) != str(row_video_id):
            doc["video_id"] = str(row_video_id)
        docs.append(doc)

    return docs, skipped, failed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Chroma index from cleaned transcript JSON files")
    parser.add_argument("--video-id", type=str, default=None)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--max-chars-per-chunk", type=int, default=800)
    parser.add_argument("--overlap-segments", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def run_pending(
    video_id: str | None = None,
    rebuild: bool = False,
    max_chars_per_chunk: int = 800,
    overlap_segments: int = 1,
    limit: int | None = None,
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    docs, skipped_files, failed_files = collect_pending_docs(video_id=video_id, limit=limit)
    if not docs:
        logging.info("No summarized videos pending indexing.")
        return

    collection = get_chroma_collection(rebuild=rebuild)

    all_ids: list[str] = []
    all_docs: list[str] = []
    all_metas: list[dict[str, Any]] = []
    processed_video_ids: list[str] = []
    failed_video_ids: list[str] = []

    for doc in docs:
        try:
            chunks = build_chunks_from_segments(
                segments=doc["segments"],
                max_chars_per_chunk=max_chars_per_chunk,
                overlap_segments=overlap_segments,
            )
            for i, chunk in enumerate(chunks):
                start_sec = round(float(chunk["start_sec"]), 3)
                end_sec = round(float(chunk["end_sec"]), 3)
                all_ids.append(f"{doc['video_id']}:{i}:{start_sec}:{end_sec}")
                all_docs.append(chunk["chunk_text"])
                all_metas.append(
                    {
                        "video_id": str(doc["video_id"]),
                        "title": str(doc.get("title", "")),
                        "youtube_url": str(doc.get("youtube_url", "")),
                        "start_sec": start_sec,
                        "end_sec": end_sec,
                        "source_file": str(doc["source_file"]),
                        "chunk_index": i,
                    }
                )
            processed_video_ids.append(doc["video_id"])
        except Exception:
            failed_video_ids.append(doc["video_id"])
            logging.exception("[FAIL] building chunks for %s", doc.get("video_id"))

    if all_ids:
        collection.upsert(ids=all_ids, documents=all_docs, metadatas=all_metas)
        logging.info("Upserted %d chunks across %d videos", len(all_ids), len(processed_video_ids))

    with get_connection() as conn:
        for vid in processed_video_ids:
            advance_stage(conn, vid, "indexed")
        for vid in failed_video_ids:
            mark_error(conn, vid)

    logging.info(
        "Indexing done | files_processed=%s | total_chunks=%s | skipped_files=%s | failed_files=%s",
        len(processed_video_ids),
        len(all_ids),
        skipped_files,
        failed_files + len(failed_video_ids),
    )


def main() -> None:
    args = parse_args()
    run_pending(
        video_id=args.video_id,
        rebuild=args.rebuild,
        max_chars_per_chunk=args.max_chars_per_chunk,
        overlap_segments=args.overlap_segments,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
