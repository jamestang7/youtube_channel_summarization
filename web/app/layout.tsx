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
      </body>
    </html>
  );
}
