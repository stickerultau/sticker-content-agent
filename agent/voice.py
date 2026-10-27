"""Voiceover with Microsoft's neural voices (edge-tts, no API key) including word-level timings for captions."""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import edge_tts

from . import log


async def _speak(text: str, voice: str, rate: str, out: Path) -> list[tuple[float, float, str]]:
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(out, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append((start, start + chunk["duration"] / 1e7, chunk["text"]))
    return words


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def synthesize(lines: list[str], voice: str, rate: str, folder: Path) -> list[dict]:
    """One audio file per line, so each line can be placed exactly on its clip."""
    folder.mkdir(parents=True, exist_ok=True)
    segments = []
    for i, text in enumerate(lines):
        out = folder / f"voice_{i:02d}.mp3"
        for attempt in range(3):
            try:
                words = asyncio.run(_speak(text, voice, rate, out))
                break
            except Exception as exc:  # network hiccups on the free voice service
                if attempt == 2:
                    raise RuntimeError(f"Voiceover failed: {exc}") from exc
                log.warn(f"voice retry ({exc.__class__.__name__})")
        segments.append({"file": out.name, "text": text, "duration": duration(out), "words": words})
    return segments
