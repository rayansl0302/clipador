import httpx


def reference_from_oembed(payload: object) -> tuple[str, str, str] | None:
    if not isinstance(payload, dict):
        return None
    title = str(payload.get("title") or "").strip()
    channel = str(payload.get("author_name") or "").strip()
    thumbnail = str(payload.get("thumbnail_url") or "").strip()
    if not title:
        return None
    if not thumbnail.startswith("https://"):
        thumbnail = ""
    return title[:200], channel[:200], thumbnail[:500]


def youtube_reference(url: str) -> tuple[str, str, str] | None:
    try:
        response = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=8,
            follow_redirects=True,
        )
        response.raise_for_status()
        return reference_from_oembed(response.json())
    except (httpx.HTTPError, ValueError):
        return None
