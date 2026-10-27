"""Public URLs for Instagram to download the media from.

Instagram's API fetches media from a public URL. Each post's files are committed to a `media` branch of the
(public) GitHub repository, replacing the previous post, and served through the jsDelivr CDN, which sends the
correct video/image content types. Nothing to sign up for beyond GitHub.
"""
from __future__ import annotations

import base64
import subprocess
import time
from pathlib import Path

import requests

from . import log
from .settings import env

GITHUB = "https://api.github.com"
BRANCH = "media"


class MediaHostError(RuntimeError):
    pass


def _token() -> str:
    token = env("MEDIA_REPO_TOKEN") or env("GITHUB_TOKEN") or env("GH_TOKEN")
    if token:
        return token
    try:  # local runs: reuse the GitHub CLI login
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception as exc:
        raise MediaHostError("No GitHub token: set GITHUB_TOKEN or run `gh auth login`.") from exc


class GitHubMediaHost:
    def __init__(self) -> None:
        self.repo = env("MEDIA_REPO") or env("GITHUB_REPOSITORY")
        if not self.repo:
            raise MediaHostError("Set MEDIA_REPO=owner/name in .env (a PUBLIC GitHub repository).")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _call(self, method: str, path: str = "", **kwargs) -> requests.Response:
        return self.session.request(method, f"{GITHUB}/repos/{self.repo}{path}", timeout=180, **kwargs)

    def check(self) -> str:
        r = self._call("GET")
        if r.status_code == 404:
            raise MediaHostError(f"Repository {self.repo} not found (or this token cannot see it).")
        r.raise_for_status()
        if r.json().get("private"):
            raise MediaHostError(f"{self.repo} is private; the CDN can only serve files from a public repository.")
        return self.repo

    def publish(self, files: dict[str, Path], message: str) -> dict[str, str]:
        """files maps published path -> local file. Returns published path -> public URL."""
        tree = []
        for name, path in files.items():
            blob = self._call("POST", "/git/blobs",
                              json={"content": base64.b64encode(path.read_bytes()).decode(), "encoding": "base64"})
            blob.raise_for_status()
            tree.append({"path": name, "mode": "100644", "type": "blob", "sha": blob.json()["sha"]})
        new_tree = self._call("POST", "/git/trees", json={"tree": tree})
        new_tree.raise_for_status()
        commit = self._call("POST", "/git/commits",
                            json={"message": message, "tree": new_tree.json()["sha"], "parents": []})
        commit.raise_for_status()
        sha = commit.json()["sha"]
        ref = self._call("PATCH", f"/git/refs/heads/{BRANCH}", json={"sha": sha, "force": True})
        if ref.status_code in (404, 422):
            ref = self._call("POST", "/git/refs", json={"ref": f"refs/heads/{BRANCH}", "sha": sha})
        ref.raise_for_status()
        urls = {name: f"https://cdn.jsdelivr.net/gh/{self.repo}@{sha}/{name}" for name in files}
        for name, url in urls.items():
            self._wait_until_served(url, files[name])
        log.info(f"Media online ({len(urls)} files)")
        return urls

    @staticmethod
    def _wait_until_served(url: str, path: Path, timeout: float = 180) -> None:
        expected = "video/" if path.suffix.lower() == ".mp4" else "image/"
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with requests.get(url, stream=True, timeout=30) as r:
                    if r.status_code == 200 and r.headers.get("content-type", "").startswith(expected):
                        return
            except requests.RequestException:
                pass
            time.sleep(5)
        raise MediaHostError(f"{url} is not reachable yet; try publishing again in a minute.")
