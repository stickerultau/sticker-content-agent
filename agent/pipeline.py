"""The Content Creation Agent: topic research -> copy -> visuals -> design & edit -> publish."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from . import copywriter, design, log, research, state, video, visuals, voice
from .higgsfield import Higgsfield
from .hosting import GitHubMediaHost
from .instagram import Instagram
from .llm import Claude
from .settings import OUTPUT


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_local(cfg: dict) -> dt.datetime:
    return dt.datetime.now(ZoneInfo(cfg["page"]["timezone"]))


def pick_palette(cfg: dict, day: dt.date, fmt: str) -> dict:
    palettes = cfg["brand"]["palettes"]
    return palettes[(day.toordinal() + (3 if fmt == "reel" else 0)) % len(palettes)]


def _find(folder: Path, stem: str) -> Path | None:
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if (folder / f"{stem}{ext}").exists():
            return folder / f"{stem}{ext}"
    return None


def _save(img: Image.Image, path: Path) -> str:
    img.convert("RGB").save(path, "JPEG", quality=93, subsampling=0, optimize=True)
    return path.as_posix()


# ---------------------------------------------------------------------------------------------- create

def create(cfg: dict, fmt: str) -> Path:
    now = now_local(cfg)
    claude = Claude(cfg["models"]["claude"], cfg["models"]["effort"])

    with log.step(1, "Topic research"):
        topic = research.research(claude, cfg, fmt, state.recent(), now.date())
    post_dir = OUTPUT / f"{now:%Y-%m-%d_%H%M}_{fmt}_{design.slug(topic['theme'])}"
    post_dir.mkdir(parents=True, exist_ok=True)
    write_json(post_dir / "research.json", topic)

    with log.step(2, "Generate copy"):
        writer = copywriter.write_carousel if fmt == "carousel" else copywriter.write_reel
        copy = writer(claude, cfg, topic)
        copy.update(theme=topic["theme"], palette=pick_palette(cfg, now.date(), fmt))
        write_json(post_dir / "copy.json", copy)

    hf = Higgsfield()
    with log.step(3, "Create visuals (Higgsfield)"):
        if fmt == "carousel":
            media = visuals.carousel_images(hf, cfg, copy, copy["palette"], post_dir / "images")
        else:
            media = visuals.reel_media(hf, cfg, copy, post_dir / "media")
        write_json(post_dir / "media.json", media)

    with log.step(4, "Design & edit" + (" + voiceover + captions" if fmt == "reel" else "")):
        post = render(cfg, post_dir)

    post["cost_usd"] = round(claude.cost + hf.spent, 3)
    write_json(post_dir / "post.json", post)
    log.info(f"Estimated cost of this post: ${post['cost_usd']:.2f} (Claude ${claude.cost:.2f}, Higgsfield ${hf.spent:.2f})")
    log.info(f"Saved in {post_dir}")
    return post_dir


def render(cfg: dict, post_dir: Path) -> dict:
    """Builds the final slides or reel from copy.json and the generated media. Safe to re-run after edits."""
    copy = read_json(post_dir / "copy.json")
    post = render_carousel(cfg, post_dir, copy) if copy["format"] == "carousel" else render_reel(cfg, post_dir, copy)
    previous = read_json(post_dir / "post.json") if (post_dir / "post.json").exists() else {}
    post.update(theme=copy["theme"], caption=copy["full_caption"], created_at=previous.get("created_at")
                or now_local(cfg).isoformat(timespec="seconds"), cost_usd=previous.get("cost_usd"))
    write_json(post_dir / "post.json", post)
    return post


def render_carousel(cfg: dict, post_dir: Path, copy: dict) -> dict:
    brand, page, palette = cfg["brand"], cfg["page"], copy["palette"]
    images_dir, slides = post_dir / "images", post_dir / "slides"
    slides.mkdir(exist_ok=True)
    for old in slides.glob("*.jpg"):
        old.unlink()
    items = copy["items"]
    images = [Image.open(_find(images_dir, f"item_{i:02d}")).convert("RGB") for i in range(1, len(items) + 1)]

    files = [_save(design.carousel_cover(copy, images, palette, brand, page), slides / "01_cover.jpg")]
    alts = [copy["title"].replace("*", "")]
    for i, (item, image) in enumerate(zip(items, images), start=1):
        files.append(_save(design.carousel_item(item, i, len(items), image, palette, brand, page),
                           slides / f"{i + 1:02d}_{design.slug(item['name'], 24)}.jpg"))
        alts.append(item["alt_text"])
    mockup = _find(images_dir, "mockup")
    if mockup:
        files.append(_save(design.carousel_mockup(Image.open(mockup), copy["mockup_label"], palette, brand, page),
                           slides / f"{len(files) + 1:02d}_mockup.jpg"))
        alts.append(copy["mockup_label"])
    files.append(_save(design.carousel_cta(copy, images, palette, brand, page), slides / f"{len(files) + 1:02d}_cta.jpg"))
    alts.append(copy["cta_title"])
    design.contact_sheet(files, post_dir / "preview.jpg")
    log.info(f"{len(files)} slides designed")
    return {"format": "carousel", "media": [Path(f).relative_to(post_dir).as_posix() for f in files], "alt_texts": alts}


def render_reel(cfg: dict, post_dir: Path, copy: dict) -> dict:
    brand, page, palette = cfg["brand"], cfg["page"], copy["palette"]
    reel_cfg = cfg["formats"]["reel"]
    media_dir, overlays = post_dir / "media", post_dir / "overlays"
    overlays.mkdir(exist_ok=True)
    clips = copy["clips"]
    frames = [Image.open(_find(media_dir, f"frame_{k:02d}")).convert("RGB") for k in range(1, len(clips) + 1)]

    design.reel_hook(copy["hook"], palette, brand).save(overlays / "hook.png")
    for k, clip in enumerate(clips, start=1):
        design.reel_label(clip["name"], k, palette, brand).save(overlays / f"label_{k}.png")
    end_card = design.reel_end_card(copy, frames, palette, brand, page)
    end_card.save(overlays / "end_card.png")

    lines = [copy["hook"], *[c["narration"] for c in clips], copy["cta"]]
    cache = post_dir / "voice" / "segments.json"
    if cache.exists() and [s["text"] for s in read_json(cache)] == lines:
        segments = read_json(cache)
    else:
        segments = voice.synthesize(lines, reel_cfg["voice"], reel_cfg["voice_rate"], post_dir / "voice")
        write_json(cache, segments)

    clip_files = [media_dir / f"clip_{k:02d}.mp4" for k in range(1, len(clips) + 1)]
    video.render_reel(post_dir, clip_files, segments, ink=brand["ink"], volume=reel_cfg["music_volume"])
    _save(design.reel_cover(copy["hook"], frames[0], palette, brand, page), post_dir / "cover.jpg")
    design.contact_sheet([post_dir / "cover.jpg", *[_find(media_dir, f"frame_{k:02d}") for k in range(1, len(clips) + 1)],
                          overlays / "end_card.png"], post_dir / "preview.jpg")
    return {"format": "reel", "media": ["reel.mp4"], "cover": "cover.jpg"}


# ---------------------------------------------------------------------------------------------- publish

def publish(cfg: dict, post_dir: Path) -> dict:
    post = read_json(post_dir / "post.json")
    if post.get("published"):
        log.warn(f"Already published: {post['published'].get('permalink')}")
        return post["published"]

    ig = Instagram()
    ig.refresh_if_needed()
    log.info(f"Account: @{ig.account.get('username')} ({ig.account.get('account_type')})")
    left = ig.quota_left()
    if left is not None and left <= 0:
        raise RuntimeError("Instagram's 24-hour publishing limit is used up; try again later.")

    files = {f"{post_dir.name}/{Path(p).name}": post_dir / p for p in post["media"]}
    if post.get("cover"):
        files[f"{post_dir.name}/{post['cover']}"] = post_dir / post["cover"]
    urls = GitHubMediaHost().publish(files, f"media for {post_dir.name}")
    url_list = list(urls.values())
    collaborators = cfg["page"].get("collaborators") or None

    if post["format"] == "carousel":
        result = ig.publish_carousel(url_list[:len(post["media"])], post["caption"], post.get("alt_texts"), collaborators)
    else:
        result = ig.publish_reel(url_list[0], post["caption"], url_list[1] if post.get("cover") else None, collaborators)

    result["published_at"] = now_local(cfg).isoformat(timespec="seconds")
    post["published"] = result
    write_json(post_dir / "post.json", post)
    copy = read_json(post_dir / "copy.json")
    state.add({"date": result["published_at"][:10], "format": post["format"], "theme": post["theme"],
               "names": [i["name"] for i in copy.get("items", copy.get("clips", []))],
               "permalink": result.get("permalink"), "media_id": result.get("media_id")})
    log.info(f"Published: {result.get('permalink')}")
    preview = url_list[0] if post["format"] == "carousel" else url_list[-1]
    log.summary(f"### {post['theme']}\n\n[Open on Instagram]({result.get('permalink')})\n\n"
                f"<img src=\"{preview}\" width=\"320\">\n\n```\n{post['caption']}\n```")
    return result
