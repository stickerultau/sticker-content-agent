"""Cost ledger: every paid API call is recorded with its real price, so spend is visible per post, day and month.

Higgsfield prices come from its estimate endpoint (your account's real rates); Claude's from the token counts in each
response. The ledger is state/costs.jsonl, committed by the schedule like the post history.
"""
from __future__ import annotations

import datetime as dt
import json
import threading
from collections import defaultdict

from .settings import STATE

LEDGER = STATE / "costs.jsonl"
_context = {"post": None}
_lock = threading.Lock()   # images and clips are generated in parallel threads


def set_post(post_id: str | None) -> None:
    """Every cost recorded from now on is attributed to this post."""
    _context["post"] = post_id


def record(service: str, model: str, usd: float, detail: str = "") -> None:
    LEDGER.parent.mkdir(exist_ok=True)
    entry = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "post": _context["post"],
             "service": service, "model": model, "usd": round(float(usd), 4)}
    if detail:
        entry["detail"] = detail
    with _lock, open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]


def total(month: str | None = None, post: str | None = None) -> float:
    month = month or dt.date.today().strftime("%Y-%m")
    return round(sum(e["usd"] for e in load()
                     if (post is None and e["at"].startswith(month)) or (post is not None and e["post"] == post)), 4)


def report(budget: float | None = None) -> str:
    entries = load()
    if not entries:
        return "No costs recorded yet."
    month = dt.date.today().strftime("%Y-%m")
    by_month, by_model, by_post = defaultdict(float), defaultdict(float), defaultdict(float)
    for e in entries:
        by_month[e["at"][:7]] += e["usd"]
        if e["at"].startswith(month):
            by_model[f"{e['service']}: {e['model']}"] += e["usd"]
            by_post[e["post"] or "(tests and other)"] += e["usd"]
    lines = ["Spend per month:"] + [f"  {m}  ${v:7.2f}" for m, v in sorted(by_month.items())]
    if budget:
        lines.append(f"This month: ${by_month[month]:.2f} of ${budget:.2f} budget ({by_month[month] / budget:.0%})")
    lines += ["", f"This month by model ({month}):"]
    lines += [f"  ${v:7.2f}  {k}" for k, v in sorted(by_model.items(), key=lambda kv: -kv[1])]
    lines += ["", "This month by post:"]
    lines += [f"  ${v:7.2f}  {k}" for k, v in sorted(by_post.items(), key=lambda kv: kv[0] or "")]
    return "\n".join(lines)
