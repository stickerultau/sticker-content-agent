"""Higgsfield API client: submit a generation, wait for it, download the result.

Docs: https://docs.higgsfield.ai  (auth header: "Authorization: Key <id>:<secret>")
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import requests

from . import costs, log
from .settings import env

API = "https://api.higgsfield.ai"


class HiggsfieldError(RuntimeError):
    pass


class ModelRejected(HiggsfieldError):
    """The model path or its arguments were rejected (404/422): try the next model."""


class Higgsfield:
    def __init__(self) -> None:
        key_id, secret = env("HF_API_KEY_ID"), env("HF_API_KEY_SECRET")
        if not (key_id and secret) and env("HF_KEY") and ":" in env("HF_KEY"):
            key_id, secret = env("HF_KEY").split(":", 1)
        if not (key_id and secret):
            raise HiggsfieldError("Missing HF_API_KEY_ID / HF_API_KEY_SECRET (create a key at https://open.higgsfield.ai).")
        self.headers = {"Authorization": f"Key {key_id}:{secret}", "Content-Type": "application/json"}
        self.spent = 0.0

    # ------------------------------------------------------------------ low level
    def submit(self, model: str, arguments: dict) -> dict:
        headers = {**self.headers, "Idempotency-Key": str(uuid.uuid4())}
        for attempt in range(4):
            try:
                r = requests.post(f"{API}/{model}", json=arguments, headers=headers, timeout=60)
            except requests.RequestException as exc:
                if attempt == 3:
                    raise HiggsfieldError(f"Network error submitting to {model}: {exc}") from exc
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code in (400, 404, 405, 422):
                raise ModelRejected(f"{model}: HTTP {r.status_code} {r.text[:300]}")
            if r.status_code in (401, 403):
                raise HiggsfieldError("Higgsfield rejected the API key (check HF_API_KEY_ID / HF_API_KEY_SECRET).")
            if r.status_code == 402:
                raise HiggsfieldError("Higgsfield API balance is empty: top up at https://open.higgsfield.ai")
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        raise HiggsfieldError(f"{model}: still failing after retries (HTTP {r.status_code})")

    def wait(self, job: dict, timeout: float, interval: float) -> dict:
        url = job.get("status_url") or f"{API}/requests/{job['request_id']}/status"
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = requests.get(url, headers=self.headers, timeout=30)
            except requests.RequestException:
                time.sleep(interval)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(interval)
                continue
            r.raise_for_status()
            data = r.json()
            status = data.get("status")
            if status == "completed":
                return data
            if status in ("failed", "nsfw", "canceled"):
                raise HiggsfieldError(f"generation {status}: {data.get('error') or ''}".strip())
            time.sleep(interval)
        raise HiggsfieldError(f"generation timed out after {timeout:.0f}s (request {job.get('request_id')})")

    def estimate(self, model: str, arguments: dict) -> float | None:
        """Real price in USD for this exact request on your account (Higgsfield's estimate endpoint)."""
        try:
            r = requests.post(f"{API}/estimate/{model}", json=arguments, headers=self.headers, timeout=30)
            return float(r.json()["usd"]) if r.ok else None
        except (requests.RequestException, KeyError, ValueError, TypeError):
            return None

    @staticmethod
    def download(url: str, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(3):
            try:
                with requests.get(url, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    with open(path, "wb") as f:
                        for chunk in r.iter_content(1 << 16):
                            f.write(chunk)
                return path
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(3)
        return path

    # ------------------------------------------------------------------ high level
    def generate(self, chain: list[dict], prompt: str, out: Path, kind: str = "image",
                 required: dict | None = None, extra: dict | None = None,
                 refs: list[str] | None = None) -> dict:
        """Tries each model in `chain` until one returns a result. Returns {path, url, model}.

        `required` arguments are always sent (e.g. the start image of a video); `extra` ones are dropped
        on a retry if the model rejects them (e.g. an aspect ratio it does not support).
        """
        timeout, interval = (900, 10) if kind == "video" else (300, 3)
        errors = []
        for spec in chain:
            model = spec["id"]
            arguments = {"prompt": prompt, **spec.get("args", {}), **(required or {}), **(extra or {})}
            if refs is not None:
                arguments[spec.get("refs", "image_urls")] = refs[: spec.get("max_refs", len(refs))]
            for attempt in range(2):
                try:
                    data = self.wait(self.submit(model, arguments), timeout, interval)
                    url = data["video"]["url"] if kind == "video" else data["images"][0]["url"]
                    self.download(url, out)
                    usd = self.estimate(model, arguments)
                    if usd is None:  # fall back to the price noted in config/page.yaml
                        seconds = float(arguments.get("duration", 0) or 0)
                        usd = spec.get("price", 0) + spec.get("price_per_sec", 0) * seconds
                    self.spent += usd
                    costs.record("higgsfield", model, usd, out.name)
                    return {"path": str(out), "url": url, "model": model, "usd": round(usd, 4)}
                except ModelRejected as exc:
                    if attempt == 0 and extra and any(k in arguments for k in extra):
                        log.warn(f"{model} rejected optional settings; retrying without them")
                        for key in extra:
                            arguments.pop(key, None)
                        continue
                    errors.append(str(exc))
                    break
                except HiggsfieldError as exc:
                    if "API key" in str(exc) or "balance" in str(exc):
                        raise
                    errors.append(f"{model}: {exc}")
                    if attempt == 0:
                        log.warn(f"{model}: {exc}; retrying once")
                        continue
                    break
            log.warn(f"{model} unavailable, trying the next model")
        raise HiggsfieldError("No model could generate this. " + " | ".join(errors))
