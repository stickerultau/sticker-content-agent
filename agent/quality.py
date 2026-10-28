"""Automatic quality check: Claude looks at generated pictures and clips and rejects visible defects before posting."""
from __future__ import annotations

import base64
import io
import subprocess
from pathlib import Path

from PIL import Image

from .llm import INT, STR, Claude, arr, obj
from .video import duration as probe

SYSTEM = ("You are a strict quality inspector for short product videos about stickers, made with AI image and video "
          "models. You judge only what is visible.")

CHECKS = """Reject the clip (ok = false) if a viewer would notice any of these (ignore differences of a few pixels, and
normal motion blur while the new sticker is moving):
- a sticker that appears later is drawn underneath an earlier one, or stickers swap their layering between frames
- a sticker moves, resizes, morphs or changes its artwork after it has landed
- warped, melted, duplicated, cut-off or half-transparent stickers once they have landed
- hands or fingers that look unnatural (extra or missing fingers, fingers merging with objects)
- objects or stickers appearing out of nowhere or vanishing (other than the new sticker arriving)
- text, letters or watermarks inside the scene"""

EDIT_CHECKS = """Reject the edit (ok = false) if any of these is true:
- not exactly one new sticker was added (none, or more than one)
- the new sticker is far from where it should be, touches or covers another sticker, or shows a clearly different
  subject than described (small differences in pose or details are fine)
- a sticker that was already there visibly moved, resized, changed its artwork or disappeared (ignore a few pixels)
- the framing, surface, light or camera angle changed noticeably
- warped, melted or duplicated stickers, or text, letters or watermarks"""

CUTOUT_CHECKS = """Reject the sticker (ok = false) if any of these is true:
- not exactly one sticker, or part of it is missing or cut off
- the artwork doesn't match its description, or it contains text, letters or numbers
- green background, green fringes or other leftovers around its edge
- warped, smeared or broken artwork"""

SCHEMA = obj(ok={"type": "boolean"}, score=INT, issues=arr(STR))
BOX_SCHEMA = obj(x0=INT, y0=INT, x1=INT, y1=INT)
SCORING = "score: 1-10 for how professional it looks. issues: short descriptions, empty if none."


def _image(jpg: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpg).decode()}}


def _jpeg(path: Path, width: int) -> bytes:
    img = Image.open(path).convert("RGB")
    img.thumbnail((width, width * 2))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


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
        content.append(_image(jpg))
    content.append({"type": "text", "text": (
        f"These frames are in time order from a short Instagram video.\nWhat should happen: {expectation}\n\n{CHECKS}\n\n"
        + SCORING)})
    return claude.ask_json(SYSTEM, content, SCHEMA)


def check_cutout(claude: Claude, sticker: Image.Image, expectation: str, width: int = 640) -> dict:
    """Looks at a cut-out sticker on a neutral grey background (so leftovers of the green screen show)."""
    sheet = Image.new("RGB", (sticker.width + 80, sticker.height + 80), (128, 128, 128))
    sheet.paste(sticker, (40, 40), sticker)
    sheet.thumbnail((width, width))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=88)
    content = [_image(buf.getvalue()),
               {"type": "text", "text": f"A sticker cut out for a video. It should be: {expectation}\n\n{CUTOUT_CHECKS}\n\n"
                + SCORING}]
    return claude.ask_json(SYSTEM, content, SCHEMA)


def locate(claude: Claude, scene: Path, target: str) -> tuple[float, float, float, float] | None:
    """Where `target` is in the photo: the largest rectangle lying entirely on it, as fractions (x0, y0, x1, y1)."""
    content = [_image(_jpeg(scene, 768)), {"type": "text", "text": (
        f"Stickers will be stuck on {target} in this photo. Give the largest rectangle that lies entirely on "
        f"{target}, not on its frame, edges, seals, handles or anything in front of it, as x0, y0, x1, y1 in "
        "thousandths of the image width and height (0 to 1000; x from the left, y from the top).")}]
    box = claude.ask_json("You locate areas in photos precisely.", content, BOX_SCHEMA)
    x0, y0, x1, y1 = (box[k] / 1000 for k in ("x0", "y0", "x1", "y1"))
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1) or x1 - x0 < 0.25 or y1 - y0 < 0.12:
        return None
    return x0, y0, x1, y1


def check_edit(claude: Claude, before: Path, after: Path, expectation: str, width: int = 640) -> dict:
    """Compares a picture before and after an edit that should add exactly one sticker."""
    content = [{"type": "text", "text": "Image 1: before the edit."}, _image(_jpeg(before, width)),
               {"type": "text", "text": "Image 2: after the edit."}, _image(_jpeg(after, width)),
               {"type": "text", "text": f"What the edit should do: {expectation}\n\n{EDIT_CHECKS}\n\n" + SCORING}]
    return claude.ask_json(SYSTEM, content, SCHEMA)
