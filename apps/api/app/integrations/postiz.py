import logging
from pathlib import Path

import httpx

logger = logging.getLogger("clip.postiz")

EMPTY_SETTINGS = {"threads", "mastodon", "bluesky", "telegram", "nostr", "vk", "kick"}


class PostizError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PostizClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        root = base_url.rstrip("/")
        if root.endswith("/api/public/v1"):
            self.api = root
        else:
            self.api = f"{root}/api/public/v1"
        self.api_key = api_key

    def list_integrations(self) -> list[dict[str, object]]:
        response = self._request("GET", "/integrations")
        payload = response.json()
        if not isinstance(payload, list):
            raise PostizError("A lista de canais do Postiz não veio como array")
        return [item for item in payload if isinstance(item, dict)]

    def upload_file(self, path: Path) -> dict[str, object]:
        with path.open("rb") as handle:
            response = httpx.post(
                f"{self.api}/upload",
                headers={"Authorization": self.api_key},
                files={"file": (path.name, handle, "video/mp4")},
                timeout=300,
            )
        self._raise_for_status(response)
        payload = response.json()
        if not isinstance(payload, dict) or "id" not in payload or "path" not in payload:
            raise PostizError("O upload do Postiz não devolveu id e path")
        return payload

    def create_scheduled_post(
        self,
        *,
        integration_ids: list[tuple[str, str]],
        content: str,
        when_iso: str,
        media_id: str,
        media_path: str,
        title: str,
    ) -> dict[str, object]:
        posts = []
        for integration_id, identifier in integration_ids:
            posts.append(
                {
                    "integration": {"id": integration_id},
                    "value": [{"content": content, "image": [{"id": media_id, "path": media_path}]}],
                    "settings": platform_settings(identifier, title),
                }
            )
        body = {"type": "schedule", "date": when_iso, "shortLink": False, "tags": [], "posts": posts}
        response = self._request("POST", "/posts", json_body=body)
        payload = response.json()
        if not isinstance(payload, dict):
            return {"raw": payload}
        return payload

    def _request(self, method: str, path: str, json_body: dict | None = None) -> httpx.Response:
        response = httpx.request(
            method,
            f"{self.api}{path}",
            headers={"Authorization": self.api_key, "Content-Type": "application/json"},
            json=json_body,
            timeout=60,
        )
        self._raise_for_status(response)
        return response

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        detail = response.text[:500] or "erro sem corpo"
        logger.info("postiz_error status=%s", response.status_code)
        raise PostizError(f"Postiz respondeu {response.status_code}: {detail}", response.status_code)


def platform_settings(identifier: str, title: str) -> dict[str, object]:
    safe_title = title.strip() or "Corte"
    if identifier in {"instagram", "instagram-standalone"}:
        return {"__type": identifier, "post_type": "post"}
    if identifier == "youtube":
        visible = safe_title[:100]
        if len(visible) < 2:
            visible = "Corte"
        return {
            "__type": "youtube",
            "title": visible,
            "type": "public",
            "selfDeclaredMadeForKids": "no",
        }
    if identifier == "tiktok":
        return {
            "__type": "tiktok",
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "duet": True,
            "stitch": True,
            "comment": True,
            "autoAddMusic": "no",
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
            "content_posting_method": "DIRECT_POST",
        }
    if identifier == "facebook":
        return {"__type": "facebook"}
    if identifier in EMPTY_SETTINGS:
        return {"__type": identifier}
    return {"__type": identifier}
