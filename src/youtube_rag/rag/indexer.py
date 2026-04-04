from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from ..core import config
from .chunking import build_chunks_from_segments

DEFAULT_COLLECTION_NAME = "youtube_transcript_chunks"


def load_docs(source: str, video_id: str | None = None) -> tuple[list[dict[str, Any]], int, int]:
    if source == "transcripts":
        base_dir = Path(config.TRANSCRIPTS_DIR)
        pattern = "*.json"
    else:
        base_dir = Path(config.PROCESSED_DIR)
        pattern = "*.cleaned.json"

    if video_id:
        candidate = base_dir / (f"{video_id}.json" if source == "transcripts" else f"{video_id}.cleaned.json")
        file_paths = [candidate] if candidate.exists() else []
    else:
        file_paths = sorted(base_dir.glob(pattern))

    docs: list[dict[str, Any]] = []
    skipped = 0
    failed = 0

    for path in file_paths:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            segments = data.get("segments")
            if not isinstance(segments, list) or not segments:
                logging.warning("[SKIP] %s has no valid segments", path.name)
                skipped += 1
                continue

            docs.append(
                {
                    "video_id": data.get("video_id") or path.stem.replace(".cleaned", ""),
                    "title": data.get("title") or "",
                    "youtube_url": data.get("youtube_url") or "",
                    "segments": segments,
                    "source_file": str(path),
                }
            )
        except json.JSONDecodeError:
            logging.exception("[FAIL] Invalid JSON: %s", path.name)
            failed += 1
        except Exception:
            logging.exception("[FAIL] Could not load %s", path.name)
            failed += 1

    return docs, skipped, failed


def get_or_create_collection(rebuild: bool = False, collection_name: str = DEFAULT_COLLECTION_NAME) -> Any:
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


def upsert_chunks(collection: Any, doc: dict[str, Any], chunks: list[dict[str, Any]]) -> int:
    if not chunks:
        return 0

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for chunk_index, chunk in enumerate(chunks):
        start_sec = round(float(chunk["start_sec"]), 3)
        end_sec = round(float(chunk["end_sec"]), 3)
        chunk_id = f"{doc['video_id']}:{chunk_index}:{start_sec}:{end_sec}"

        ids.append(chunk_id)
        documents.append(chunk["chunk_text"])
        metadatas.append(
            {
                "video_id": str(doc["video_id"]),
                "title": str(doc.get("title", "")),
                "youtube_url": str(doc.get("youtube_url", "")),
                "start_sec": start_sec,
                "end_sec": end_sec,
                "source_file": str(doc["source_file"]),
                "chunk_index": chunk_index,
            }
        )

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return len(ids)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Chroma index from transcript JSON files")
    parser.add_argument("--source", choices=["transcripts", "processed"], default="transcripts")
    parser.add_argument("--video-id", type=str, default=None)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--max-chars-per-chunk", type=int, default=800)
    parser.add_argument("--overlap-segments", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    docs, skipped_files, failed_files = load_docs(source=args.source, video_id=args.video_id)
    if not docs:
        logging.info("No files to index from source=%s", args.source)
        return

    collection = get_or_create_collection(rebuild=args.rebuild)

    processed_files = 0
    total_chunks = 0

    for doc in docs:
        try:
            chunks = build_chunks_from_segments(
                segments=doc["segments"],
                max_chars_per_chunk=args.max_chars_per_chunk,
                overlap_segments=args.overlap_segments,
            )
            chunk_count = upsert_chunks(collection=collection, doc=doc, chunks=chunks)
            total_chunks += chunk_count
            processed_files += 1
            logging.info("[OK] %s indexed with %s chunks", doc["video_id"], chunk_count)
        except Exception:
            failed_files += 1
            logging.exception("[FAIL] Could not index %s", doc.get("video_id", "unknown"))

    logging.info(
        "Indexing done | files_processed=%s | total_chunks=%s | skipped_files=%s | failed_files=%s",
        processed_files,
        total_chunks,
        skipped_files,
        failed_files,
    )


if __name__ == "__main__":
    main()
