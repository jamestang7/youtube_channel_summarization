from __future__ import annotations

import json
import time
from typing import Any
from urllib import error, request

TRANSIENT_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


def post_json_with_retry(
    *,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    provider: str,
    timeout_seconds: int = 180,
    max_retries: int = 2,
    retry_backoff_seconds: float = 1.5,
) -> dict[str, Any]:
    req_bytes = json.dumps(payload).encode("utf-8")

    for attempt in range(max_retries + 1):
        req = request.Request(url=url, data=req_bytes, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            is_transient = exc.code in TRANSIENT_HTTP_CODES
            if is_transient and attempt < max_retries:
                time.sleep(retry_backoff_seconds * (attempt + 1))
                continue
            raise RuntimeError(f"[{provider}] HTTP error {exc.code} for {url}: {body}") from exc
        except error.URLError as exc:
            if attempt < max_retries:
                time.sleep(retry_backoff_seconds * (attempt + 1))
                continue
            raise RuntimeError(f"[{provider}] Connection error for {url}: {exc}") from exc
        except TimeoutError as exc:
            if attempt < max_retries:
                time.sleep(retry_backoff_seconds * (attempt + 1))
                continue
            raise RuntimeError(f"[{provider}] Request timeout for {url}") from exc

    raise RuntimeError(f"[{provider}] Unexpected request failure for {url}")
