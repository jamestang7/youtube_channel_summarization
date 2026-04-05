import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

import { readEvents } from "./events";
import type { OutlineSegment, RankedVideo, UsageEvent, VideoOutline } from "./types";

const execFileAsync = promisify(execFile);
const PROCESSED_DIR = path.join(process.cwd(), "..", "data", "processed");
const DB_FILE = path.join(process.cwd(), "..", "data", "project.db");
const RECENT_DAYS = 14;

function toIsoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function normalizeUploadDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const raw = value.trim();
  if (!raw) return null;
  if (/^\d{8}$/.test(raw)) {
    return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return null;
  return toIsoDate(parsed);
}

function deriveSummary(fullText: string): string {
  return fullText.replace(/\s+/g, "").slice(0, 150) + (fullText.length > 150 ? "…" : "");
}

function deriveSegmentTitle(text: string): string {
  const clean = text.replace(/\s+/g, "");
  return clean.slice(0, 20) + (clean.length > 20 ? "…" : "");
}

function deriveSegmentDesc(text: string): string {
  const clean = text.replace(/\s+/g, "");
  return clean.slice(20, 95) + (clean.length > 95 ? "…" : "");
}

async function readProcessedFiles(): Promise<string[]> {
  const entries = await fs.readdir(PROCESSED_DIR);
  return entries.filter((f) => f.endsWith(".cleaned.json"));
}

async function readUploadDates(): Promise<Map<string, string>> {
  const script = [
    "import json, sqlite3, sys",
    "conn = sqlite3.connect(sys.argv[1])",
    "rows = conn.execute('SELECT video_id, upload_date FROM videos').fetchall()",
    "conn.close()",
    "print(json.dumps(rows, ensure_ascii=False))",
  ].join("; ");

  try {
    const { stdout } = await execFileAsync("python", ["-c", script, DB_FILE], {
      cwd: process.cwd(),
      windowsHide: true,
    });
    const rows = JSON.parse(stdout) as Array<[string, string | null]>;
    const uploadDates = new Map<string, string>();
    for (const [videoId, uploadDate] of rows) {
      const normalized = normalizeUploadDate(uploadDate);
      if (normalized) uploadDates.set(videoId, normalized);
    }
    return uploadDates;
  } catch {
    return new Map<string, string>();
  }
}

async function readOutline(videoId: string, uploadDates: Map<string, string>): Promise<VideoOutline | null> {
  try {
    const filePath = path.join(PROCESSED_DIR, `${videoId}.cleaned.json`);
    const [raw, stat] = await Promise.all([fs.readFile(filePath, "utf-8"), fs.stat(filePath)]);
    const data = JSON.parse(raw) as {
      video_id: string;
      title: string;
      youtube_url?: string | null;
      cleaned_full_text?: string;
      segments?: Array<{ start?: number; end?: number; text?: string }>;
    };

    const segments = (data.segments ?? []).slice(0, 12).map((seg) => {
      const text = seg.text ?? "";
      return {
        start: seg.start ?? 0,
        end: seg.end ?? seg.start ?? 0,
        title: deriveSegmentTitle(text),
        description: deriveSegmentDesc(text),
      } as OutlineSegment;
    });

    const durationSec = (data.segments?.[data.segments.length - 1]?.end as number | undefined) ?? 0;
    const summary = deriveSummary(data.cleaned_full_text ?? "");
    const uploadDate = uploadDates.get(data.video_id) ?? toIsoDate(stat.mtime);

    return {
      videoId: data.video_id,
      title: data.title,
      youtubeUrl: data.youtube_url ?? `https://www.youtube.com/watch?v=${data.video_id}`,
      thumbnail: `https://i.ytimg.com/vi/${data.video_id}/hqdefault.jpg`,
      summary,
      meta: {
        date: uploadDate,
        type: "深度解读",
        status: uploadDates.has(data.video_id) ? "可检索" : "可检索 · 日期回退",
        durationSec,
      },
      segments,
    };
  } catch {
    return null;
  }
}

function withinRecentWindow(ts: string, days: number): boolean {
  const cutoff = Date.now() - days * 24 * 3600 * 1000;
  return new Date(ts).getTime() >= cutoff;
}

function scoreEvents(events: UsageEvent[], videoId: string): number {
  let score = 0;
  for (const e of events) {
    if (!withinRecentWindow(e.ts, RECENT_DAYS)) continue;
    const sameVideo = e.payload.videoId === videoId;
    if (!sameVideo) continue;

    if (e.type === "source_clicked") score += 3;
    if (e.type === "outline_opened") score += 2;
    if (e.type === "related_search_clicked") score += 1.5;
    if (e.type === "query_submitted") score += 1;
  }
  return score;
}

export async function getHomepageSignals(): Promise<{
  hotQuestions: string[];
  hotTopics: Array<{ videoId: string; title: string; score: number }>;
  topVideos: RankedVideo[];
}> {
  const [events, files, uploadDates] = await Promise.all([readEvents(), readProcessedFiles(), readUploadDates()]);

  const queryCount = new Map<string, number>();
  for (const e of events) {
    if (e.type === "query_submitted" && withinRecentWindow(e.ts, 7) && e.payload.query) {
      const q = e.payload.query.trim();
      queryCount.set(q, (queryCount.get(q) ?? 0) + 1);
    }
  }

  const outlines = await Promise.all(
    files.slice(0, 80).map((f) => readOutline(f.replace(".cleaned.json", ""), uploadDates)),
  );
  const validOutlines = outlines.filter(Boolean) as VideoOutline[];

  const rankedRows = validOutlines.map((o) => ({
    videoId: o.videoId,
    title: o.title,
    thumbnail: o.thumbnail,
    youtubeUrl: o.youtubeUrl,
    summary: o.summary,
    date: o.meta.date,
    type: o.meta.type,
    status: o.meta.status,
    score: scoreEvents(events, o.videoId),
  }));

  const ranked = [...rankedRows].sort((a, b) => b.score - a.score || b.date.localeCompare(a.date));

  const hotTopics = ranked
    .filter((r) => r.score > 0)
    .slice(0, 6)
    .map((r) => ({ videoId: r.videoId, title: r.title, score: r.score }));

  const hotQuestions = [...queryCount.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([q]) => q);

  // Recency here is YouTube upload_date from the DB, not processed file mtime.
  const topVideos = [...rankedRows].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 4);

  return {
    hotQuestions,
    hotTopics,
    topVideos,
  };
}

export async function getVideoOutline(videoId: string): Promise<VideoOutline | null> {
  const uploadDates = await readUploadDates();
  return readOutline(videoId, uploadDates);
}

function hms(sec: number): string {
  const t = Math.max(0, Math.floor(sec));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  if (h > 0) {
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function formatRange(start: number, end: number): string {
  return `${hms(start)} - ${hms(end)}`;
}
