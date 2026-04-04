import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";

import type { EventType, UsageEvent } from "./types";

const EVENTS_FILE = path.join(process.cwd(), "..", "data", "web_events.jsonl");

export async function recordEvent(type: EventType, payload: UsageEvent["payload"]): Promise<void> {
  const event: UsageEvent = {
    id: randomUUID(),
    type,
    ts: new Date().toISOString(),
    payload,
  };

  await fs.mkdir(path.dirname(EVENTS_FILE), { recursive: true });
  await fs.appendFile(EVENTS_FILE, `${JSON.stringify(event)}\n`, "utf-8");
}

export async function readEvents(): Promise<UsageEvent[]> {
  try {
    const raw = await fs.readFile(EVENTS_FILE, "utf-8");
    return raw
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line) as UsageEvent);
  } catch {
    return [];
  }
}
