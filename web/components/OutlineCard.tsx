"use client";

import { useState } from "react";

import { youtubeWatchUrl } from "@/lib/youtube";

type Segment = { start_sec: number; end_sec: number; title: string; summary: string };
type Outline = {
  video_id: string;
  title: string;
  youtube_url: string;
  overall_summary: string;
  segments: Segment[];
};

function hms(sec: number): string {
  const t = Math.max(0, Math.floor(sec));
  const m = Math.floor(t / 60);
  const s = t % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function OutlineCard({
  videoId,
  title,
  thumbnail,
  youtubeUrl,
  date,
  type,
  status,
}: {
  videoId: string;
  title: string;
  thumbnail: string;
  youtubeUrl: string;
  date: string;
  type: string;
  status: string;
}) {
  const [open, setOpen] = useState(false);
  const [outline, setOutline] = useState<Outline | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (outline) return;
    setLoading(true);
    setError(false);
    try {
      const res = await fetch(`/api/outline/${videoId}`);
      if (!res.ok) throw new Error();
      setOutline(await res.json());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <article className="video-card">
      <div style={{ display: "flex" }}>
        <div style={{ position: "relative", width: 180, minWidth: 180 }}>
          <a
            href={youtubeUrl}
            target="_blank"
            rel="noopener noreferrer"
            title="在 YouTube 打开"
            style={{ display: "block", lineHeight: 0 }}
          >
            <img
              src={thumbnail}
              alt={title}
              style={{ width: "100%", aspectRatio: "16/9", objectFit: "cover", display: "block" }}
            />
          </a>
        </div>
        <div className="video-body" style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>{title}</div>
          <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
            {date} · {type} · {status}
          </div>
          <div className="video-actions" style={{ marginTop: 10 }}>
            <button className="link-button" onClick={toggle}>
              {open ? "收起大纲" : "看大纲"}
            </button>
            <a
              className="link-button"
              href={`/search?q=${encodeURIComponent(title)}&videoId=${videoId}&event=related&auto=0`}
            >
              搜索相关观点
            </a>
          </div>
        </div>
      </div>

      {open && (
        <div style={{ borderTop: "1px solid rgba(0,0,0,0.07)", background: "#fafafa" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "10px 16px",
              borderBottom: "1px solid rgba(0,0,0,0.06)",
            }}
          >
            <span style={{ fontSize: 13, fontWeight: 600 }}>段落大纲</span>
            {outline && (
              <span
                style={{
                  fontSize: 12,
                  color: "#6e6e73",
                  background: "rgba(0,0,0,0.06)",
                  borderRadius: 999,
                  padding: "2px 8px",
                }}
              >
                {outline.segments.length} 段
              </span>
            )}
          </div>

          {loading && <div style={{ padding: "20px 16px", color: "#6e6e73", fontSize: 13 }}>生成中…</div>}
          {error && (
            <div style={{ padding: "20px 16px", color: "#c0392b", fontSize: 13 }}>
              大纲暂未生成，请先运行 summarize.py
            </div>
          )}

          {outline && (
            <>
              <div
                style={{
                  margin: "12px 16px",
                  background: "#fff",
                  border: "1px solid rgba(0,0,0,0.08)",
                  borderRadius: 10,
                  padding: "10px 14px",
                }}
              >
                <div
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    color: "#6e6e73",
                    textTransform: "uppercase",
                    letterSpacing: "0.4px",
                    marginBottom: 6,
                  }}
                >
                  内容摘要
                </div>
                <div style={{ fontSize: 13, lineHeight: 1.65 }}>{outline.overall_summary}</div>
              </div>
              {outline.segments.map((seg, i) => {
                const atUrl = youtubeWatchUrl(outline.video_id, seg.start_sec);
                return (
                  <div
                    key={i}
                    style={{
                      padding: "12px 16px",
                      borderBottom: "1px solid rgba(0,0,0,0.05)",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6, flexWrap: "wrap" }}>
                      <a
                        href={atUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          fontSize: 11,
                          fontWeight: 600,
                          color: "#0071e3",
                          background: "#e8f1fc",
                          borderRadius: 6,
                          padding: "3px 8px",
                          fontFamily: "monospace",
                          whiteSpace: "nowrap",
                          textDecoration: "none",
                        }}
                      >
                        {hms(seg.start_sec)} – {hms(seg.end_sec)}
                      </a>
                      <a
                        className="link-button"
                        href={atUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: 12, padding: "2px 8px" }}
                      >
                        打开此段
                      </a>
                      <span style={{ fontSize: 14, fontWeight: 600 }}>{seg.title}</span>
                    </div>
                    <div style={{ fontSize: 13, color: "#3a3a3c", lineHeight: 1.6 }}>{seg.summary}</div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      )}
    </article>
  );
}
