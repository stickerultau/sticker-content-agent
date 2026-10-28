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
    items=arr(obj(name=STR, line=STR, design=STR, material=STR, alt_text=STR)),
    mockup_scene=STR,
    mockup_label=STR,
    cta_title=STR,
    cta_sub=STR,
    shop_cta=STR,
    caption=STR,
    hashtags=arr(STR),
)

REEL_SCHEMA = obj(
    hook=STR,
    surface=STR,
    target=STR,
    stickers=arr(obj(name=STR, design=STR, material=STR)),
    shop_cta=STR,
    caption=STR,
    hashtags=arr(STR),
)


def _material_rule(cfg: dict) -> str:
    materials = cfg["page"]["shop_offer"]["materials"]
    names = [m["name"] for m in materials]
    showcase = ", ".join(m["name"] + (f" ({m['hint']})" if m.get("hint") else "") for m in materials[1:])
    return (f'one of: {", ".join(names)}. Use "{names[0]}" for most designs and give 1-2 designs per pack a showcase '
            f"material ({showcase}) where it suits the artwork, so followers discover the shop's range")


def _shop_cta_rule(cfg: dict, where: str = "on the last slide") -> str:
    shop = cfg["page"]["shop_handle"]
    return (f"- shop_cta: Romanian, max 60 characters, shown {where}: where these can be printed, naming a "
            f"surface or material from the shop's range that fits this theme (for example \"Le vrei pe mașină? Le "
            f"printăm și holografic → @{shop}\"). It must end with @{shop}")


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

Create exactly {n} sticker designs for this theme, ordered as an escalation: each one a little funnier, cuter or more relatable than the one before, the last one the punchline of the pack, so people swipe to the end. For each one:
- name: catchy Romanian name, 2-4 words, max 24 characters
- line: one witty Romanian line, max 70 characters: the joke or feeling that makes someone want it
- design: {DESIGN_GUIDE}
- material: {_material_rule(cfg)}
- alt_text: Romanian alt text describing the sticker, max 120 characters

Also write:
- kicker: tiny uppercase Romanian label above the cover title, max 22 characters (for example "PACHETUL ZILEI" or the occasion)
- title: Romanian cover headline, max 46 characters, that names the theme and makes people curious enough to swipe to the end, without giving away the best design. Wrap the single most important word in *asterisks*.
- mockup_scene: English description of one real-life surface from the shop's range where these stickers are stuck together, chosen to fit the theme and varied from post to post (for example "the rear window of a small city car", "the glass door of a cozy café", "the lid of a closed silver laptop on a light oak desk", "a matte steel water bottle on a gym bench")
- mockup_label: Romanian label for that photo, max 28 characters (for example "Așa arată pe mașină")
- cta_title: Romanian, max 30 characters, invites people to pick a favorite
- cta_sub: Romanian, max 60 characters, asks them to comment the number
{_shop_cta_rule(cfg)}
{_caption_rules(cfg)}"""
    copy = claude.ask_json(system_prompt(cfg), prompt, CAROUSEL_SCHEMA)
    if len(copy["items"]) < n:
        raise RuntimeError(f"Claude returned {len(copy['items'])} designs instead of {n}")
    copy["items"] = copy["items"][:n]
    return _finish(copy, cfg, "carousel")


def write_reel(claude: Claude, cfg: dict, topic: dict) -> dict:
    n = cfg["formats"]["reel"]["stickers"]
    choices = ", ".join(m["name"] + (f" ({m['hint']})" if m.get("hint") else "")
                        for m in cfg["page"]["shop_offer"]["materials"])
    prompt = f"""Write today's reel: a 9-second vertical video with no voiceover, made to be watched to the end and replayed. It opens on the finished result for a split second, rewinds to an empty surface, then {n} stickers for today's theme land on it one by one with a satisfying slap while an on-screen counter goes from 1/{n} to {n}/{n}. After the last one lands, the video ends on the finished surface and loops.
{_topic_block(topic)}

What keeps people watching: the hook opens a question that only the LAST sticker answers, the counter makes them want to complete the set, and the last sticker is the payoff. Everything below serves that.

