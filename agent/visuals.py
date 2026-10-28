"""Step 3 — Visuals: turns sticker descriptions into images and video clips with the Higgsfield API.

All prompts share one art direction so every post looks like the same brand.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import animate, log, quality
from .higgsfield import Higgsfield, HiggsfieldError
from .llm import Claude

STICKER = (
    "ONE {material}. The sticker artwork: {design}. Bold clean outlines, vibrant saturated colors, "
    "smooth cel shading, cute cartoon illustration"
)


def material_prompt(cfg: dict, name: str) -> str:
    """English description of a shop material for the image model (falls back to the first material)."""
    materials = cfg["page"]["shop_offer"]["materials"]
    for material in materials:
        if material["name"].lower() == (name or "").lower():
            return material["prompt"]
    return materials[0]["prompt"]

PRODUCT_SHOT = (
    "Premium studio product photograph, seen from directly above: " + STICKER + ". The sticker lies flat, centered, "
    "filling about half of the frame, with generous empty space above and below it. Background: seamless matte "
    "{bg_label} paper ({bg_hex}). Soft even daylight, a very soft realistic contact shadow. Clean, minimal, high-end, "
    "ultra sharp. No text, no letters, no logos, no watermark, no hands, only one sticker."
)

MOCKUP = (
    "Photorealistic lifestyle photo: the stickers from the reference images, each with exactly the same artwork and "
    "finish, stuck on {scene}. Real printed stickers with die-cut edges, natural light, slight perspective, shallow "
    "depth of field, high-end commercial photography. Keep every sticker design faithful. No text, no logos."
)


def carousel_images(hf: Higgsfield, cfg: dict, copy: dict, palette: dict, folder: Path) -> dict:
    models = cfg["models"]
    items = copy["items"]
    log.info(f"Generating {len(items)} sticker designs")

    def one(index_item):
        index, item = index_item
        prompt = PRODUCT_SHOT.format(material=material_prompt(cfg, item.get("material")), design=item["design"],
                                     bg_label=palette["label"], bg_hex=palette["bg"])
        # 2:3 costs $0.197 vs $0.277 for 3:4 and is still larger than the 1080x1350 slide it is cropped into.
        result = hf.generate(models["sticker_image"], prompt, folder / f"item_{index:02d}.jpg",
                             extra={"aspect_ratio": "2:3"})
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


# ---------------------------------------------------------------------------------------------- reel: sticker bomb

SCENE = (
    "Vertical close-up photo, seen straight on: {surface}. {target} fills most of the frame and is completely clean "
    "and empty, ready for stickers, with nothing on it or in front of it (no wiper, handle, label or object). Soft "
    "natural light with a gentle highlight, realistic textures, high-end commercial photography, sharp focus. "
    "No stickers, no text, no logos, no people, no hands."
)

ADD_STICKER = (
    "Edit this photo: add exactly ONE new sticker stuck perfectly flat on {target}, in the {slot}, with clear space "
    "around it, not touching any other sticker. The sticker: ONE {material}. Its artwork: {design}. A premium die-cut "
    "sticker with bold clean outlines, vivid colors and a cute cartoon illustration, about {size} of the image width, "
    "slightly rotated, lit by the same light as the photo. Keep everything else exactly as it is: the same framing, "
    "camera, light and surface, and every existing sticker in the same place, size and artwork. Photorealistic. "
    "No text, no letters, no hands."
)

LAND = (
    "Locked-off static camera, a satisfying ASMR sticker video. Only one thing happens: a new die-cut sticker slaps "
    "down onto {target} in the {slot}, landing perfectly flat with a crisp, satisfying vinyl slap and a tiny bounce, "
    "its edges pressing down onto the surface. The sticker stays sharp and its artwork never changes. Every other "
    "sticker and the surface stay perfectly still and unchanged.{finale} Realistic light and reflections. Sound: one "
    "crisp sticker slap over quiet room tone, no music, no voices. No hands, no text."
)

FINALE = {  # the payoff on the last sticker: its material catches the light right after it lands
    "holografic": " Right after it lands, a rainbow shimmer sweeps across its holographic surface.",
    "epoxy 3D": " Right after it lands, a bright highlight glides across its glossy resin dome.",
    "vinil lucios": " Right after it lands, a soft glint of light glides across its glossy surface.",
}

SLOTS = ["upper left corner area", "upper right corner area", "lower left corner area", "middle left area",
         "middle right area", "upper middle area"]


def slot(index: int, count: int) -> str:
    """Where sticker `index` (1-based) lands. Stickers never overlap: an AI edit that adds a sticker over another one
    redraws it, and earlier stickers shift. The last and biggest one takes the largest free space left."""
    if index == count:
        return "largest free space left (its middle or lower right)"
    return SLOTS[(index - 1) % len(SLOTS)]


def _checked(make, check, label: str, attempts: int = 2) -> tuple[dict, dict]:
    """Makes something until Claude's quality check passes (at most `attempts` times). Returns the best try and its
    verdict; the verdict's "ok" stays False if no try passed."""
    tries = []
    for attempt in range(attempts):
        result = make(attempt)
        verdict = check(result)
        tries.append((verdict.get("score", 0), result, verdict))
        if verdict.get("ok"):
            log.info(f"  {label}: quality check passed ({verdict.get('score')}/10)")
            return result, verdict
        issues = "; ".join(verdict.get("issues", []))[:240]
        log.warn(f"  {label}: quality check failed ({verdict.get('score')}/10): {issues}"
                 + (", making it again" if attempt + 1 < attempts else ""))
    _, result, verdict = max(tries, key=lambda t: t[0])
    return result, verdict


