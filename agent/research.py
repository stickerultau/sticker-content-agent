"""Step 1 — Topic research: picks today's theme from upcoming occasions, Google Trends and post history."""
from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET

import requests

from . import log
from .llm import INT, STR, Claude, arr, obj

FORMAT_BRIEF = {
    "carousel": "a carousel presenting a themed pack of {n} original sticker designs",
    "reel": ("a 9-second vertical video without voiceover where {n} sticker designs land one by one on a real surface "
             "(a laptop, a car window, a shop window, a fridge, a notebook...) until it is covered"),
}


def system_prompt(cfg: dict) -> str:
    page = cfg["page"]
    pillars = "\n".join(f"- {p}" for p in page["pillars"])
    rules = "\n".join(f"- {r}" for r in page["rules"])
    offer = page.get("shop_offer", {})
    surfaces = "; ".join(offer.get("surfaces", []))
    materials = ", ".join(m["name"] for m in offer.get("materials", []))
    return f"""You are the creative director of "{page['name']}" (@{page['handle']}), an Instagram page in Romania that publishes original sticker designs.
{page['concept']}

Audience: {page['audience']}
Voice: {page['voice']}
Shop: followers order any design at @{page['shop_handle']}, printed on any surface ({surfaces}) and in these materials: {materials}.

Content pillars:
{pillars}

Hard rules:
{rules}

Everything the audience reads is in {page['language']} with correct diacritics (ș and ț with comma below, ă, â, î).
Descriptions meant for the image model are in English."""


def upcoming_occasions(occasions: dict, today: dt.date, days: int = 21) -> list[str]:
    found = []
    for mmdd, name in occasions.items():
        month, day = (int(x) for x in mmdd.split("-"))
        for year in (today.year, today.year + 1):
            try:
                date = dt.date(year, month, day)
            except ValueError:
                continue
            delta = (date - today).days
            if 0 <= delta <= days:
                when = "TODAY" if delta == 0 else f"in {delta} days"
                found.append((delta, f"- {name}: {date:%d %B} ({when})"))
    return [line for _, line in sorted(found)]


def google_trends(geo: str = "RO", limit: int = 15) -> list[str]:
    try:
        response = requests.get(f"https://trends.google.com/trending/rss?geo={geo}", timeout=15)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        return [item.findtext("title") for item in root.iter("item") if item.findtext("title")][:limit]
    except Exception as exc:  # trends are optional inspiration
        log.warn(f"Google Trends unavailable ({exc.__class__.__name__}), continuing without it")
        return []


def research(claude: Claude, cfg: dict, fmt: str, recent: list[str], today: dt.date) -> dict:
    count = cfg["formats"][fmt]["items" if fmt == "carousel" else "stickers"]
    reel_rule = ("\n- For a reel: pick a theme whose people will recognize themselves in it and send it to friends, with "
                 "room for designs that build up to a punchline sticker at the end.") if fmt == "reel" else ""
    occasions = upcoming_occasions(cfg["page"]["occasions"], today)
    trends = google_trends()
    log.info(f"{len(occasions)} upcoming occasions, {len(trends)} trending searches, {len(recent)} past posts")

    prompt = f"""TODAY: {today:%A, %d %B %Y} (Romania).
TODAY'S FORMAT: {FORMAT_BRIEF[fmt].format(n=count)}.

UPCOMING OCCASIONS (next 3 weeks):
{chr(10).join(occasions) or "- none"}

WHAT ROMANIA IS SEARCHING TODAY (Google Trends). Use one only if it fits naturally, is family friendly and will still make sense in a week:
{chr(10).join(f"- {t}" for t in trends) or "- unavailable"}

ALREADY POSTED, most recent first. Do not repeat these themes or close variations of them:
{chr(10).join(f"- {r}" for r in recent) or "- nothing yet, this is one of the first posts"}

Brainstorm 6 clearly different themes for today's post. Score each from 1 to 10 for how likely people are to stop scrolling, save or share it, and want these stickers on their own things. Then choose the strongest one.
Guidelines:
- Use an upcoming occasion when it is close, but keep at most about 1 post in 3 seasonal. Otherwise rotate pillars compared to the recent history.
- Specific beats generic: "stickere pentru programatorii care fac deploy vinerea" beats "stickere pentru programatori".
- The theme must support {count} visually different designs.{reel_rule}
Write theme, angle and why in Romanian. "occasion" is the occasion name, or an empty string."""

    schema = obj(
        ideas=arr(obj(theme=STR, angle=STR, pillar=STR, score=INT)),
        chosen=obj(theme=STR, angle=STR, pillar=STR, occasion=STR, why=STR),
    )
    result = claude.ask_json(system_prompt(cfg), prompt, schema)
    chosen = result["chosen"]
    log.info(f"Theme: {chosen['theme']}")
    return {**chosen, "ideas": result["ideas"], "occasions": occasions, "trends": trends}
