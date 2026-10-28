"""Automatic quality check: Claude looks at frames of a generated clip and rejects visible defects before posting."""
from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from .llm import INT, STR, Claude, arr, obj
from .voice import duration as probe

SYSTEM = ("You are a strict quality inspector for short product videos about stickers, made with AI video models. "
          "You judge only what is visible in the frames.")

CHECKS = """Reject the clip (ok = false) if a viewer would notice any of these:
- a sticker that appears later is drawn underneath an earlier one, or stickers swap their layering between frames
- a sticker moves, resizes, morphs or changes its artwork after it has landed
- warped, melted, duplicated, cut-off or half-transparent stickers
- hands or fingers that look unnatural (extra or missing fingers, fingers merging with objects)
- objects or stickers appearing out of nowhere or vanishing
- text, letters or watermarks inside the scene"""

SCHEMA = obj(ok={"type": "boolean"}, score=INT, issues=arr(STR))


def frames(video: Path, count: int = 6, width: int = 432) -> list[bytes]:
    """`count` evenly spaced JPEG frames (small, to keep the check cheap)."""
    length = probe(video)
    shots = []
    for i in range(count):
        t = min(length - 0.05, (i + 0.5) * length / count)
        shots.append(subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
             "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
            capture_output=True, check=True).stdout)
    return shots


def check_clip(claude: Claude, video: Path, expectation: str, count: int = 6) -> dict:
    """Returns {"ok": bool, "score": 1-10, "issues": [...]}."""
    content = []
    for i, jpg in enumerate(frames(video, count), start=1):
        content.append({"type": "text", "text": f"Frame {i} of {count}"})
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpg).decode()}})
    content.append({"type": "text", "text": (
        f"These frames are in time order from a short Instagram video.\nWhat should happen: {expectation}\n\n{CHECKS}\n\n"
        "score: 1-10 for how professional it looks. issues: short descriptions, empty if none.")})
    return claude.ask_json(SYSTEM, content, SCHEMA)
