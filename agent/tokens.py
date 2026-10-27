"""Stores the Instagram access token and keeps it valid (long-lived tokens expire after 60 days unless refreshed).

- Locally: state/ig_token.json (gitignored).
- GitHub Actions: state/ig_token.enc, encrypted with the TOKEN_KEY secret, so the workflow can save refreshed tokens
  by committing the file. Without TOKEN_KEY the file is unreadable.
"""
from __future__ import annotations

import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from .settings import STATE, env

ENCRYPTED = STATE / "ig_token.enc"
PLAIN = STATE / "ig_token.json"


def _fernet() -> Fernet | None:
    key = env("TOKEN_KEY")
    return Fernet(key.encode()) if key else None


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def read_encrypted() -> dict | None:
    """The token data in state/ig_token.enc, or None if there is no file or no TOKEN_KEY."""
    fernet = _fernet()
    if not (fernet and ENCRYPTED.exists()):
        return None
    try:
        return json.loads(fernet.decrypt(ENCRYPTED.read_bytes()))
    except InvalidToken as exc:
        raise RuntimeError("TOKEN_KEY cannot decrypt state/ig_token.enc (key changed?). "
                           "Put a fresh IG_ACCESS_TOKEN in .env, then run: python run.py seal-token") from exc


def load() -> dict:
    stored = read_encrypted()
    if stored is None and PLAIN.exists():
        stored = json.loads(PLAIN.read_text(encoding="utf-8"))

    env_token = env("IG_ACCESS_TOKEN")
    # A token pasted into .env that differs from the one we started from wins (e.g. you generated a new one).
    if env_token and (stored is None or stored.get("seed") != _fingerprint(env_token)):
        return {"access_token": env_token, "refreshed_at": 0, "seed": _fingerprint(env_token)}
    if stored:
        return stored
    raise RuntimeError("No Instagram token yet: put IG_ACCESS_TOKEN in .env (see README, step 3).")


def save(data: dict) -> None:
    STATE.mkdir(exist_ok=True)
    fernet = _fernet()
    if fernet:
        ENCRYPTED.write_bytes(fernet.encrypt(json.dumps(data).encode()))
    else:
        PLAIN.write_text(json.dumps(data, indent=2), encoding="utf-8")


def new_key() -> str:
    return Fernet.generate_key().decode()
