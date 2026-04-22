from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from youtube_rag.core import config

STOP_TERMS = {"视频", "频道", "内容", "观点", "分析", "总结", "事件", "历史", "政治", "经济"}
DIRS = {
    "videos": config.KNOWLEDGE_DIR / "videos",
    "concepts": config.KNOWLEDGE_DIR / "concepts",
    "people": config.KNOWLEDGE_DIR / "people",
    "organizations": config.KNOWLEDGE_DIR / "organizations",
    "events": config.KNOWLEDGE_DIR / "events",
    "timelines": config.KNOWLEDGE_DIR / "timelines",
    "graph": config.KNOWLEDGE_DIR / "graph",
}


def ensure_dirs() -> None:
    config.KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    for folder in DIRS.values():
        folder.mkdir(parents=True, exist_ok=True)


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip().lower())
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "untitled"


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def format_hms(sec: float) -> str:
    t = max(0, int(sec))
    h = t // 3600
    m = (t % 3600) // 60
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def yaml_block(name: str, values: list[str]) -> list[str]:
    lines = [f"{name}:"]
    if values:
        lines.extend([f'  - "{value}"' for value in values])
    else:
        lines.append("  []")
    return lines


def load_upload_dates() -> dict[str, str]:
    if not config.DB_FILE.exists():
        return {}
    conn = sqlite3.connect(config.DB_FILE)
    try:
        rows = conn.execute("SELECT video_id, upload_date FROM videos").fetchall()
    finally:
        conn.close()
    return {str(video_id): str(upload_date or "") for video_id, upload_date in rows}


def load_outlines() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in config.PROCESSED_DIR.glob("*.outline.json"):
        try:
            out[path.stem.replace(".outline", "")] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logging.exception("Failed to read %s", path.name)
    return out


def extract_terms(text: str) -> list[str]:
    raw = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", text)
    return [token for token in raw if token not in STOP_TERMS and not token.isdigit()]


def classify_terms(title: str, summary: str, highlights: list[dict[str, Any]]) -> dict[str, list[str]]:
    blob = " ".join([title, summary] + [f"{h['title']} {h['summary']}" for h in highlights])
    counts = Counter(extract_terms(blob))
    buckets: dict[str, list[str]] = {"people": [], "organizations": [], "events": [], "concepts": []}
    for term, _ in counts.most_common(24):
        if term.endswith(("先生", "主席", "总理", "书记", "社长")):
            buckets["people"].append(term)
        elif term.endswith(("公司", "集团", "大学", "政府", "法院", "银行", "委员会", "媒体", "党")):
            buckets["organizations"].append(term)
        elif term.endswith(("事件", "会议", "战争", "危机", "改革", "选举", "运动", "案")):
            buckets["events"].append(term)
        else:
            buckets["concepts"].append(term)
    return {key: dedupe(value[:12]) for key, value in buckets.items()}


def build_video_record(payload: dict[str, Any], outline: dict[str, Any] | None, upload_dates: dict[str, str]) -> dict[str, Any]:
    video_id = str(payload.get("video_id") or "")
    title = str(payload.get("title") or video_id)
    youtube_url = str(payload.get("youtube_url") or f"https://www.youtube.com/watch?v={video_id}")
    full_text = str(payload.get("cleaned_full_text") or "")
    highlights = []
    for seg in (outline or {}).get("segments", [])[:8]:
        highlights.append(
            {
                "start_sec": float(seg.get("start_sec", 0.0)),
                "end_sec": float(seg.get("end_sec", seg.get("start_sec", 0.0))),
                "title": str(seg.get("title", "")),
                "summary": str(seg.get("summary", "")),
            }
        )
    summary = str((outline or {}).get("overall_summary") or full_text[:180]).strip()
    entities = classify_terms(title, summary, highlights)
    return {
        "kind": "video",
        "videoId": video_id,
        "slug": video_id,
        "title": title,
        "summary": summary,
        "youtubeUrl": youtube_url,
        "date": upload_dates.get(video_id, ""),
        "transcriptExcerpt": full_text[:1600],
        "highlights": highlights,
        **entities,
    }


def render_video_note(video: dict[str, Any]) -> str:
    lines = [
        "---",
        'type: "video"',
        f'video_id: "{video["videoId"]}"',
        f'title: "{video["title"]}"',
        f'published: "{video["date"]}"',
        f'youtube_url: "{video["youtubeUrl"]}"',
        *yaml_block("concepts", video["concepts"]),
        *yaml_block("people", video["people"]),
        *yaml_block("organizations", video["organizations"]),
        *yaml_block("events", video["events"]),
        "---",
        "",
        f"# {video['title']}",
        "",
        "## Summary",
        video["summary"] or "暂无",
        "",
        "## Key concepts",
        *([f"- [[{item}]]" for item in video["concepts"]] or ["- 暂无"]),
        "",
        "## Key people",
        *([f"- [[{item}]]" for item in video["people"]] or ["- 暂无"]),
        "",
        "## Organizations",
        *([f"- [[{item}]]" for item in video["organizations"]] or ["- 暂无"]),
        "",
        "## Events",
        *([f"- [[{item}]]" for item in video["events"]] or ["- 暂无"]),
        "",
        "## Timestamped highlights",
    ]
    if video["highlights"]:
        for h in video["highlights"]:
            start = int(h["start_sec"])
            lines.append(f"- [{format_hms(start)}]({video['youtubeUrl']}&t={start}s) {h['title']} — {h['summary']}")
    else:
        lines.append("- 暂无")
    lines.extend(["", "## Transcript excerpt", video["transcriptExcerpt"] or "暂无", ""])
    return "\n".join(lines)


