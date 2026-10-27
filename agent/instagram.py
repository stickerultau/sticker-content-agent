"""Publishing through the official Instagram API with Instagram Login (graph.instagram.com).

Free, no Facebook Page needed. Requires an Instagram professional account (Creator or Business) and a token with
the instagram_business_basic and instagram_business_content_publish permissions.
"""
from __future__ import annotations

import json
import time

import requests

from . import log, tokens
from .settings import env

API_VERSION = env("IG_API_VERSION", "v26.0")
GRAPH = f"https://graph.instagram.com/{API_VERSION}"
REFRESH_URL = "https://graph.instagram.com/refresh_access_token"
REFRESH_EVERY_DAYS = 7
OPTIONAL_FIELDS = ("is_ai_generated", "alt_text", "collaborators", "audio_name")


class InstagramError(RuntimeError):
    def __init__(self, message: str, error: dict | None = None):
        super().__init__(message)
        self.error = error or {}


class Instagram:
    def __init__(self) -> None:
        self.token_data = tokens.load()
        self._account = None

    @property
    def token(self) -> str:
        return self.token_data["access_token"]

    def _request(self, method: str, path: str, **params) -> dict:
        url = path if path.startswith("http") else f"{GRAPH}/{path}"
        params["access_token"] = self.token
        for attempt in range(4):
            try:
                if method == "GET":
                    r = requests.get(url, params=params, timeout=60)
                else:
                    r = requests.post(url, data=params, timeout=120)
            except requests.RequestException as exc:
                if attempt == 3:
                    raise InstagramError(f"Network error talking to Instagram: {exc}") from exc
                time.sleep(5 * (attempt + 1))
                continue
            data = r.json() if r.content else {}
            if r.ok and "error" not in data:
                return data
            err = data.get("error", {})
            transient = err.get("is_transient") or r.status_code >= 500 or err.get("code") in (1, 2, 4, 17, 32, 613)
            if transient and attempt < 3:
                time.sleep(20 * (attempt + 1))
                continue
            message = err.get("error_user_msg") or err.get("message") or r.text[:300]
            raise InstagramError(f"{message} (code {err.get('code')}/{err.get('error_subcode')})", err)
        raise InstagramError("Instagram kept failing")

    # ------------------------------------------------------------------ account & token
    @property
    def account(self) -> dict:
        if self._account is None:
            self._account = self._request(
                "GET", "me", fields="user_id,username,account_type,media_count,followers_count")
        return self._account

    @property
    def ig_id(self) -> str:
        return env("IG_USER_ID") or str(self.account.get("user_id") or self.account["id"])

    def refresh_if_needed(self, force: bool = False) -> bool:
        age_days = (time.time() - float(self.token_data.get("refreshed_at", 0))) / 86400
        if not force and age_days < REFRESH_EVERY_DAYS:
            return False
        try:
            data = self._request("GET", REFRESH_URL, grant_type="ig_refresh_token")
        except InstagramError as exc:  # e.g. a brand-new token (must be at least 24h old)
            log.warn(f"Token refresh skipped: {exc}")
            return False
        self.token_data.update(access_token=data["access_token"], refreshed_at=time.time(),
                               expires_in=data.get("expires_in"))
        tokens.save(self.token_data)
        log.info(f"Instagram token refreshed, valid for {int(data.get('expires_in', 0)) // 86400} more days")
        return True

    def quota_left(self) -> int | None:
        try:
            data = self._request("GET", f"{self.ig_id}/content_publishing_limit", fields="quota_usage,config")
            usage = data["data"][0]
            return int(usage["config"]["quota_total"]) - int(usage["quota_usage"])
        except Exception:
            return None

    # ------------------------------------------------------------------ publishing
    def _create(self, **fields) -> str:
        try:
            return self._request("POST", f"{self.ig_id}/media", **fields)["id"]
        except InstagramError as exc:
            dropped = [k for k in OPTIONAL_FIELDS if fields.pop(k, None) is not None]
            if not dropped:
                raise
            log.warn(f"Instagram rejected {dropped} ({exc}); retrying without them")
            return self._request("POST", f"{self.ig_id}/media", **fields)["id"]

    def _wait(self, container: str, timeout: float, interval: float) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = self._request("GET", container, fields="status_code,status")
            code = data.get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                return
            if code in ("ERROR", "EXPIRED"):
                raise InstagramError(f"Instagram could not process the media: {data.get('status')}")
            time.sleep(interval)
        raise InstagramError("Instagram took too long to process the media")

    def _publish(self, container: str) -> dict:
        media_id = self._request("POST", f"{self.ig_id}/media_publish", creation_id=container)["id"]
        info = self._request("GET", media_id, fields="permalink,timestamp")
        return {"media_id": media_id, "permalink": info.get("permalink")}

    def publish_carousel(self, image_urls: list[str], caption: str, alt_texts: list[str] | None = None,
                         collaborators: list[str] | None = None) -> dict:
        children = []
        for i, url in enumerate(image_urls):
            fields = {"image_url": url, "is_carousel_item": "true"}
            if alt_texts and i < len(alt_texts) and alt_texts[i]:
                fields["alt_text"] = alt_texts[i][:1000]
            children.append(self._create(**fields))
        for child in children:
            self._wait(child, timeout=300, interval=3)
        fields = {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption,
                  "is_ai_generated": "true"}
        if collaborators:
            fields["collaborators"] = json.dumps(collaborators)
        container = self._create(**fields)
        self._wait(container, timeout=300, interval=4)
        return self._publish(container)

    def publish_reel(self, video_url: str, caption: str, cover_url: str | None = None,
                     collaborators: list[str] | None = None) -> dict:
        fields = {"media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": "true",
                  "is_ai_generated": "true"}
        if cover_url:
            fields["cover_url"] = cover_url
        if collaborators:
            fields["collaborators"] = json.dumps(collaborators)
        container = self._create(**fields)
        self._wait(container, timeout=900, interval=10)
        return self._publish(container)
