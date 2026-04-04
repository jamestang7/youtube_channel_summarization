import Link from "next/link";
import { notFound } from "next/navigation";

import { formatRange, getVideoOutline } from "@/lib/content";
import { recordEvent } from "@/lib/events";
import { youtubeWatchUrl } from "@/lib/youtube";

export default async function VideoOutlinePage({ params }: { params: Promise<{ videoId: string }> }) {
  const { videoId } = await params;
  const outline = await getVideoOutline(videoId);
  if (!outline) return notFound();

  await recordEvent("outline_opened", { videoId });

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="panel">
        <h1 style={{ marginTop: 0 }}>{outline.title}</h1>
        <div className="muted">
          {outline.meta.date} · {outline.meta.type} · {outline.meta.status}
        </div>
        <p className="muted" style={{ marginTop: 12 }}>
          {outline.summary}
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          <a className="link-button" href={outline.youtubeUrl} target="_blank" rel="noopener noreferrer">
            打开原视频
          </a>
          <Link
            className="link-button"
            href={`/search?q=${encodeURIComponent(outline.title)}&videoId=${outline.videoId}&event=related&auto=0`}
          >
            去搜索相关观点
          </Link>
        </div>
      </section>

      <section className="panel">
        <h2 style={{ marginTop: 0 }}>视频大纲</h2>
        <div className="outline-list">
          {outline.segments.map((seg, idx) => {
            const atUrl = youtubeWatchUrl(videoId, seg.start);
            return (
              <article key={`${seg.start}-${idx}`} className="outline-item">
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <a
                    className="muted"
                    href={atUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ textDecoration: "underline", textUnderlineOffset: 2 }}
                  >
                    {formatRange(seg.start, seg.end)}
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
                </div>
                <div style={{ fontWeight: 700, marginTop: 4 }}>{seg.title}</div>
                <div className="muted" style={{ marginTop: 6 }}>
                  {seg.description}
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
