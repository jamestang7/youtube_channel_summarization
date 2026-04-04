# main.py — runs the full pipeline end to end
import argparse

from youtube_rag.pipeline.ingest import sync_channel, download_audio
from youtube_rag.pipeline.transcribe import transcribe_videos
from youtube_rag.pipeline.preprocess import main as preprocess_main
from youtube_rag.pipeline.summarize import main as summarize_main
from youtube_rag.rag.indexer import main as index_main
from youtube_rag.rag.search_engine import ask_question


def main():
    parser = argparse.ArgumentParser(description="YouTube RAG Pipeline")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("ingest")
    sub.add_parser("transcribe")
    sub.add_parser("preprocess")
    sub.add_parser("summarize")
    sub.add_parser("index")
    q = sub.add_parser("query")
    q.add_argument("--query", required=True)
    args = parser.parse_args()

    if args.command == "transcribe":
        transcribe_videos()
    elif args.command == "preprocess":
        preprocess_main()
    elif args.command == "summarize":
        summarize_main()
    elif args.command == "index":
        index_main()
    elif args.command == "query":
        import json
        print(json.dumps(ask_question(args.query), ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
