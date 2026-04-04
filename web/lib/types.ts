export type EventType =
  | "query_submitted"
  | "source_clicked"
  | "outline_opened"
  | "related_search_clicked";

export type EventPayload = {
  query?: string;
  videoId?: string;
  sourceIndex?: number;
  sourceUrl?: string;
};

export type UsageEvent = {
  id: string;
  type: EventType;
  ts: string;
  payload: EventPayload;
};

export type OutlineSegment = {
  start: number;
  end: number;
  title: string;
  description: string;
};

export type VideoOutline = {
  videoId: string;
  title: string;
  youtubeUrl: string;
  thumbnail: string;
  summary: string;
  meta: {
    date: string;
    type: string;
    status: string;
    durationSec: number;
  };
  segments: OutlineSegment[];
};

export type RankedVideo = {
  videoId: string;
  title: string;
  thumbnail: string;
  youtubeUrl: string;
  summary: string;
  date: string;
  type: string;
  status: string;
  score: number;
};
