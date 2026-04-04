import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";

const PROCESSED_DIR = path.join(process.cwd(), "..", "data", "processed");

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ videoId: string }> }
) {
  const { videoId } = await params;
  if (!videoId || !/^[\w-]{6,20}$/.test(videoId)) {
    return NextResponse.json({ error: "invalid" }, { status: 400 });
  }
  try {
    const raw = await fs.readFile(path.join(PROCESSED_DIR, `${videoId}.outline.json`), "utf-8");
    return NextResponse.json(JSON.parse(raw));
  } catch {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }
}
