"""Code-placed sticker bomb: cuts the stickers out, lays them out on the surface and animates every landing.

Once the pictures exist nothing is left to an AI model: the newest sticker is always on top, stickers never move
after they land, and every reel has the same crisp rhythm. Each landing: the sticker drops toward the surface
(shrinking to its size as it gets closer), squashes and bounces, its shadow tightens, the frame shakes slightly and
glossy materials catch a shine (a rainbow one on holographic). The video opens on the finished surface, rewinds, and
ends on that same picture, so it loops.
"""
from __future__ import annotations

import colorsys
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

from . import log
from .design import RH, RW
from .settings import ASSETS

FPS = 30
SFX = ASSETS / "sfx"
PAD_X, PAD_Y = 18, 32                    # spare canvas around the frame, so the shake never shows an edge
CW, CH = RW + 2 * PAD_X, RH + 2 * PAD_Y
OPEN_HOLD, UNSLAP = 0.35, 0.1            # the finished surface first, then each sticker lifts off, last one first
HOOK_END, END_HOLD = 2.2, 1.9            # the hook's time on screen; the hold after the last sticker (the loop point)
SHINE = {"vinil lucios": 0.5, "holografic": 0.75, "epoxy 3D": 0.7, "transparent": 0.4, "electrostatic": 0.35}
# Landing spots inside the target area (x, y, tilt). The first lands low, clear of the hook text still on screen.
SPOTS = [(0.73, 0.70, 7), (0.28, 0.30, -8), (0.72, 0.29, 10), (0.27, 0.72, -6), (0.50, 0.17, 4), (0.50, 0.85, -5)]
HERO_SPOT = (0.46, 0.57, -3)             # the last sticker: in the middle, over the others


# ---------------------------------------------------------------------------------------------- cut-outs

CLEAR = {"transparent", "electrostatic"}     # materials printed on clear film


