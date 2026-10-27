"""Paths, secrets and the page profile.

Secrets come from environment variables: a local `.env` file, or GitHub Actions secrets in the cloud.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
MUSIC = ASSETS / "music"
STATE = ROOT / "state"
OUTPUT = ROOT / "output"
CONFIG_FILE = ROOT / "config" / "page.yaml"

load_dotenv(ROOT / ".env", override=False)


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def load_config(path: Path = CONFIG_FILE) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)
