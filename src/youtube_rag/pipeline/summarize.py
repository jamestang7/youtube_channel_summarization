"""Generate segment-level summaries for each processed transcript using Ollama."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from youtube_rag.core import config
from youtube_rag.core.database import advance_stage, get_connection, mark_error
from youtube_rag.core.utils import iter_with_progress
from youtube_rag.rag.llm_client import llm_generate

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


def summarize_group(provider: str, group: list[dict], video_title: str) -> dict:
    text = "".join(s.get("text", "") for s in group)
    start = group[0].get("start", 0)
    end = group[-1].get("end", start)
    user_prompt = (
        f"视频标题：{video_title}\n"
        f"时间段：{int(start // 60)}:{int(start % 60):02d} - {int(end // 60)}:{int(end % 60):02d}\n"
        f"内容：{text[:1200]}"
    )
    raw = llm_generate(provider=provider, system=SUMMARY_SYSTEM_PROMPT, user=user_prompt, temperature=0)
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


def process_one(path: Path, output_dir: Path, provider: str, force: bool) -> bool:
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
        result = summarize_group(provider, group, title)
        section_summaries.append(result)
        logging.info("[%s] segment %d/%d done", video_id, i + 1, len(groups))
        time.sleep(0.5)

    all_titles = "\n".join(f"- {s['title']}：{s['summary']}" for s in section_summaries)
    overall = llm_generate(
        provider=provider,
        system=OVERALL_SYSTEM_PROMPT,
        user=f"视频标题：{title}\n\n{all_titles}",
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


def collect_pending_items(video_id: str | None = None, limit: int | None = None) -> list[tuple[str, Path]]:
    query = [
        "SELECT video_id, cleaned_path FROM videos",
        "WHERE pipeline_stage = ?",
    ]
    params: list[object] = ["cleaned"]

    if video_id:
        query.append("AND video_id = ?")
        params.append(video_id)

    query.append("ORDER BY download_date")
    if limit is not None:
        query.append("LIMIT ?")
        params.append(limit)

    with get_connection() as db:
        rows = db.execute(" ".join(query), params).fetchall()

    return [(str(row[0]), Path(row[1])) for row in rows if row[1]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def run_pending(video_id: str | None = None, limit: int | None = None, force: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    output_dir = Path(config.PROCESSED_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    items = collect_pending_items(video_id=video_id, limit=limit)
    if not items:
        logging.info("No cleaned transcript files pending summarization.")
        return

    provider = config.PROVIDER_OLLAMA
    logging.info("Summarizing %d file(s) from %s", len(items), output_dir)
    success_count = 0
    fail_count = 0

    for current_video_id, file_path in iter_with_progress(items, desc="Summarizing", unit="file"):
        outline_path = output_dir / f"{current_video_id}.outline.json"
        try:
            ok = process_one(file_path, output_dir, provider, force)
        except Exception:
            ok = False
            logging.exception("[FAIL] %s unexpected summarize failure", current_video_id)

        with get_connection() as db:
            if ok:
                db.execute(
                    "UPDATE videos SET outline_path = ? WHERE video_id = ?",
                    (str(outline_path.resolve()), current_video_id),
                )
                advance_stage(db, current_video_id, "summarized")
                success_count += 1
            else:
                mark_error(db, current_video_id)
                fail_count += 1

    logging.info("Done. success=%d fail=%d total=%d", success_count, fail_count, len(items))


def main() -> None:
    args = parse_args()
    run_pending(video_id=args.video_id, limit=args.limit, force=args.force)


if __name__ == "__main__":
    main()