def cutout(path: Path, clear: bool = False) -> tuple[Image.Image, list[str]]:
    """The sticker from a green-screen picture as a transparent image cropped to its edges, plus any problems found
    (no clean green background, the sticker cut off by the picture's edge, the sticker too small).
    A die-cut sticker is cut only along its outline, so green showing through gaps inside the artwork becomes the
    sticker's white paper, or see-through on clear film (`clear`)."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    r, g, b = img.split()
    rb = ImageChops.lighter(r, b)
    green = ImageChops.subtract(g, rb).point(lambda v: 255 if v > 38 else 0)
    # The background is the green that touches the picture's edges; green inside the sticker's border stays.
    marked = green.copy()
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)):
        if marked.getpixel(seed) == 255:
            ImageDraw.floodfill(marked, seed, 128)
    background = marked.point(lambda v: 255 if v == 128 else 0)
    share = background.histogram()[255] / (w * h)
    holes = Image.new("L", (w, h), 0)
    if share >= 0.12:
        # Green-screen colour trapped inside the outline (artwork greens are far less pure, so they stay).
        screen = tuple(int(v) for v in ImageStat.Stat(img, mask=background).mean)
        dr, dg, db = ImageChops.difference(img, Image.new("RGB", (w, h), screen)).split()
        holes = ImageChops.lighter(ImageChops.lighter(dr, dg), db).point(lambda v: 255 if v < 70 else 0)
        holes = ImageChops.subtract(holes, background)
        if clear:
            background = ImageChops.lighter(background, holes)
        else:
            paper = Image.new("RGB", (w, h), (248, 248, 246))
            img = Image.composite(paper, img, holes.filter(ImageFilter.MaxFilter(3)))
            r, g, b = img.split()
            rb = ImageChops.lighter(r, b)
    alpha = ImageOps.invert(background).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    edge = ImageChops.lighter(background, holes).filter(ImageFilter.MaxFilter(9))
    g = Image.composite(ImageChops.darker(g, rb.point(lambda v: min(255, v + 12))), g, edge)   # no green fringe
    sticker = Image.merge("RGBA", (r, g, b, alpha))
    box = alpha.point(lambda v: 255 if v > 24 else 0).getbbox()
    problems = []
    if share < 0.12 or not box:
        problems.append("no clean green background around the sticker")
    if box and (box[0] <= 2 or box[1] <= 2 or box[2] >= w - 2 or box[3] >= h - 2):
        problems.append("the sticker is cut off by the edge of the picture")
    if box and (box[2] - box[0]) * (box[3] - box[1]) < 0.1 * w * h:
        problems.append("the sticker is too small in the picture")
    return (sticker.crop(box) if box else sticker), problems


def load_cutout(raw: Path, clear: bool = False) -> Image.Image:
    """The saved cut-out next to the raw picture (made when the quality check ran), or a fresh one."""
    saved = raw.with_name(raw.stem + "_cut.png")
    if saved.exists():
        return Image.open(saved).convert("RGBA")
    image, _ = cutout(raw, clear)
    image.save(saved)
    return image


# ---------------------------------------------------------------------------------------------- layout and drawing

def fit_scene(scene: Image.Image):
    """The scene scaled to cover the canvas, and a function mapping a box in scene fractions to canvas fractions."""
    sw, sh = scene.size
    s = max(CW / sw, CH / sh)
    nw, nh = round(sw * s), round(sh * s)
    ox, oy = round((nw - CW) / 2), round((nh - CH) / 2)
    canvas = scene.convert("RGB").resize((nw, nh), Image.LANCZOS).crop((ox, oy, ox + CW, oy + CH)).convert("RGBA")

    def to_canvas(box):
        x0, y0, x1, y1 = box
        fx = lambda v: min(max((v * nw - ox) / CW, (PAD_X + 20) / CW), 1 - (PAD_X + 20) / CW)
        fy = lambda v: min(max((v * nh - oy) / CH, (PAD_Y + 20) / CH), 1 - (PAD_Y + 20) / CH)
        return fx(x0), fy(y0), fx(x1), fy(y1)

    return canvas, to_canvas


def layout(cutouts: list[Image.Image], box: tuple) -> list[dict]:
    """Where each sticker lands: centre and width in canvas pixels, and its tilt. `box`: the target area as canvas
    fractions (x0, y0, x1, y1). Stickers stay inside it; the last one goes in the middle, over the others."""
    x0, y0, x1, y1 = box[0] * CW, box[1] * CH, box[2] * CW, box[3] * CH
    bw, bh = x1 - x0, y1 - y0
    spots = []
    for k, img in enumerate(cutouts):
        hero = k == len(cutouts) - 1
        fx, fy, angle = HERO_SPOT if hero else SPOTS[k % len(SPOTS)]
        width = bw * (0.56 if hero else 0.44)
        height = width * img.height / img.width
        limit = bh * (0.68 if hero else 0.50)
        if height > limit:
            width, height = width * limit / height, limit
        half_w, half_h = 0.55 * width, 0.55 * height          # a little room for the tilt
        cx = min(max(x0 + fx * bw, x0 + half_w), x1 - half_w)
        cy = min(max(y0 + fy * bh, y0 + half_h), y1 - half_h)
        spots.append({"center": (cx, cy), "width": width, "angle": angle})
    return spots


def _put(canvas: Image.Image, layer: Image.Image, x: float, y: float) -> None:
    """Alpha-composites `layer` with its top-left corner at (x, y), clipped to the canvas."""
    x, y = round(x), round(y)
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(layer.width, canvas.width - x), min(layer.height, canvas.height - y)
    if right > left and bottom > top:
        canvas.alpha_composite(layer.crop((left, top, right, bottom)), (x + left, y + top))


def _rainbow(size: tuple[int, int]) -> Image.Image:
    strip = Image.new("RGB", (64, 1))
    strip.putdata([tuple(int(c * 255) for c in colorsys.hsv_to_rgb(i / 64, 0.5, 1.0)) for i in range(64)])
    return strip.resize(size, Image.BILINEAR).convert("RGBA")


def _shine(sprite: Image.Image, progress: float, strength: float, rainbow: bool) -> Image.Image:
    """The sticker with a soft diagonal band of light at `progress` (0 to 1) of its sweep across it."""
    w, h = sprite.size
    span = w + h
    c, half = -0.25 * span + progress * 1.5 * span, 0.07 * span
    band = Image.new("L", (w, h), 0)
    ImageDraw.Draw(band).polygon([(c - half, 0), (c + half, 0), (c + half - h, h), (c - half - h, h)], fill=255)
    band = band.filter(ImageFilter.GaussianBlur(max(2.0, half * 0.6)))
    band = ImageChops.multiply(band, sprite.getchannel("A")).point(lambda v: int(v * strength))
    light = _rainbow((w, h)) if rainbow else Image.new("RGBA", (w, h), (255, 255, 255, 255))
    light.putalpha(band)
    out = sprite.copy()
    out.alpha_composite(light)
    return out


def stick(canvas: Image.Image, img: Image.Image, spot: dict, scale: float = 1.0, alpha: float = 1.0,
          lift: float = 0.0, shine: float | None = None, strength: float = 0.0, rainbow: bool = False) -> None:
    """Draws one sticker and its shadow. lift: 0 = lying on the surface, 1 = high above it (bigger, blurrier shadow)."""
    w = max(4, round(spot["width"] * scale))
    sprite = img.resize((w, max(4, round(w * img.height / img.width))), Image.LANCZOS)
    sprite = sprite.rotate(spot["angle"] + 10 * lift, resample=Image.BICUBIC, expand=True)
    if shine is not None and strength:
        sprite = _shine(sprite, shine, strength, rainbow)
    if alpha < 1:
        sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * alpha)))
    blur = 3 + 20 * lift
    pad = int(blur * 3) + 2
    shadow = Image.new("RGBA", (sprite.width + 2 * pad, sprite.height + 2 * pad), (0, 0, 0, 0))
    opacity = (0.38 - 0.25 * lift) * alpha
    shadow.paste((20, 16, 30, 255), (pad, pad), sprite.getchannel("A").point(lambda v: int(v * opacity)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    cx, cy = spot["center"]
    _put(canvas, shadow, cx - shadow.width / 2 + 3 + 22 * lift, cy - shadow.height / 2 + 5 + 34 * lift)
    _put(canvas, sprite, cx - sprite.width / 2, cy - sprite.height / 2 - 40 * lift)


# ---------------------------------------------------------------------------------------------- timing

def schedule(count: int) -> tuple[list[dict], float]:
    """When each sticker appears and lands: faster and faster, with a longer "wait for it" before the last one."""
    t = OPEN_HOLD + UNSLAP * count
    events = []
    for k in range(count):
        hero, f = k == count - 1, k / max(count - 2, 1)
        pause = 0.45 if hero else 0.26 - 0.10 * f
        fall = 0.40 if hero else 0.30 - 0.08 * f
        events.append({"appear": t + pause, "impact": t + pause + fall})
        t = t + pause + fall + (END_HOLD if hero else 0.70 - 0.30 * f)
    return events, t


def _bounce(since: float) -> float:
    return 1 - 0.045 * math.exp(-since / 0.06) * math.cos(2 * math.pi * since / 0.12)


def _shake(since: float, hero: bool) -> tuple[float, float]:
    if since > 0.28:
        return 0.0, 0.0
    amp = (11 if hero else 6) * math.exp(-since / 0.07)
    return amp * math.sin(2 * math.pi * 17 * since), 0.7 * amp * math.sin(2 * math.pi * 13 * since + 0.6)


def _picture(t: float, bases, cutouts, spots, events, materials):
    """The canvas at time t and the shake offset."""
    n = len(cutouts)
    if t < OPEN_HOLD:
        return bases[n], (0.0, 0.0)
    if t < OPEN_HOLD + UNSLAP * n:                      # rewind: stickers lift off, the last one first
        step = int((t - OPEN_HOLD) / UNSLAP)
        k, p = n - 1 - step, (t - OPEN_HOLD - step * UNSLAP) / UNSLAP
        img = bases[k].copy()
        stick(img, cutouts[k], spots[k], scale=1 + 0.5 * p, alpha=1 - p, lift=p)
        return img, (0.0, 0.0)
    for k, ev in enumerate(events):
        if t < ev["appear"]:
            return bases[k], (0.0, 0.0)
        if t < ev["impact"]:                             # falling toward the surface, faster and faster
            u = (t - ev["appear"]) / (ev["impact"] - ev["appear"])
            lift = 1 - u * u
            img = bases[k].copy()
            stick(img, cutouts[k], spots[k], scale=1 + 0.55 * lift, alpha=min(1.0, u / 0.12), lift=lift)
            return img, (0.0, 0.0)
        if k + 1 == n or t < events[k + 1]["appear"]:  # landed: bounce, shine, shake
            since, hero = t - ev["impact"], k == n - 1
            shine_time = 0.6 if hero else 0.35
            if since >= max(shine_time, 0.2):
                return bases[k + 1], _shake(since, hero)
            img = bases[k].copy()
            stick(img, cutouts[k], spots[k], scale=_bounce(since),
                  shine=since / shine_time if since < shine_time else None,
                  strength=SHINE.get(materials[k], 0.0), rainbow=materials[k] == "holografic")
            return img, _shake(since, hero)
    return bases[n], (0.0, 0.0)


# ---------------------------------------------------------------------------------------------- overlays and sound

def _layer(path: Path) -> tuple[Image.Image, tuple[int, int]]:
    """A full-frame overlay cropped to what it shows (fast to fade and composite)."""
    img = Image.open(path).convert("RGBA")
    box = img.getchannel("A").getbbox() or (0, 0, 1, 1)
    return img.crop(box), (box[0], box[1])


def _overlay(frame: Image.Image, t: float, layers: dict, impacts: list[float], total: float) -> None:
    shown = []
    if t < HOOK_END:
        shown.append((layers["hook"], min(1.0, (HOOK_END - t) / 0.25)))
    for k, layer in enumerate(layers["counters"]):
        end = impacts[k + 1] if k + 1 < len(impacts) else total + 1
        if impacts[k] <= t < end:
            shown.append((layer, min(1.0, (t - impacts[k]) / 0.08)))
    if t >= impacts[-1] + 0.15:
        shown.append((layers["shop"], min(1.0, (t - impacts[-1] - 0.15) / 0.15)))
    for (img, xy), a in shown:
        if a < 1:
            img = img.copy()
            img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
        frame.alpha_composite(img, xy)


def soundtrack(path: Path, events: list[dict], total: float) -> Path:
    """A slap on every landing (the heaviest on the last one), a soft whoosh during each fall and quick reversed
    slaps during the rewind, loudness-normalised for Instagram."""
    slaps = sorted(SFX.glob("slap_[0-9]*.wav"))
    hero_slap = SFX / "slap_hero.wav"
    n = len(events)
    inputs, graph, mix = [], [], []

    def add(sample: Path) -> int:
        inputs.extend(["-i", str(sample)])
        return inputs.count("-i") - 1

    for k, ev in enumerate(events):
        hero = k == n - 1
        i = add(hero_slap if hero else slaps[k % len(slaps)])
        at = max(0, round(ev["impact"] * 1000) - 10)          # measured: the slap then peaks on the impact frame
        graph.append(f"[{i}:a]aformat=channel_layouts=stereo,volume={1.0 if hero else 0.85},adelay={at}|{at}[s{k}]")
        fall, start = ev["impact"] - ev["appear"], round(ev["appear"] * 1000)
        graph.append(f"anoisesrc=d={fall:.3f}:c=pink:r=48000:a=0.5,highpass=f=500,lowpass=f=5000,"
                     f"afade=t=in:d={fall * 0.85:.3f}:curve=exp,volume=0.16,aformat=channel_layouts=stereo,"
                     f"adelay={start}|{start}[w{k}]")
        mix += [f"[s{k}]", f"[w{k}]"]
    for step in range(n):
        k = n - 1 - step
        i = add(hero_slap if k == n - 1 else slaps[k % len(slaps)])
        at = round((OPEN_HOLD + step * UNSLAP) * 1000)
        graph.append(f"[{i}:a]aformat=channel_layouts=stereo,areverse,atempo=2.0,volume=0.45,adelay={at}|{at}[r{step}]")
        mix.append(f"[r{step}]")
    graph.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=longest,apad=whole_dur={total:.3f},"
                 f"atrim=duration={total:.3f},loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    result = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs, "-filter_complex",
                             ";".join(graph), "-map", "[aout]", "-ar", "48000", str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("FFmpeg failed on the sound:\n" + result.stderr[-2000:])
    return path


# ---------------------------------------------------------------------------------------------- the reel

def render_reel(post_dir: Path, scene: Path, cutouts: list[Image.Image], box: tuple, materials: list[str],
                layers: dict) -> dict:
    """Writes reel.mp4 and overlays/state_<k>.jpg (the surface with k stickers). `box`: the target area as fractions
    of the scene picture; `layers`: {"hook": png, "counters": [png per sticker], "shop": png}. Returns the timeline."""
    n = len(cutouts)
    canvas, to_canvas = fit_scene(Image.open(scene))
    spots = layout(cutouts, to_canvas(box))
    events, total = schedule(n)
    impacts = [e["impact"] for e in events]
    work = post_dir / "overlays"
    work.mkdir(exist_ok=True)

    bases = [canvas]                                     # bases[k]: the surface with the first k stickers on it
    for k in range(n):
        settled = bases[-1].copy()
        stick(settled, cutouts[k], spots[k])
        bases.append(settled)
    crop = lambda img, dx=0.0, dy=0.0: img.crop((round(PAD_X + dx), round(PAD_Y + dy),
                                                 round(PAD_X + dx) + RW, round(PAD_Y + dy) + RH))
    for k, base in enumerate(bases):
        crop(base).convert("RGB").save(work / f"state_{k}.jpg", quality=92)

    sound = soundtrack(work / "sound.wav", events, total)
    overlays = {"hook": _layer(layers["hook"]), "counters": [_layer(p) for p in layers["counters"]],
                "shop": _layer(layers["shop"])}
    out = post_dir / "reel.mp4"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{RW}x{RH}", "-r", str(FPS), "-i", "-", "-i", str(sound),
           "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-maxrate", "8M",
           "-bufsize", "16M", "-pix_fmt", "yuv420p", "-profile:v", "high", "-g", str(FPS * 2),
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for i in range(round(total * FPS)):
        t = i / FPS
        picture, (dx, dy) = _picture(t, bases, cutouts, spots, events, materials)
        frame = crop(picture, dx, dy)
        _overlay(frame, t, overlays, impacts, total)
        proc.stdin.write(frame.convert("RGB").tobytes())
    proc.stdin.close()
    errors = proc.stderr.read().decode(errors="replace")
    if proc.wait() != 0:
        raise RuntimeError("FFmpeg failed:\n" + errors[-2000:])
    log.info(f"Reel: {total:.1f}s, {out.stat().st_size / 1e6:.1f} MB; stickers land at "
             + ", ".join(f"{t:.1f}s" for t in impacts))
    return {"total": total, "landings": impacts}