def collect_entities(videos: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, dict[str, dict[str, Any]]] = {
        "concepts": {},
        "people": {},
        "organizations": {},
        "events": {},
    }
    field_to_kind = {"concepts": "concept", "people": "person", "organizations": "organization", "events": "event"}
    for video in videos:
        all_related = dedupe(video["concepts"] + video["people"] + video["organizations"] + video["events"])
        for field, kind in field_to_kind.items():
            for item in video[field]:
                entry = buckets[field].setdefault(
                    item,
                    {
                        "kind": kind,
                        "slug": slugify(item),
                        "title": item,
                        "summary": f"{item} 是从频道视频中提炼出的 {kind} 节点。",
                        "videoIds": [],
                        "related": [],
                    },
                )
                entry["videoIds"] = dedupe(entry["videoIds"] + [video["videoId"]])
                entry["related"] = dedupe(entry["related"] + [value for value in all_related if value != item])[:16]
    return {key: sorted(value.values(), key=lambda row: (-len(row["videoIds"]), row["title"])) for key, value in buckets.items()}


def render_entity_note(entity: dict[str, Any], video_map: dict[str, dict[str, Any]]) -> str:
    lines = [
        "---",
        f'type: "{entity["kind"]}"',
        f'name: "{entity["title"]}"',
        f'slug: "{entity["slug"]}"',
        *yaml_block("related", entity["related"]),
        *yaml_block("video_ids", entity["videoIds"]),
        "---",
        "",
        f"# {entity['title']}",
        "",
        "## Summary",
        entity["summary"],
        "",
        "## Related nodes",
        *([f"- [[{item}]]" for item in entity["related"]] or ["- 暂无"]),
        "",
        "## Mentioned in videos",
    ]
    refs = [video_map[video_id] for video_id in entity["videoIds"] if video_id in video_map]
    lines.extend([f"- [[{video['title']}]] ({video['date']})" for video in refs] or ["- 暂无"])
    return "\n".join(lines)


def build_graph(videos: list[dict[str, Any]], entity_groups: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    lookup: dict[str, str] = {}
    for video in videos:
        nodes.append({"id": f"video:{video['videoId']}", "label": video["title"], "kind": "video", "date": video["date"]})
    for group in entity_groups.values():
        for entity in group:
            node_id = f"{entity['kind']}:{entity['slug']}"
            lookup[entity["title"]] = node_id
            nodes.append({"id": node_id, "label": entity["title"], "kind": entity["kind"], "count": len(entity["videoIds"])})
    for video in videos:
        for field, kind in [("concepts", "concept"), ("people", "person"), ("organizations", "organization"), ("events", "event")]:
            for item in video[field]:
                edges.append({"source": f"video:{video['videoId']}", "target": lookup.get(item, f"{kind}:{slugify(item)}"), "kind": "mentions"})
    for group in entity_groups.values():
        for entity in group:
            source = f"{entity['kind']}:{entity['slug']}"
            for related in entity["related"]:
                edges.append({"source": source, "target": lookup.get(related, f"concept:{slugify(related)}"), "kind": "related_to"})
    uniq = []
    seen = set()
    for edge in edges:
        key = (edge["source"], edge["target"], edge["kind"])
        if key not in seen:
            seen.add(key)
            uniq.append(edge)
    return nodes, uniq


def write_timeline(videos: list[dict[str, Any]]) -> None:
    ordered = sorted(videos, key=lambda item: (item["date"], item["videoId"]), reverse=True)
    content = ["---", 'type: "timeline"', 'title: "频道时间线"', "---", "", "# 频道时间线", ""]
    content.extend([f"- {video['date'] or 'unknown'} — [[{video['title']}]]" for video in ordered])
    (DIRS["timelines"] / "channel-timeline.md").write_text("\n".join(content), encoding="utf-8")


def build_knowledge_base() -> dict[str, int]:
    ensure_dirs()
    upload_dates = load_upload_dates()
    outlines = load_outlines()
    videos: list[dict[str, Any]] = []
    for path in sorted(config.PROCESSED_DIR.glob("*.cleaned.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = build_video_record(payload, outlines.get(path.stem.replace(".cleaned", "")), upload_dates)
        videos.append(record)
        (DIRS["videos"] / f"{record['videoId']}.md").write_text(render_video_note(record), encoding="utf-8")
    video_map = {video["videoId"]: video for video in videos}
    entity_groups = collect_entities(videos)
    folder_map = {"concepts": DIRS["concepts"], "people": DIRS["people"], "organizations": DIRS["organizations"], "events": DIRS["events"]}
    for group_name, entities in entity_groups.items():
        for entity in entities:
            (folder_map[group_name] / f"{entity['slug']}.md").write_text(render_entity_note(entity, video_map), encoding="utf-8")
    nodes, edges = build_graph(videos, entity_groups)
    (DIRS["graph"] / "nodes.json").write_text(json.dumps(nodes, ensure_ascii=False, indent=2), encoding="utf-8")
    (DIRS["graph"] / "edges.json").write_text(json.dumps(edges, ensure_ascii=False, indent=2), encoding="utf-8")
    index_payload = {"videos": videos, **entity_groups}
    (config.KNOWLEDGE_DIR / "site_index.json").write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_timeline(videos)
    return {
        "videos": len(videos),
        "concepts": len(entity_groups["concepts"]),
        "people": len(entity_groups["people"]),
        "organizations": len(entity_groups["organizations"]),
        "events": len(entity_groups["events"]),
        "nodes": len(nodes),
        "edges": len(edges),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Obsidian-style knowledge notes and graph artifacts")
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    counts = build_knowledge_base()
    logging.info("Knowledge base built: %s", counts)


if __name__ == "__main__":
    main()
