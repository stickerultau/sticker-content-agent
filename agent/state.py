"""Post history: lets the researcher avoid repeating themes. Committed back to the repo after each scheduled run."""
from __future__ import annotations

import json

from .settings import STATE

HISTORY = STATE / "history.json"


def load() -> list[dict]:
    return json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []


def recent(n: int = 40) -> list[str]:
    return [f"{p['date']} [{p['format']}] {p['theme']}: {', '.join(p.get('names', []))}" for p in reversed(load()[-n:])]


def add(entry: dict) -> None:
    STATE.mkdir(exist_ok=True)
    items = load()
    items.append(entry)
    HISTORY.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
