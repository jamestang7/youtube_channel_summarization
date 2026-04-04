/** Canonical YouTube watch URL for a video; optional start time in seconds (`t=`). */
export function youtubeWatchUrl(videoId: string, startSec?: number): string {
  const id = String(videoId).trim();
  const base = `https://www.youtube.com/watch?v=${encodeURIComponent(id)}`;
  if (startSec === undefined || startSec === null || Number.isNaN(Number(startSec))) {
    return base;
  }
  const t = Math.max(0, Math.floor(Number(startSec)));
  return `${base}&t=${t}s`;
}
