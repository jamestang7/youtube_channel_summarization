import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "政经鲁社长知识库",
  description: "频道检索与观点追踪",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <header className="topbar">
          <div className="brand">政经鲁社长 · 知识库</div>
          <div className="nav">
            <a href="/">首页</a>
            <a href="/search">观点搜索</a>
          </div>
          <div className="muted">中文</div>
        </header>
        <main className="shell">{children}</main>
        <footer className="site-footer shell">
          <section className="footer-disclaimer">
            <div className="section-title" style={{ marginTop: 0, marginBottom: 10 }}>
              特别提示
            </div>
            <p>
              【特别提示】本搜索结果仅供学术探讨与逻辑参考，不代表本网站立场。AI
              生成之综述内容均基于查询词义之延伸解构，本站对信息的绝对准确性、完整性及实时性不作法律担保，最终结论请以原片视听内容为准。
            </p>
          </section>

          <div className="footer-links">
            <a
              className="footer-card"
              href="https://www.youtube.com/@zrzjpl"
              target="_blank"
              rel="noopener noreferrer"
            >
              <div className="footer-card-header">
                <span className="footer-icon footer-icon-youtube" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none">
                    <rect x="2" y="5" width="20" height="14" rx="4.5" fill="currentColor" />
                    <path d="M10 9.2L15.8 12L10 14.8V9.2Z" fill="white" />
                  </svg>
                </span>
                <span className="footer-card-label">外部链接</span>
              </div>
              <strong>YouTube 频道</strong>
              <span className="muted">查看政经鲁社长频道主页</span>
            </a>
            <a className="footer-card" href="https://x.com/xzzzjpl" target="_blank" rel="noopener noreferrer">
              <div className="footer-card-header">
                <span className="footer-icon footer-icon-x" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none">
                    <path
                      d="M4 4H8.6L12.2 9.14L16.5 4H20L13.8 11.36L20.36 20H15.7L11.82 14.58L7.18 20H3.64L10.2 12.28L4 4Z"
                      fill="currentColor"
                    />
                  </svg>
                </span>
                <span className="footer-card-label">外部链接</span>
              </div>
              <strong>X 账号</strong>
              <span className="muted">查看政经鲁社长的 X 页面</span>
            </a>
          </div>
        </footer>
      </body>
    </html>
  );
}
