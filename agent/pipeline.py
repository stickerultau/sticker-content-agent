"""The Content Creation Agent: topic research -> copy -> visuals -> design & edit -> publish."""
from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from . import animate, copywriter, costs, design, log, research, state, video, visuals
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

def reel_visuals(cfg: dict):
    """How the reel's stickers land: "placed" (cut out and animated by code) or "ai_clips" (one Kling clip each)."""
    engine = cfg["formats"]["reel"].get("engine", "placed")
    return visuals.reel_placed_media if engine == "placed" else visuals.reel_media


def check_budget(cfg: dict) -> float | None:
    budget = (cfg.get("budget") or {}).get("monthly_usd")
    spent = costs.total()
    if budget and spent >= budget:
        raise RuntimeError(f"Monthly budget reached: ${spent:.2f} of ${budget:.2f} spent this month "
                           "(raise budget.monthly_usd in config/page.yaml to continue).")
    return budget


def create(cfg: dict, fmt: str) -> Path:
    now = now_local(cfg)
    budget = check_budget(cfg)
    costs.set_post(f"{now:%Y-%m-%d_%H%M}_{fmt}")
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
            media = reel_visuals(cfg)(hf, claude, cfg, copy, post_dir / "media")
        write_json(post_dir / "media.json", media)

    with log.step(4, "Design & edit"):
        post = render(cfg, post_dir)

    post["cost_usd"] = round(claude.cost + hf.spent, 3)
    write_json(post_dir / "post.json", post)
    log.info(f"Cost of this post: ${post['cost_usd']:.2f} (Claude ${claude.cost:.2f}, Higgsfield ${hf.spent:.2f}); "
             f"this month so far: ${costs.total():.2f}" + (f" of ${budget:.2f}" if budget else ""))
    log.info(f"Saved in {post_dir}")
    return post_dir


def remake(cfg: dict, post_dir: Path) -> Path:
    """Makes the pictures (or clips) of an unpublished post again with the same theme and text, then re-renders it:
    for a post that failed the quality check or that you didn't like."""
    if (post_dir / "post.json").exists() and read_json(post_dir / "post.json").get("published"):
        raise RuntimeError("This post is already published.")
    check_budget(cfg)
    copy = read_json(post_dir / "copy.json")
    costs.set_post("_".join(post_dir.name.split("_")[:3]))   # same id as when it was created: date_time_format
    claude, hf = Claude(cfg["models"]["claude"], cfg["models"]["effort"]), Higgsfield()
    folder = post_dir / ("images" if copy["format"] == "carousel" else "media")
    shutil.rmtree(folder, ignore_errors=True)
    with log.step(3, "Create visuals again (Higgsfield)"):
        if copy["format"] == "carousel":
            media = visuals.carousel_images(hf, cfg, copy, copy["palette"], folder)
        else:
            media = reel_visuals(cfg)(hf, claude, cfg, copy, folder)
        write_json(post_dir / "media.json", media)
    with log.step(4, "Design & edit"):
        post = render(cfg, post_dir)
    spent = claude.cost + hf.spent
    post["cost_usd"] = round((post.get("cost_usd") or 0) + spent, 3)
    write_json(post_dir / "post.json", post)
    log.info(f"Cost of this remake: ${spent:.2f}; this post in total: ${post['cost_usd']:.2f}")
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
    media = read_json(post_dir / "media.json")
    overlays = post_dir / "overlays"
    overlays.mkdir(exist_ok=True)
    stickers = copy["stickers"]
    n = len(stickers)

    design.reel_hook(copy["hook"], palette, brand).save(overlays / "hook.png")
    counters = []
    for k, sticker in enumerate(stickers, start=1):
        design.reel_counter(k, n, sticker["material"], palette, brand).save(overlays / f"counter_{k}.png")
        counters.append(overlays / f"counter_{k}.png")
    design.reel_shop(copy.get("shop_cta") or page["cta_line"], palette).save(overlays / "shop.png")

    layers = {"hook": overlays / "hook.png", "counters": counters, "shop": overlays / "shop.png"}
    if media.get("engine") == "placed":
        cutouts = [animate.load_cutout(post_dir / "media" / s["file"], clear=item["material"] in animate.CLEAR)
                   for s, item in zip(media["stickers"], stickers)]
        timeline = animate.render_reel(post_dir, post_dir / "media" / media["scenes"][0]["file"], cutouts,
                                       tuple(media["box"]), [s["material"] for s in stickers], layers)
    else:
        clips = [post_dir / "media" / c["file"] for c in media["clips"]]
        timeline = video.render_reel(post_dir, clips, layers)
    finished = Image.open(overlays / f"state_{n}.jpg")
    _save(design.reel_cover(copy["hook"], finished, palette, brand, page), post_dir / "cover.jpg")
    design.contact_sheet([post_dir / "cover.jpg", *[overlays / f"state_{k}.jpg" for k in range(n + 1)]],
                         post_dir / "preview.jpg")
    if not media.get("qa_ok", True):
        log.warn("Some edits or clips failed the quality check (details in media.json); this reel won't be "
                 "published automatically.")
    return {"format": "reel", "media": ["reel.mp4"], "cover": "cover.jpg", "length_s": round(timeline["total"], 2),
            "qa_ok": media.get("qa_ok", True)}


# ---------------------------------------------------------------------------------------------- publish

def publish(cfg: dict, post_dir: Path, force: bool = False) -> dict:
    post = read_json(post_dir / "post.json")
    if post.get("published"):
        log.warn(f"Already published: {post['published'].get('permalink')}")
        return post["published"]
    if post.get("qa_ok") is False and not force:
        raise RuntimeError("This reel failed the automatic quality check (see media.json), so it was not published. "
                           f"Watch {post_dir / 'reel.mp4'}; to publish it anyway: python run.py publish "
                           f"\"{post_dir}\" --force")

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
               "names": [i["name"] for i in copy.get("items") or copy.get("stickers") or []],
               "permalink": result.get("permalink"), "media_id": result.get("media_id")})
    log.info(f"Published: {result.get('permalink')}")
    preview = url_list[0] if post["format"] == "carousel" else url_list[-1]
    budget = (cfg.get("budget") or {}).get("monthly_usd")
    log.summary(f"### {post['theme']}\n\n[Open on Instagram]({result.get('permalink')})\n\n"
                f"<img src=\"{preview}\" width=\"320\">\n\n"
                f"Cost of this post: **${post.get('cost_usd') or 0:.2f}**; this month so far: **${costs.total():.2f}**"
                + (f" of ${budget:.2f}" if budget else "") + f"\n\n```\n{post['caption']}\n```")
    return result
