import { NextRequest, NextResponse } from "next/server";

import type { EventType } from "@/lib/types";
import { recordEvent } from "@/lib/events";

export async function POST(req: NextRequest) {
  const body = (await req.json()) as { type?: EventType; payload?: Record<string, unknown> };
  if (!body.type) {
    return NextResponse.json({ error: "type required" }, { status: 400 });
  }

  await recordEvent(body.type, body.payload ?? {});
  return NextResponse.json({ ok: true });
}
