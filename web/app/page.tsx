import Link from "next/link";

import { getHomepageSignals } from "@/lib/content";
import OutlineCard from "@/components/OutlineCard";

export default async function HomePage() {
  const data = await getHomepageSignals();

  const defaultQuestions = [
    "鲁社长如何评价薄瓜瓜？",
    "王立军如何登上历史舞台？",
    "泰国政治的三个阶段是什么？",
    "他信为什么会下台？",
  ];

  return (
    <div>
      <section className="panel">
        <h1 style={{ marginTop: 0 }}>政经鲁社长频道检索</h1>
        <p className="muted">用检索证据回答问题，支持时间戳回看与观点追踪。</p>
        <form action="/search" method="get">
          <div style={{ display: "flex", gap: 10 }}>
            <input className="hero-input" name="q" placeholder="例如：鲁社长如何评价薄瓜瓜？" />
            <button className="hero-button" type="submit">
              开始搜索
            </button>
          </div>
        </form>
      </section>

      <h2 className="section-title">先从大家最近最关心的问题开始</h2>
      <section className="panel chips">
        {(data.hotQuestions.length ? data.hotQuestions : defaultQuestions).map((q) => (
          <Link key={q} className="chip" href={`/search?q=${encodeURIComponent(q)}`}>
            {q}
          </Link>
        ))}
      </section>

      <h2 className="section-title">最近被反复点击、展开和引用的视频主题</h2>
      <section className="panel chips">
        {data.hotTopics.length ? (
          data.hotTopics.map((topic) => (
            <Link
              key={topic.videoId}
              className="chip"
              href={`/search?q=${encodeURIComponent(topic.title)}&videoId=${topic.videoId}&event=related&auto=0`}
            >
              {topic.title}
            </Link>
          ))
        ) : (
          <span className="muted">暂无行为数据，先从上方问题开始。</span>
        )}
      </section>

      <h2 className="section-title">近期值得先看</h2>
      <section className="video-grid">
        {data.topVideos.map((video) => (
          <OutlineCard
            key={video.videoId}
            videoId={video.videoId}
            title={video.title}
            thumbnail={video.thumbnail}
            youtubeUrl={video.youtubeUrl}
            date={video.date}
            type={video.type}
            status={video.status}
          />
        ))}
      </section>
    </div>
  );
}
