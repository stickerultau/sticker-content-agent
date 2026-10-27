"""Console progress output that mirrors the agent's flow, plus the GitHub Actions run summary."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager

TOTAL_STEPS = 5


def info(message: str) -> None:
    print(f"    {message}", flush=True)


def warn(message: str) -> None:
    print(f"    ! {message}", flush=True)


@contextmanager
def step(number: int, title: str):
    print(f"\n[{number}/{TOTAL_STEPS}] {title}", flush=True)
    started = time.time()
    yield
    print(f"    done in {time.time() - started:.0f}s", flush=True)


def summary(markdown: str) -> None:
    """Appends to the GitHub Actions job summary (no-op when running locally)."""
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")
