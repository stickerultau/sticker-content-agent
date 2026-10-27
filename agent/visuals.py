"""Step 3 — Visuals: turns sticker descriptions into images and video clips with the Higgsfield API.

All prompts share one art direction so every post looks like the same brand.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import log
from .higgsfield import Higgsfield, HiggsfieldError

STICKER = (
    "ONE glossy die-cut vinyl sticker. The sticker artwork: {design}. Bold clean outlines, vibrant saturated colors, "
    "smooth cel shading, cute cartoon illustration, a thick even white die-cut border around the whole shape "
    "with a subtle glossy highlight"
)

PRODUCT_SHOT = (
    "Premium studio product photograph, seen from directly above: " + STICKER + ". The sticker lies flat, centered, "
    "filling about half of the frame, with generous empty space above and below it. Background: seamless matte "
    "{bg_label} paper ({bg_hex}). Soft even daylight, a very soft realistic contact shadow. Clean, minimal, high-end, "
    "ultra sharp. No text, no letters, no logos, no watermark, no hands, only one sticker."
)

START_FRAME = (
    "Vertical close-up product photo: " + STICKER + ", still on its white glossy backing paper, lying on {surface}, "
    "with {target} visible nearby. Soft natural window light, shallow depth of field, realistic, high-end commercial "
    "photography, the sticker in the center of the frame. No text, no logos, no hands."
)

MOTION = {
    "peel": (
        "A hand enters the frame, slowly peels the sticker off its backing paper in satisfying slow motion, then presses "
        "it onto {target} and smooths it with a thumb. Stable macro camera, natural light, realistic motion. "
        "The sticker artwork stays exactly the same and undistorted."
    ),
    "float": (
        "The sticker gently lifts off its backing paper, turns slightly toward the camera so light sweeps across the "
        "glossy vinyl, then settles back down. Slow push-in, stable camera, natural light, realistic. "
        "The sticker artwork stays exactly the same and undistorted."
    ),
}
NEGATIVE = "blurry, distorted hands, extra fingers, warped or melting sticker, changing artwork, text, watermark"

MOCKUP = (
    "Photorealistic lifestyle photo: the stickers from the reference images, each with exactly the same artwork, stuck on "
    "{scene}. Real glossy vinyl with white die-cut borders, natural light, slight perspective, shallow depth of field, "
    "high-end commercial photography. Keep every sticker design faithful. No text, no logos."
)


def carousel_images(hf: Higgsfield, cfg: dict, copy: dict, palette: dict, folder: Path) -> dict:
    models = cfg["models"]
    items = copy["items"]
    log.info(f"Generating {len(items)} sticker designs")

    def one(index_item):
        index, item = index_item
        prompt = PRODUCT_SHOT.format(design=item["design"], bg_label=palette["label"], bg_hex=palette["bg"])
        result = hf.generate(models["sticker_image"], prompt, folder / f"item_{index:02d}.jpg",
                             extra={"aspect_ratio": "3:4"})
        log.info(f"  #{index} {item['name']}  ({result['model']})")
        return result

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(one, enumerate(items, start=1)))

    mockup = None
    if cfg["formats"]["carousel"].get("mockup_slide") and models.get("mockup_image"):
        try:
            prompt = MOCKUP.format(scene=copy["mockup_scene"])
            mockup = hf.generate(models["mockup_image"], prompt, folder / "mockup.jpg",
                                 extra={"aspect_ratio": "3:4"}, refs=[r["url"] for r in results])
            log.info(f"  mockup slide ({mockup['model']})")
        except HiggsfieldError as exc:
            log.warn(f"Mockup slide skipped: {exc}")
    return {"items": results, "mockup": mockup}


def reel_media(hf: Higgsfield, cfg: dict, copy: dict, folder: Path) -> list[dict]:
    models = cfg["models"]
    motion = MOTION.get(cfg["formats"]["reel"].get("motion", "peel"), MOTION["peel"])
    clips = copy["clips"]
    log.info(f"Generating {len(clips)} start frames")

    def frame(index_clip):
        index, clip = index_clip
        prompt = START_FRAME.format(design=clip["design"], surface=clip["surface"], target=clip["target"])
        return hf.generate(models["sticker_image"], prompt, folder / f"frame_{index:02d}.jpg",
                           extra={"aspect_ratio": "9:16"})

    with ThreadPoolExecutor(max_workers=4) as pool:
        frames = list(pool.map(frame, enumerate(clips, start=1)))

    log.info(f"Animating {len(clips)} clips (this takes a few minutes)")

    def animate(args):
        index, clip, still = args
        prompt = motion.format(target=clip["target"])
        result = hf.generate(models["video"], prompt, folder / f"clip_{index:02d}.mp4", kind="video",
                             required={"image_url": still["url"]}, extra={"negative_prompt": NEGATIVE})
        log.info(f"  clip {index}: {clip['name']}  ({result['model']})")
        return result

    jobs = [(i, c, f) for i, (c, f) in enumerate(zip(clips, frames), start=1)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        videos = list(pool.map(animate, jobs))
    return [{"frame": f, "clip": v} for f, v in zip(frames, videos)]