def _entry(result: dict, verdict: dict | None = None) -> dict:
    """What media.json keeps: the file name (inside the post's media folder), its URL, model, cost, quality verdict."""
    entry = {"file": Path(result["path"]).name, "url": result["url"], "model": result["model"], "usd": result.get("usd")}
    if verdict is not None:
        entry["qa"] = verdict
    return entry


def reel_media(hf: Higgsfield, claude: Claude, cfg: dict, copy: dict, folder: Path) -> dict:
    """The empty surface, then one edit per sticker (each adds exactly one sticker on top of the previous picture, so
    the layering always follows the landing order), then one short clip per sticker between consecutive pictures.
    Claude checks every edit and clip, and anything that fails is made once more."""
    models, seconds = cfg["models"], cfg["formats"]["reel"]["clip_seconds"]
    stickers = copy["stickers"]
    n = len(stickers)
    target = copy.get("target") or "the surface"
    folder.mkdir(parents=True, exist_ok=True)

    log.info(f"Generating the empty surface ({target})")
    scene = SCENE.format(surface=copy["surface"], target=target[:1].upper() + target[1:])
    scenes = [hf.generate(models["reel_scene"], scene, folder / "scene_00.jpg", extra={"aspect_ratio": "9:16"})]
    edits = []
    log.info(f"Adding {n} stickers one at a time")
    for k, sticker in enumerate(stickers, start=1):
        where, before = slot(k, n), scenes[-1]
        prompt = ADD_STICKER.format(target=target, slot=where, material=material_prompt(cfg, sticker["material"]),
                                    design=sticker["design"], size="38%" if k == n else "a quarter")
        expectation = (f"Exactly one new sticker was added in the {where}, not touching the other stickers: "
                       f"{sticker['design']} ({sticker['material']} finish).")
        result, verdict = _checked(
            lambda attempt: hf.generate(models["reel_edit"], prompt, folder / f"scene_{k:02d}{'_b' * attempt}.jpg",
                                        refs=[before["url"]]),
            lambda r: quality.check_edit(claude, Path(before["path"]), Path(r["path"]), expectation),
            f"sticker {k} ({sticker['name']})")
        scenes.append(result)
        edits.append(verdict)

    log.info(f"Animating {n} clips (a few minutes)")

    def clip(k: int) -> tuple[dict, dict]:
        where, sticker = slot(k, n), stickers[k - 1]
        finale = FINALE.get(sticker["material"], "") if k == n else ""
        expectation = (f"One sticker ({sticker['design']}) slaps down and lands in the {where} without touching the "
                       "other stickers; the earlier stickers and the surface stay as they are." + finale)
        return _checked(
            lambda attempt: hf.generate(
                models["reel_video"], LAND.format(target=target, slot=where, finale=finale),
                folder / f"clip_{k:02d}{'_b' * attempt}.mp4",
                kind="video", required={"first_frame_url": scenes[k - 1]["url"], "last_frame_url": scenes[k]["url"],
                                        "duration": seconds}),
            lambda r: quality.check_clip(claude, Path(r["path"]), expectation),
            f"clip {k}")

    with ThreadPoolExecutor(max_workers=n) as pool:
        clips = list(pool.map(clip, range(1, n + 1)))
    verdicts = edits + [v for _, v in clips]
    return {"engine": "ai_clips", "scenes": [_entry(scenes[0])] + [_entry(s, v) for s, v in zip(scenes[1:], edits)],
            "clips": [_entry(c, v) for c, v in clips],
            "qa_ok": all(v.get("ok") for v in verdicts)}


