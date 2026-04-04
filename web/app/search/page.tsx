"use client";

import { Suspense } from "react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

type Source = {
  video_id: string;
  title: string;
  start_sec: number;
  end_sec: number;
  chunk_text: string;
  youtube_url: string;
  timestamp_url: string;
};

type AskResponse = {
  answer_text: string;
  sources: Source[];
};

function fmt(sec: number): string {
  const t = Math.max(0, Math.floor(sec));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  if (h > 0) return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function injectCitationLinks(answer: string, sources: Source[]): string {
  const escaped = answer
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\n/g, "<br />");

  return escaped.replace(/\[Source\s+(\d+)\]/g, (_, p1) => {
    const idx = Number(p1) - 1;
    const src = sources[idx];
    if (!src?.timestamp_url) return `[Source ${p1}]`;
    return `<a href="${src.timestamp_url}" target="_blank" rel="noreferrer">[Source ${p1}]</a>`;
  });
}

function SearchPageContent() {
  const params = useSearchParams();
  const initialQuery = params.get("q") ?? "";
  const videoId = params.get("videoId") ?? undefined;
  const fromRelated = params.get("event") === "related";
  // All searches are manual (no POST /api/ask on load). Links may use `auto=0` to mark flows that must never auto-run; reserved `auto=1` for a future opt-in if needed.

  const [query, setQuery] = useState(initialQuery);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (fromRelated && videoId) {
      void fetch("/api/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "related_search_clicked", payload: { videoId, query: initialQuery } }),
      });
    }
  }, [fromRelated, videoId, initialQuery]);

  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);

    await fetch("/api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "query_submitted", payload: { query, videoId } }),
    });

    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: 5 }),
    });

    const data = (await res.json()) as AskResponse | { error: string };
    if (!res.ok) {
      setError((data as { error: string }).error || "请求失败");
      setLoading(false);
      return;
    }

    setResult(data as AskResponse);
    setLoading(false);
  }

  const renderedAnswer = useMemo(() => {
    if (!result) return "";
    return injectCitationLinks(result.answer_text, result.sources);
  }, [result]);

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="panel">
        <form onSubmit={submit} style={{ display: "grid", gap: 10 }}>
          <input className="hero-input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="输入问题" />
          <button className="hero-button" type="submit" disabled={loading}>
            {loading ? "检索中..." : "搜索"}
          </button>
        </form>
      </section>

      {error && <section className="panel">{error}</section>}

      {result && (
        <>
          <section className="panel">
            <h2 style={{ marginTop: 0 }}>回答</h2>
            <div className="muted" dangerouslySetInnerHTML={{ __html: renderedAnswer }} />
          </section>

          <section className="panel" style={{ display: "grid", gap: 10 }}>
            <h2 style={{ marginTop: 0 }}>来源</h2>
            {result.sources.map((src, idx) => (
              <article key={`${src.video_id}-${idx}`} className="outline-item">
                <div style={{ fontWeight: 700 }}>
                  {idx + 1}. {src.title}
                </div>
                <div className="muted">
                  {fmt(src.start_sec)} - {fmt(src.end_sec)}
                </div>
                <a
                  className="link-button"
                  href={src.timestamp_url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={() => {
                    void fetch("/api/events", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        type: "source_clicked",
                        payload: {
                          videoId: src.video_id,
                          sourceIndex: idx + 1,
                          sourceUrl: src.timestamp_url,
                          query,
                        },
                      }),
                    });
                  }}
                >
                  打开时间戳
                </a>
                <div className="muted" style={{ marginTop: 8 }}>
                  {src.chunk_text}
                </div>
              </article>
            ))}
          </section>
        </>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<section className="panel">加载中...</section>}>
      <SearchPageContent />
    </Suspense>
  );
}
