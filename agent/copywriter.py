"""Step 2 — Copywriting: Claude designs the stickers and writes every word of the post."""
from __future__ import annotations

import re

from . import log
from .llm import STR, Claude, arr, obj
from .research import system_prompt

DESIGN_GUIDE = (
    "English, 25-45 words: one clear subject with a pose or expression and 1-2 props, cute bold cartoon style, "
    "with its main colors. ORIGINAL characters only: never existing characters, mascots, celebrities, logos or brands. "
    "No text, letters or numbers in the artwork. Each design must look clearly different from the others "
    "(different subject, silhouette and dominant color) while obviously belonging to the theme."
)

CAROUSEL_SCHEMA = obj(
    kicker=STR,
    title=STR,
    items=arr(obj(name=STR, line=STR, design=STR, alt_text=STR)),
    mockup_scene=STR,
    mockup_label=STR,
    cta_title=STR,
    cta_sub=STR,
    caption=STR,
    hashtags=arr(STR),
)

REEL_SCHEMA = obj(
    hook=STR,
    clips=arr(obj(name=STR, design=STR, surface=STR, target=STR, narration=STR)),
    cta=STR,
    end_title=STR,
    end_sub=STR,
    caption=STR,
    hashtags=arr(STR),
)


def _topic_block(topic: dict) -> str:
    lines = [f"THEME: {topic['theme']}", f"ANGLE: {topic['angle']}"]
    if topic.get("occasion"):
        lines.append(f"OCCASION: {topic['occasion']}")
    return "\n".join(lines)


def _caption_rules(cfg: dict) -> str:
    shop = cfg["page"]["shop_handle"]
    core = ", ".join(cfg["page"]["hashtags_core"])
    return f"""- caption: the Instagram caption in Romanian. Line 1 is a hook (max 90 characters). Then 2-4 short lines with personality. Ask people to comment the number (or name) of their favorite and to tag a friend who needs it. Say any design can be ordered at @{shop}. No hashtags inside the caption. Max 4 emojis. Max 700 characters.
- hashtags: 6-9 relevant hashtags (Romanian and English, niche and broad), always including {core}"""


def write_carousel(claude: Claude, cfg: dict, topic: dict) -> dict:
    n = cfg["formats"]["carousel"]["items"]
    prompt = f"""Write today's carousel post.
{_topic_block(topic)}

Create exactly {n} sticker designs for this theme. For each one:
- name: catchy Romanian name, 2-4 words, max 24 characters
- line: one witty Romanian line, max 70 characters: the joke or feeling that makes someone want it
- design: {DESIGN_GUIDE}
- alt_text: Romanian alt text describing the sticker, max 120 characters

Also write:
- kicker: tiny uppercase Romanian label above the cover title, max 22 characters (for example "PACHETUL ZILEI" or the occasion)
- title: Romanian cover headline, max 46 characters. Wrap the single most important word in *asterisks*.
- mockup_scene: English description of one real-life spot where all these stickers are stuck together (for example "the lid of a closed silver laptop on a light oak desk next to a ceramic coffee cup")
- mockup_label: Romanian label for that photo, max 28 characters (for example "Așa arată pe laptop")
- cta_title: Romanian, max 30 characters, invites people to pick a favorite
- cta_sub: Romanian, max 60 characters, asks them to comment the number
{_caption_rules(cfg)}"""
    copy = claude.ask_json(system_prompt(cfg), prompt, CAROUSEL_SCHEMA)
    if len(copy["items"]) < n:
        raise RuntimeError(f"Claude returned {len(copy['items'])} designs instead of {n}")
    copy["items"] = copy["items"][:n]
    return _finish(copy, cfg, "carousel")


def write_reel(claude: Claude, cfg: dict, topic: dict) -> dict:
    n = cfg["formats"]["reel"]["clips"]
    prompt = f"""Write today's reel: about 18 seconds, a Romanian voiceover, {n} stickers each shown being peeled off its sheet and stuck onto an everyday object.
{_topic_block(topic)}

Create exactly {n} clips. For each one:
- name: catchy Romanian sticker name, 2-4 words, max 24 characters (shown on screen)
- design: {DESIGN_GUIDE}
- surface: English, where the sticker sheet lies at the start (for example "a light oak desk")
- target: English, the object it gets stuck on; vary them (for example "a matte black laptop lid", "a pastel blue water bottle", "a clear phone case")
- narration: Romanian voiceover for this clip, 7-11 words, natural and fun to hear

Also write:
- hook: the first line, shown on screen and spoken, Romanian, 4-8 words, max 42 characters. It must stop the scroll.
- cta: the spoken closing line, Romanian, 7-12 words: ask for their favorite in the comments and mention they can order at stickerul.tau
- end_title: Romanian, max 30 characters, for the end card
- end_sub: Romanian, max 60 characters, for the end card
{_caption_rules(cfg)}"""
    copy = claude.ask_json(system_prompt(cfg), prompt, REEL_SCHEMA)
    if len(copy["clips"]) < n:
        raise RuntimeError(f"Claude returned {len(copy['clips'])} clips instead of {n}")
    copy["clips"] = copy["clips"][:n]
    return _finish(copy, cfg, "reel")


# ---------------------------------------------------------------- clean-up shared by both formats

_CEDILLA = str.maketrans("şţŞŢ", "șțȘȚ")


def fix_ro(value):
    """Uses the correct Romanian comma-below letters everywhere (recursively)."""
    if isinstance(value, str):
        return value.translate(_CEDILLA).strip()
    if isinstance(value, list):
        return [fix_ro(v) for v in value]
    if isinstance(value, dict):
        return {k: fix_ro(v) for k, v in value.items()}
    return value


def clean_hashtags(tags: list[str], core: list[str], limit: int = 12) -> list[str]:
    seen, result = set(), []
    for tag in list(core) + list(tags):
        tag = "#" + re.sub(r"[^\w]", "", tag.lstrip("#"), flags=re.UNICODE)
        key = tag.lower()
        if len(tag) > 2 and key not in seen:
            seen.add(key)
            result.append(tag)
    return result[:limit]


def _finish(copy: dict, cfg: dict, fmt: str) -> dict:
    copy = fix_ro(copy)
    copy["format"] = fmt
    copy["hashtags"] = clean_hashtags(copy["hashtags"], cfg["page"]["hashtags_core"])
    copy["full_caption"] = (copy["caption"].strip() + "\n\n" + " ".join(copy["hashtags"]))[:2200]
    names = [i["name"] for i in copy.get("items", copy.get("clips", []))]
    log.info("Designs: " + " | ".join(names))
    return copy
