import { NextRequest, NextResponse } from "next/server";

const ASK_URL = process.env.BACKEND_ASK_URL ?? "http://127.0.0.1:8000/api/ask";

export async function POST(req: NextRequest) {
  const body = await req.json();

  try {
    const resp = await fetch(ASK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });

    const data = await resp.json();
    if (!resp.ok) {
      return NextResponse.json({ error: data?.error ?? "后端请求失败" }, { status: resp.status });
    }

    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      { error: `无法连接Python后端: ${String(err)}` },
      { status: 502 }
    );
  }
}
