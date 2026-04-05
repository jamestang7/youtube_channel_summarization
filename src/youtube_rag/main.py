import argparse
import json
import logging
import time

from youtube_rag.core.database import get_videos_at_stage
from youtube_rag.pipeline.ingest import sync_channel, download_audio
from youtube_rag.pipeline.transcribe import transcribe_videos
from youtube_rag.pipeline.preprocess import run_pending as clean_pending
from youtube_rag.pipeline.summarize import run_pending as summarize_pending
from youtube_rag.rag.indexer import run_pending as index_pending
from youtube_rag.rag.search_engine import ask_question

PIPELINE = [
    ("downloaded", transcribe_videos),
    ("transcribed", clean_pending),
    ("cleaned", summarize_pending),
    ("summarized", index_pending),
]


def run_pipeline(video_id: str | None = None) -> None:
    for stage, fn in PIPELINE:
        if get_videos_at_stage(stage, video_id=video_id):
            fn(video_id=video_id) if video_id else fn()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YouTube RAG knowledge base")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("update", help="Sync channel and process all pending stages")
    p.add_argument("--channel-url", help="Youtube channel url",required=True)
    p.add_argument("--watch", action="store_true", help="Re-run every --interval seconds")
    p.add_argument("--interval", type=int, default=3600)

    p = sub.add_parser("add", help="Add a single video")
    p.add_argument("--video-url", required=True)

    p = sub.add_parser("ask", help="Query the knowledge base")
    p.add_argument("--query", required=True)
    p.add_argument("--top-k", type=int, default=5)

    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    args = build_parser().parse_args()

    if args.command == "update":
        if args.watch:
            while True:
                sync_channel(args.channel_url)
                run_pipeline()
                logging.info("Sleeping %ds until next sync…", args.interval)
                time.sleep(args.interval)
        else:
            sync_channel(args.channel_url)
            run_pipeline()

    elif args.command == "add":
        _, video_id = download_audio(args.video_url)
        if video_id:
            run_pipeline(video_id=video_id)

    elif args.command == "ask":
        print(json.dumps(ask_question(args.query, top_k=args.top_k), ensure_ascii=False, indent=2))

    else:
        build_parser().print_help()


if __name__ == "__main__":
    main()
