"""Generate segment-level summaries for each processed transcript using Ollama."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Iterator, TypeVar

from youtube_rag.core import config
from youtube_rag.rag.llm_client import LLMChatClient

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover - optional dependency
    tqdm = None

T = TypeVar("T")

SUMMARY_SYSTEM_PROMPT = (
    "你是一位专业的视频内容编辑。我会给你提供一段视频的字幕片段（含时间戳），"
    "请为这段内容生成：\n"
    "1. 一个15字以内的段落标题\n"
    "2. 一段80字以内的段落摘要\n"
    "只输出JSON，格式：{\"title\": \"...\", \"summary\": \"...\"}\n"
    "不要输出任何其他内容。"
)

OVERALL_SYSTEM_PROMPT = (
    "你是一位专业的视频内容编辑。我会给你提供一个视频的所有段落标题和摘要，"
    "请生成一段150字以内的整体内容摘要。只输出摘要文本，不要JSON，不要标题。"
)


def group_segments(segments: list[dict], target_groups: int = 8) -> list[list[dict]]:
    if not segments:
        return []
    size = max(1, len(segments) // target_groups)
    return [segments[i : i + size] for i in range(0, len(segments), size)]


def summarize_group(client: LLMChatClient, group: list[dict], video_title: str) -> dict:
    text = "".join(s.get("text", "") for s in group)
    start = group[0].get("start", 0)
    end = group[-1].get("end", start)
    user_prompt = (
        f"视频标题：{video_title}\n"
        f"时间段：{int(start // 60)}:{int(start % 60):02d} - {int(end // 60)}:{int(end % 60):02d}\n"
        f"内容：{text[:1200]}"
    )
    raw = client.generate(system_prompt=SUMMARY_SYSTEM_PROMPT, user_prompt=user_prompt, temperature=0)
    try:
        clean = raw.strip().removeprefix("```json").removesuffix("```").strip()
        parsed = json.loads(clean)
        return {
            "start_sec": start,
            "end_sec": end,
            "title": parsed["title"],
            "summary": parsed["summary"],
        }
    except Exception:
        return {
            "start_sec": start,
            "end_sec": end,
            "title": text[:20] + "…",
            "summary": text[:80] + "…",
        }


def process_one(path: Path, output_dir: Path, client: LLMChatClient, force: bool) -> bool:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    video_id = data.get("video_id", path.stem.replace(".cleaned", ""))
    out_path = output_dir / f"{video_id}.outline.json"
    if not force and out_path.exists():
        logging.info("[SKIP] %s", video_id)
        return True

    segments = data.get("segments", [])
    title = data.get("title", "")
    if not segments:
        logging.warning("[SKIP] no segments: %s", video_id)
        return False

    groups = group_segments(segments, target_groups=min(10, max(4, len(segments) // 15)))
    section_summaries = []
    for i, group in enumerate(groups):
        result = summarize_group(client, group, title)
        section_summaries.append(result)
        logging.info("[%s] segment %d/%d done", video_id, i + 1, len(groups))
        time.sleep(0.5)

    all_titles = "\n".join(f"- {s['title']}：{s['summary']}" for s in section_summaries)
    overall = client.generate(
        system_prompt=OVERALL_SYSTEM_PROMPT,
        user_prompt=f"视频标题：{title}\n\n{all_titles}",
        temperature=0,
    )
    outline = {
        "video_id": video_id,
        "title": title,
        "youtube_url": data.get("youtube_url", ""),
        "overall_summary": overall.strip(),
        "segments": section_summaries,
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(outline, f, ensure_ascii=False, indent=2)
    logging.info("[OK] %s -> %d segments", video_id, len(section_summaries))
    return True


def iter_with_progress(items: list[T], desc: str) -> Iterator[T]:
    if tqdm is not None:
        yield from tqdm(items, desc=desc, unit="file")
        return
    total = len(items)
    for idx, item in enumerate(items, start=1):
        logging.info("%s [%d/%d]", desc, idx, total)
        yield item


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    repo_processed_dir = Path.cwd() / "data" / "processed"
    processed_dir = repo_processed_dir if repo_processed_dir.exists() else Path(config.PROCESSED_DIR)
    output_dir = processed_dir
    client = LLMChatClient(provider=config.PROVIDER_OLLAMA)
    files = sorted(processed_dir.glob("*.cleaned.json"))
    if args.video_id:
        files = [f for f in files if args.video_id in f.name]
    if args.limit:
        files = files[: args.limit]
    if not files:
        logging.info("No cleaned transcript files found in %s", processed_dir)
        return

    logging.info("Summarizing %d file(s) from %s", len(files), processed_dir)
    success_count = 0
    fail_count = 0
    for file_path in iter_with_progress(files, desc="Summarizing"):
        if process_one(file_path, output_dir, client, args.force):
            success_count += 1
        else:
            fail_count += 1
    logging.info("Done. success=%d fail=%d total=%d", success_count, fail_count, len(files))


if __name__ == "__main__":
    main()