# ---------------------------------------------------------------------------------------------- reel: placed by code

CUTOUT = (
    "Product photo of ONE {material}, seen from directly above, lying perfectly flat, centered and filling about 70% "
    "of the frame. The sticker artwork: {design}. Bold clean outlines, vibrant saturated colors, smooth cel shading, "
    "cute cartoon illustration. Background: perfectly flat, even, pure green screen (#00FF00): no texture, no "
    "gradient, no shadow. Soft even studio light. No text, no letters, no hands, nothing else in the frame."
)


def reel_placed_media(hf: Higgsfield, claude: Claude, cfg: dict, copy: dict, folder: Path) -> dict:
    """The empty surface and each sticker alone on a green screen; agent/animate.py cuts the stickers out, places
    them and animates the landings, so the layering is always right and nothing moves after it lands. Claude finds
    the target area on the photo and checks every cut-out; a failed sticker is made once more."""
    models, stickers = cfg["models"], copy["stickers"]
    target = copy.get("target") or "the surface"
    folder.mkdir(parents=True, exist_ok=True)
    scene_path = folder / "scene_00.jpg"
    if scene_path.exists():          # a surface photo placed here on purpose is reused
        scene = {"path": str(scene_path), "url": None, "model": "reused", "usd": 0}
    else:
        log.info(f"Generating the empty surface ({target})")
        prompt = SCENE.format(surface=copy["surface"], target=target[:1].upper() + target[1:])
        scene = hf.generate(models["reel_scene"], prompt, scene_path, extra={"aspect_ratio": "9:16"})
    box = quality.locate(claude, scene_path, target)
    if box is None:
        log.warn(f"Couldn't locate {target} on the photo; using the middle of the picture")
        box = (0.1, 0.25, 0.9, 0.75)

    def sticker(k: int) -> tuple[dict, dict]:
        item = stickers[k - 1]
        prompt = CUTOUT.format(material=material_prompt(cfg, item["material"]), design=item["design"])

        def check(result: dict) -> dict:
            raw = Path(result["path"])
            image, problems = animate.cutout(raw, clear=item["material"] in animate.CLEAR)
            if problems:
                return {"ok": False, "score": 2, "issues": problems}
            image.save(raw.with_name(raw.stem + "_cut.png"))
            return quality.check_cutout(claude, image, f"{item['design']} ({item['material']} finish)")

        return _checked(
            lambda attempt: hf.generate(models["reel_sticker"], prompt, folder / f"sticker_{k:02d}{'_b' * attempt}.png",
                                        extra={"aspect_ratio": "1:1"}),
            check, f"sticker {k} ({item['name']})")

    log.info(f"Generating {len(stickers)} stickers on a green screen")
    with ThreadPoolExecutor(max_workers=len(stickers)) as pool:
        results = list(pool.map(sticker, range(1, len(stickers) + 1)))
    return {"engine": "placed", "scenes": [_entry(scene)], "box": list(box),
            "stickers": [_entry(r, v) for r, v in results], "qa_ok": all(v.get("ok") for _, v in results)}