Create exactly {n} sticker designs, ordered as an escalation: each one a little funnier, cuter or more relatable for this audience than the one before. The LAST one is the punchline the hook promised: the idea people will comment about and send to a friend. For each one:
- name: catchy Romanian name, 2-4 words, max 24 characters (used in the caption)
- design: {DESIGN_GUIDE} It is seen small and fast, so give it one clear subject with a strong silhouette, readable at a glance.
- material: a DIFFERENT material for every sticker, so the reel shows the shop's range (its name appears on screen as each sticker lands). Choose from: {choices}. With 4 or more stickers, include both vinil lucios and vinil mat. The LAST sticker uses a showcase material (holografic or epoxy 3D): it catches the light when it lands.

Also write:
- surface: English, ONE real flat surface that this theme's people actually put stickers on, from the shop's range, in a setting that fits the theme, photographed straight on and close up so that it fills most of a vertical frame, clean and empty. Vary it from post to post. Examples: "the lid of a closed matte black laptop on a walnut desk, seen from above", "the rear window of a small white city car, close up from behind", "the glass door of a cozy café, seen from outside", "the door of a pastel green retro fridge in a sunny kitchen", "the cover of a kraft paper notebook on a desk".
- target: English, 2-5 words naming exactly the area of that surface the stickers go on (for example "the rear window glass", "the laptop lid", "the glass door", "the fridge door", "the notebook cover").
- hook: on-screen text for the first 2 seconds, Romanian, 3-6 words, max 34 characters, no emoji. It must make THIS theme's people stay until the last sticker: open a question only the ending answers, never describe the video and never give away the last sticker. Patterns that work (adapt them to the theme, don't copy them):
  * tease the last one: "Ultimul e pentru tine", "Așteaptă-l pe ultimul"
  * call out the audience, then tease: "Șoferi, ultimul e despre voi", "Dacă ai pisică, vezi ultimul"
  * promise something about the ending: "Ultimul e mașina tatălui tău", "Ultimul m-a făcut să râd"
  Wrong, because they describe the video or the product: "Stickere pe laptop", "4 stickere noi pentru tine".
{_shop_cta_rule(cfg, "at the end of the video")}
{_caption_rules(cfg)}
- For this reel, caption line 1 asks which of the {n} is their favorite (1 to {n}); a later line asks them to send the reel to one specific kind of friend from this theme (for example "prietenului care zice mereu «lasă că merge și așa»")."""
    copy = claude.ask_json(system_prompt(cfg), prompt, REEL_SCHEMA)
    if len(copy["stickers"]) < n:
        raise RuntimeError(f"Claude returned {len(copy['stickers'])} stickers instead of {n}")
    copy["stickers"] = copy["stickers"][:n]
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
    materials = {m["name"].lower(): m["name"] for m in cfg["page"]["shop_offer"]["materials"]}
    default_material = next(iter(materials.values()))
    entries = copy.get("items") or copy.get("stickers") or []
    for entry in entries:
        entry["material"] = materials.get(entry.get("material", "").strip().lower(), default_material)
    if fmt == "reel" and entries:
        # Every sticker in a reel shows a different material; the last (showcase) one keeps its own.
        used = {entries[-1]["material"]}
        for entry in entries[:-1]:
            if entry["material"] in used:
                entry["material"] = next((m for m in materials.values() if m not in used), entry["material"])
            used.add(entry["material"])
    shop = "@" + cfg["page"]["shop_handle"]
    cta = copy.get("shop_cta", "").strip()
    if not cta:
        cta = cfg["page"]["cta_line"]
    elif shop not in cta:
        cta = f"{cta.rstrip(' .→')} → {shop}"
    copy["shop_cta"] = cta
    copy["hashtags"] = clean_hashtags(copy["hashtags"], cfg["page"]["hashtags_core"])
    copy["full_caption"] = (copy["caption"].strip() + "\n\n" + " ".join(copy["hashtags"]))[:2200]
    log.info("Designs: " + " | ".join(e["name"] for e in entries))
    return copy
